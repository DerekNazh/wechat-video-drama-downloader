"""结构化业务异常

所有服务层/工具层抛出的业务错误统一使用 BizError，
API 层捕获后直接调用 .to_response() 返回给前端。

使用方式：
    from core.api.exceptions import BizError
    from core.api.error_codes import ErrorCode

    # 服务层抛出
    raise BizError(ErrorCode.DOC_QUOTA_EXCEEDED)
    raise BizError(ErrorCode.DOC_AUTH_FAILED, detail="Client ID 不匹配")

    # API 层捕获
    try:
        ...
    except BizError as e:
        return e.to_response()
"""
import logging
from typing import Optional

logger = logging.getLogger("api_exceptions")


class BizError(Exception):
    """业务异常基类

    Attributes:
        error_code: 机器可读标识 (如 "DOC_QUOTA_EXCEEDED")
        message:    默认中文消息
        severity:   严重程度 fatal/warn/retry
        detail:     附加详情（覆盖默认 message）
    """

    def __init__(self, error_tuple: tuple, detail: str = ""):
        self.error_code, self.message, self.severity = error_tuple
        self.detail = detail
        super().__init__(detail or self.message)

    def to_response(self) -> dict:
        """转换为 API 返回格式"""
        return {
            "code": -1,
            "error_code": self.error_code,
            "msg": self.detail or self.message,
            "severity": self.severity,
        }

    def log(self, extra: str = ""):
        """记录日志（按严重程度选择日志级别）"""
        msg = f"[{self.error_code}] {self.detail or self.message}"
        if extra:
            msg += f" | {extra}"
        if self.severity == "fatal":
            logger.error(msg)
        elif self.severity == "retry":
            logger.warning(msg)
        else:
            logger.info(msg)

    def __repr__(self):
        return f"BizError(code={self.error_code}, severity={self.severity}, msg={self.detail or self.message})"
