"""链路健康状态端点

返回短剧嗅探 / 视频号下载链路的各节点状态，供前端展示链路健康三灯：
- res_download: 短剧嗅探服务（8899 HTTP）
- upstream: 上游 MITM 代理（2023，res_download 的转发目标）
- go_api: 微信视频号后端 HTTP API（2022）
- system_proxy: 系统代理是否指向本应用端口（8899）

任一节点异常时，链路对应功能不可用，前端可据此提示而非静默失败。
"""
import logging

from fastapi import APIRouter

from config.settings import settings

logger = logging.getLogger("link_status")
router = APIRouter(tags=["link_status"])


def _collect_link_status() -> dict:
    """采集各节点状态（不抛异常，任何探测失败都归一为 down）"""
    import socket

    status = {
        "res_download": "down",
        "upstream": "down",
        "go_api": "down",
        "system_proxy": "disabled",
    }

    def _tcp_open(port: int, timeout: float = 1.0) -> bool:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=timeout):
                return True
        except (ConnectionRefusedError, OSError):
            return False

    # 1. res_download HTTP（8899）
    try:
        import requests
        resp = requests.get(f"{settings.res_api_url}/api/app-info", timeout=1.5)
        if resp.status_code == 200:
            status["res_download"] = "up"
    except Exception:
        pass

    # 2. 上游 MITM 代理（2023）
    if _tcp_open(settings.res_upstream_port):
        status["upstream"] = "up"

    # 3. 微信后端 HTTP API（2022）
    try:
        import requests
        resp = requests.get("http://127.0.0.1:2022/api/status", timeout=1.5)
        if resp.status_code == 200 and resp.json().get("code") == 0:
            status["go_api"] = "up"
    except Exception:
        pass

    # 4. 系统代理指向（仅 Windows）
    if __import__("sys").platform == "win32":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Internet Settings", 0, winreg.KEY_READ) as key:
                proxy_enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
                proxy_server, _ = winreg.QueryValueEx(key, "ProxyServer")
            if proxy_enable and proxy_server == f"127.0.0.1:{settings.res_port}":
                status["system_proxy"] = "enabled"
            elif proxy_enable:
                status["system_proxy"] = "other"
        except Exception:
            status["system_proxy"] = "unknown"

    return status


@router.get("/api/service/link-status")
def get_link_status():
    """获取链路健康状态"""
    status = _collect_link_status()
    unhealthy = [k for k, v in status.items() if v in ("down", "other")]
    logger.info("[链路] 状态: %s", status)
    return {"code": 0, "data": status, "unhealthy": unhealthy}
