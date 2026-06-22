"""开屏弹窗业务逻辑"""

from core.utils.qrcode_source import get_qrcode_source


class SplashService:
    """开屏弹窗服务"""

    def __init__(self, source_type: str = "local", url: str = None):
        self._source = get_qrcode_source(source_type, url)

    def get_splash_config(self) -> dict:
        """获取弹窗配置"""
        return {
            "show": True,
            "qrcode_url": self._source.get_url(),
            "source_type": self._source.get_type(),
        }


# 默认实例：使用本地图片
splash_service = SplashService(source_type="local")