"""本地 API 安全中间件（YZPQ-311）：仅本机 + token 鉴权 + Host 校验 + 错误脱敏。

提供纯判定函数，可被任意框架（FastAPI/aiohttp）包装。绑定 127.0.0.1 由启动
配置保证，这里只做请求级校验。
"""
from __future__ import annotations

ALLOWED_HOSTS = {"127.0.0.1", "localhost"}


def check_token(provided: str | None, expected: str) -> bool:
    """无 token / 错 token 一律 False（401）。expected 为空则不校验（开发兜底）。"""
    if not expected:
        return True
    return bool(provided) and provided == expected


def check_host(host_header: str | None) -> bool:
    """Host 头须是本机（去掉端口）。"""
    if not host_header:
        return False
    host = host_header.split(":")[0].lower()
    return host in ALLOWED_HOSTS


def sanitize_error(exc: Exception) -> dict:
    """错误响应脱敏：不外泄路径/堆栈/密钥，只给通用文案。"""
    return {"error": "internal_error", "detail": "请求处理失败"}
