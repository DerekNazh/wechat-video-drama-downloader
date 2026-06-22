"""短剧嗅探代理路由

将前端 sniff iframe 的 /api/* 请求透传到 res_download:8899
Python 已有路由均带二级前缀（/api/service/、/api/video/ 等），无冲突
"""
import logging
from pathlib import Path

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import Response, StreamingResponse

from config.settings import settings

logger = logging.getLogger("api_sniff_proxy")
router = APIRouter(tags=["sniff_proxy"])

RES_API_BASE = settings.res_api_url
HTTP_TIMEOUT = 15.0

# res_download 的 10 个 API 路径
RES_API_PATHS = frozenset({
    "/api/resources",
    "/api/download",
    "/api/direct-download",
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


def _is_res_api(path: str) -> bool:
    """判断请求路径是否属于 res_download 的 API"""
    return path in RES_API_PATHS or path.startswith("/api/")


async def _proxy_request(request: Request) -> Response:
    """通用代理：将请求透传到 res_download 服务"""
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

    logger.debug("[代理] %s %s → %s", method, path, target_url)

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            resp = await client.request(
                method=method,
                url=target_url,
                headers=headers,
                content=body,
            )

        content_type = resp.headers.get("content-type", "application/json")
        return Response(
            content=resp.content,
            status_code=resp.status_code,
            media_type=content_type,
        )
    except httpx.ConnectError:
        logger.warning("[代理] res_download 服务未响应: %s", target_url)
        return Response(
            content='{"code":0,"message":"res_download 服务未启动","data":null}',
            status_code=502,
            media_type="application/json",
        )
    except Exception as e:
        logger.error("[代理] 请求转发失败: %s %s → %s", method, path, e)
        return Response(
            content=f'{{"code":0,"message":"代理请求失败: {e}","data":null}}',
            status_code=502,
            media_type="application/json",
        )


# 为每个 res_download API 路径注册 GET 和 POST 代理
for _api_path in RES_API_PATHS:
    # 用闭包捕获路径，避免循环变量问题
    def _make_route(p: str):
        @router.api_route(p, methods=["GET", "POST", "PUT", "DELETE"], include_in_schema=False)
        async def _proxy_route(request: Request) -> Response:
            return await _proxy_request(request)
        return _proxy_route

    _make_route(_api_path)

logger.info("[代理] 已注册 %d 个 res_download API 代理路由", len(RES_API_PATHS))
