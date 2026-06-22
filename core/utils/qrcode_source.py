"""二维码图片来源 - 支持本地/HTTP/OSS多种来源"""

from abc import ABC, abstractmethod


class QRCodeSource(ABC):
    """二维码图片来源基类"""

    @abstractmethod
    def get_url(self) -> str:
        """获取二维码图片URL（前端可访问）"""
        pass

    @abstractmethod
    def get_type(self) -> str:
        """获取类型标识：local / http / oss"""
        pass


class LocalQRCodeSource(QRCodeSource):
    """本地文件来源"""

    def __init__(self, url: str = "/static/leader/2wm.jpg"):
        self._url = url

    def get_url(self) -> str:
        return self._url

    def get_type(self) -> str:
        return "local"


class HttpQRCodeSource(QRCodeSource):
    """HTTP静态资源来源"""

    def __init__(self, url: str):
        self._url = url

    def get_url(self) -> str:
        return self._url

    def get_type(self) -> str:
        return "http"


class OSSQRCodeSource(QRCodeSource):
    """阿里云OSS来源"""

    def __init__(self, url: str):
        self._url = url

    def get_url(self) -> str:
        return self._url

    def get_type(self) -> str:
        return "oss"


def get_qrcode_source(source_type: str = "local", url: str = None) -> QRCodeSource:
    """工厂函数：根据类型创建对应的来源实例"""
    if source_type == "local":
        return LocalQRCodeSource(url or "/static/leader/2wm.jpg")
    elif source_type == "http":
        return HttpQRCodeSource(url)
    elif source_type == "oss":
        return OSSQRCodeSource(url)
    else:
        return LocalQRCodeSource()
