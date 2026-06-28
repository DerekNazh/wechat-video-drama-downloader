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
HTTP_TIMEOUT = 15.0
DOWNLOAD_TIMEOUT = 120.0

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
    """Python 自行下载，文件名 = 短剧ID_序号_视频ID.mp4"""
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

    save_dir = str(settings.wx_download_dir)
    app_dir = Path(save_dir) / "短剧" / app_id

    # 序号 = 该短剧目录已有文件数 + 1
    seq = sum(1 for f in app_dir.iterdir() if f.is_file()) + 1 if app_dir.is_dir() else 1

    filename = f"{app_id}_{seq}_{video_id}{suffix}"
    save_path = app_dir / filename

    # 已存在则跳过
    if save_path.exists():
        logger.info("[direct-download] 文件已存在: %s", save_path)
        return Response(content=json.dumps({"code": 1, "message": "ok", "data": {"save_path": str(save_path)}}), media_type="application/json")

    # 下载
    os.makedirs(str(app_dir), exist_ok=True)
    logger.info("[direct-download] %s → %s", download_url, save_path)

    try:
        async with httpx.AsyncClient(timeout=DOWNLOAD_TIMEOUT, follow_redirects=True) as client:
            resp = await client.get(download_url)
        if resp.status_code != 200:
            logger.error("[direct-download] HTTP %d", resp.status_code)
            return Response(content=json.dumps({"code": 0, "message": f"HTTP {resp.status_code}", "data": None}), media_type="application/json")

        with open(str(save_path), "wb") as f:
            f.write(resp.content)

        logger.info("[direct-download] 完成: %s (%d bytes)", save_path, len(resp.content))
        return Response(content=json.dumps({"code": 1, "message": "ok", "data": {"save_path": str(save_path)}}), media_type="application/json")
    except Exception as e:
        logger.error("[direct-download] 失败: %s", e)
        return Response(content=json.dumps({"code": 0, "message": str(e), "data": None}), media_type="application/json")


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
