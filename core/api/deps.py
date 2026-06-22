"""API 依赖项：Go 后端 + 微信连接状态校验

用于 Depends() 注入，确保调用 Go 后端 API 的路由
在 Go 后端在线且微信已连接时才放行。
"""
import logging

from fastapi import Depends
from fastapi import HTTPException

from core.utils.weixin_client import WechatVideoAPIClient

logger = logging.getLogger("api_deps")


def require_go_online():
    """校验 Go 后端在线（不要求微信连接）

    用于查询类接口，如任务列表。
    """
    client = WechatVideoAPIClient()

    service_ok = client.check_service()
    if not service_ok:
        logger.warning("[require_go_online] 拒绝请求: Go 后端未响应 (check_service=False)")
        raise HTTPException(
            status_code=503,
            detail={"code": -1, "msg": "微信视频号后端服务未启动，请先启动服务"},
        )


def require_wechat():
    """校验 Go 后端在线 + 微信已连接

    用法：
        @router.post("/xxx", dependencies=[Depends(require_wechat)])
    """
    client = WechatVideoAPIClient()

    if not client.check_service():
        logger.warning("[require_wechat] 拒绝请求: Go 后端未响应 (check_service=False)")
        raise HTTPException(
            status_code=503,
            detail={"code": -1, "msg": "微信视频号后端服务未启动，请先启动服务"},
        )

    if not client.check_wechat_connected():
        logger.warning("[require_wechat] 拒绝请求: 微信未连接 (check_wechat_connected=False)")
        raise HTTPException(
            status_code=503,
            detail={"code": -2, "msg": "微信视频号客户端未连接，请先打开微信并登录"},
        )
