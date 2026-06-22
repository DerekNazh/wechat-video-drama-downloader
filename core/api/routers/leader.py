"""开屏弹窗 API 路由"""

from fastapi import APIRouter

from config.settings import settings
from core.service.leader import splash_service

router = APIRouter(prefix="/api/leader", tags=["leader"])


@router.get("/splash")
def get_splash():
    """获取开屏弹窗配置（受广告开关控制）"""
    if not settings.ads_enabled:
        return {"code": 0, "data": None}
    config = splash_service.get_splash_config()
    return {"code": 0, "data": config}
