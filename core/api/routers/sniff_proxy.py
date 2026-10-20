"""短剧嗅探代理路由

将前端 sniff iframe 的 /api/* 请求透传到 res_download:8899
Python 已有路由均带二级前缀（/api/service/、/api/video/ 等），无冲突

特殊处理：
- /api/direct-download: Python 自行下载，命名规则 短剧ID_序号_视频ID.mp4
  序号 = 目标短剧目录已有文件数 + 1
"""
import json
import logging
import os
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import Response

from config.settings import settings

logger = logging.getLogger("api_sniff_proxy")
router = APIRouter(tags=["sniff_proxy"])

RES_API_BASE = settings.res_api_url
# 超时参数化：可在 .env 中调整（SNIFF_PROXY_TIMEOUT / SNIFF_DOWNLOAD_TIMEOUT）
HTTP_TIMEOUT = settings.sniff_proxy_timeout
DOWNLOAD_TIMEOUT = settings.sniff_download_timeout

# 直接透传的 API
DIRECT_PROXY_PATHS = frozenset({
    "/api/resources",
    "/api/download",
    "/api/clear",
    "/api/delete",
    "/api/set-type",
    "/api/set-config",
    "/api/get-config",
    "/api/proxy-open",
    "/api/proxy-unset",
    "/api/is-proxy",
    "/api/app-info",
    "/api/install",
    "/api/preview",
    "/api/open-folder",
    "/api/cert",
    "/api/set-system-password",
    "/api/wx-file-decode",
    "/api/batch-export",
})


def _parse_download_url(download_url: str) -> tuple:
    """从 URL 提取短剧ID、视频ID、后缀

    Returns: (app_id, video_id, suffix)
    """
    parsed = urlparse(download_url)
    path_clean = parsed.path.split("?")[0].split("#")[0]

    suffix = os.path.splitext(os.path.basename(path_clean))[1] or ".mp4"

    # 短剧ID: 域名第一个 . 之前
    host = parsed.hostname or ""
    app_id = host.split(".")[0] if "." in host else ""

    # 视频ID: 路径倒数第二段
    parts = [p for p in path_clean.split("/") if p]
    video_id = parts[-2] if len(parts) >= 2 else ""

    return app_id, video_id, suffix


async def _handle_direct_download(request: Request) -> Response:
    """Python 自行下载，文件名 = 短剧ID_序号_视频ID.mp4

    功能性保证（针对"下载不了但前端假装成功"问题）：
    1. 失败一律返回 HTTP 非 200 → 前端 await 抛异常 → 显示 error，杜绝假成功
    2. 下载失败/中断后清理残留文件，避免下次 exists() 跳过损坏文件
    3. 已存在但 size==0 视为损坏文件 → 删除重下
    4. 流式写入，避免大文件一次性读入内存导致 OOM
    5. 携带防盗链 headers（Referer 取目标 URL origin + 浏览器 UA）
    """
    body = await request.body()
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, TypeError):
        return Response(content='{"code":0,"message":"请求体解析失败","data":null}', status_code=400, media_type="application/json")

    download_url = data.get("url", "")
    if not download_url:
        return Response(content='{"code":0,"message":"url is required","data":null}', status_code=400, media_type="application/json")

    app_id, video_id, suffix = _parse_download_url(download_url)

    # 无法提取短剧ID，转交 res_download
    if not app_id or not video_id:
        logger.info("[direct-download] 无法提取短剧ID/视频ID，转交 res_download")
        return await _proxy_request(request)

    save_dir = str(settings.short_drama_download_dir)
    app_dir = Path(save_dir) / app_id

    # 已存在校验（先于序号生成）：
    # 文件名 = {app_id}_{seq}_{video_id}{suffix}，同一短剧目录内 video_id 唯一，
    # 因此按 "_video_id{suffix}" 匹配即可命中已下载文件。
    # 若用"文件数+1"序号直接生成，则重复点击永远生成新序号文件，永不命中旧文件（重复下载）。
    existing_valid = []
    existing_zero = []
    if app_dir.is_dir():
        for f in app_dir.iterdir():
            if not f.is_file():
                continue
            try:
                size = f.stat().st_size
            except OSError:
                continue
            (existing_valid if size > 0 else existing_zero).append(f)

    video_suffix = f"_{video_id}{suffix}"

    # 1) 有效文件命中 → 跳过（不重复下载）
    matched = [f for f in existing_valid if f.name.endswith(video_suffix)]
    if matched:
        logger.info("[direct-download] 文件已存在: %s", matched[0])
        return Response(content=json.dumps({"code": 1, "message": "ok", "data": {"save_path": str(matched[0])}}), media_type="application/json")

    # 2) 0 字节同名残留 → 删除重下（避免永久假成功）
    zero_matched = [f for f in existing_zero if f.name.endswith(video_suffix)]
    if zero_matched:
        logger.warning("[direct-download] 检测到 0 字节损坏残留，删除重下: %s", zero_matched[0])
        try:
            zero_matched[0].unlink()
        except OSError as e:
            logger.error("[direct-download] 删除损坏残留失败: %s", e)

    # 3) 序号 = 有效文件数 + 1（0 字节文件不计入）
    seq = len(existing_valid) + 1
    filename = f"{app_id}_{seq}_{video_id}{suffix}"
    save_path = app_dir / filename

    # 防盗链 headers：Referer 取目标 URL origin，UA 透传浏览器
    parsed = urlparse(download_url)
    origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.netloc else None
    dl_headers = {
        "User-Agent": request.headers.get("user-agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"),
    }
    if origin:
        dl_headers["Referer"] = origin

    # 下载（流式写入，防大文件内存 OOM）
    os.makedirs(str(app_dir), exist_ok=True)
    logger.info("[direct-download] %s → %s", download_url, save_path)

    try:
        async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
            async with client.stream("GET", download_url, headers=dl_headers) as resp:
                if resp.status_code != 200:
                    logger.error("[direct-download] HTTP %d", resp.status_code)
                    _cleanup_failed_download(save_path)
                    return Response(content=json.dumps({"code": 0, "message": f"HTTP {resp.status_code}", "data": None}), status_code=502, media_type="application/json")

                with open(str(save_path), "wb") as f:
                    total = 0
                    async for chunk in resp.aiter_bytes():
                        f.write(chunk)
                        total += len(chunk)

        if total == 0:
            logger.error("[direct-download] 下载内容为空，视为失败")
            _cleanup_failed_download(save_path)
            return Response(content='{"code":0,"message":"下载内容为空","data":null}', status_code=502, media_type="application/json")

        logger.info("[direct-download] 完成: %s (%d bytes)", save_path, total)
        return Response(content=json.dumps({"code": 1, "message": "ok", "data": {"save_path": str(save_path)}}), media_type="application/json")
    except Exception as e:
        logger.error("[direct-download] 失败: %s", e)
        _cleanup_failed_download(save_path)
        return Response(content=json.dumps({"code": 0, "message": str(e), "data": None}), status_code=502, media_type="application/json")


def _cleanup_failed_download(save_path: Path):
    """下载失败后清理残留文件（部分/空文件会让下次 exists() 误判为已下载）"""
    try:
        if save_path.exists():
            save_path.unlink()
            logger.info("[direct-download] 已清理失败残留: %s", save_path)
    except OSError as e:
        logger.warning("[direct-download] 清理失败残留异常: %s", e)


async def _proxy_request(request: Request) -> Response:
    """通用代理：透传到 res_download"""
    path = request.url.path
    query = request.url.query
    method = request.method
    target_url = f"{RES_API_BASE}{path}"
    if query:
        target_url += f"?{query}"

    headers = dict(request.headers)
    headers.pop("host", None)
    headers.pop("Host", None)
    body = await request.body()

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.request(method=method, url=target_url, headers=headers, content=body)
        return Response(content=resp.content, status_code=resp.status_code, media_type=resp.headers.get("content-type", "application/json"))
    except httpx.ConnectError:
        return Response(content='{"code":0,"message":"res_download 服务未启动","data":null}', status_code=502, media_type="application/json")
    except Exception as e:
        return Response(content=f'{{"code":0,"message":"{e}","data":null}}', status_code=502, media_type="application/json")


# 通用透传路由
for _api_path in DIRECT_PROXY_PATHS:
    def _make_route(p: str):
        @router.api_route(p, methods=["GET", "POST", "PUT", "DELETE"], include_in_schema=False)
        async def _proxy_route(request: Request) -> Response:
            return await _proxy_request(request)
        return _proxy_route
    _make_route(_api_path)


# /api/direct-download: 序号下载
@router.api_route("/api/direct-download", methods=["POST"], include_in_schema=False)
async def _direct_download_route(request: Request) -> Response:
    return await _handle_direct_download(request)

logger.info("[代理] 已注册 %d 个透传路由 + 1 个 direct-download 序号路由", len(DIRECT_PROXY_PATHS))
