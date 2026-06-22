"""全局错误码定义

所有 API 返回的错误统一使用 error_code 字段，前端根据 error_code 做差异化处理。

使用方式：
    from core.api.error_codes import ErrorCode
    from core.api.exceptions import BizError

    raise BizError(ErrorCode.DOC_QUOTA_EXCEEDED)
    raise BizError(ErrorCode.DOC_AUTH_FAILED, detail="Client ID 与 Token 不匹配")
"""


class ErrorCode:
    """错误码常量

    命名规则：模块_具体错误（大写 + 下划线）
    每个错误码包含：
        code:     机器可读标识，前端 switch/case 用
        message:  中文默认消息，前端可直接展示
        severity: 严重程度 fatal/warn/retry
            - fatal:  需要用户介入（重配凭证、联系管理员）
            - warn:   警告，不影响主流程
            - retry:  可自动重试（网络超时、限流）
    """

    # ============================================================
    # 通用错误 1xxx
    # ============================================================
    UNKNOWN = ("UNKNOWN", "未知错误，请重试", "fatal")
    PARAM_MISSING = ("PARAM_MISSING", "缺少必要参数", "fatal")
    PARAM_INVALID = ("PARAM_INVALID", "参数格式错误", "fatal")
    NETWORK_TIMEOUT = ("NETWORK_TIMEOUT", "网络请求超时，请检查网络连接", "retry")
    NETWORK_ERROR = ("NETWORK_ERROR", "网络连接失败", "retry")

    # ============================================================
    # 微信/Go 后端 2xxx
    # ============================================================
    WX_BACKEND_OFFLINE = ("WX_BACKEND_OFFLINE", "微信视频号后端服务未启动", "fatal")
    WX_NOT_CONNECTED = ("WX_NOT_CONNECTED", "微信客户端未连接，请先打开微信并登录", "fatal")
    WX_SEARCH_FAILED = ("WX_SEARCH_FAILED", "微信搜索接口调用失败", "retry")

    # ============================================================
    # 腾讯文档 3xxx
    # ============================================================
    DOC_QUOTA_EXCEEDED = ("DOC_QUOTA_EXCEEDED", "腾讯文档 API 配额已用完，请稍后重试或明天再试", "retry")
    DOC_AUTH_FAILED = ("DOC_AUTH_FAILED", "腾讯文档认证失败，请检查 Access Token 是否正确", "fatal")
    DOC_TOKEN_MISMATCH = ("DOC_TOKEN_MISMATCH", "腾讯文档凭证不匹配，Client ID 与 Access Token 必须属于同一应用", "fatal")
    DOC_PERMISSION_DENIED = ("DOC_PERMISSION_DENIED", "无权访问该文档，请检查文档分享权限", "fatal")
    DOC_NOT_FOUND = ("DOC_NOT_FOUND", "文档不存在或已被删除", "fatal")
    DOC_NO_SHEET = ("DOC_NO_SHEET", "文档没有子表，请先创建一个子表", "fatal")
    DOC_MULTI_SHEET = ("DOC_MULTI_SHEET", "文档只能有1个子表，请删除多余的子表", "fatal")
    DOC_PARSE_ERROR = ("DOC_PARSE_ERROR", "文档数据解析失败，请检查表格格式", "warn")
    DOC_URL_INVALID = ("DOC_URL_INVALID", "腾讯文档 URL 格式不正确", "fatal")
    DOC_CREDENTIAL_MISSING = ("DOC_CREDENTIAL_MISSING", "缺少腾讯文档凭证，请提供 Client ID、Access Token、Open ID", "fatal")
    DOC_WRITE_FAILED = ("DOC_WRITE_FAILED", "腾讯文档写入失败", "retry")

    # ============================================================
    # 数据库 4xxx
    # ============================================================
    DB_AUTHOR_NOT_FOUND = ("DB_AUTHOR_NOT_FOUND", "作者不存在", "warn")
    DB_CREATE_FAILED = ("DB_CREATE_FAILED", "数据库写入失败", "fatal")
    DB_UPDATE_FAILED = ("DB_UPDATE_FAILED", "数据库更新失败", "fatal")

    # ============================================================
    # 下载/任务 5xxx
    # ============================================================
    DOWNLOAD_CREATE_FAILED = ("DOWNLOAD_CREATE_FAILED", "下载任务创建失败", "retry")
    DOWNLOAD_FILE_MISSING = ("DOWNLOAD_FILE_MISSING", "下载文件不存在或已被删除", "warn")

    # ============================================================
    # 文档监控 6xxx
    # ============================================================
    DOC_SYNC_ALREADY_RUNNING = ("DOC_SYNC_ALREADY_RUNNING", "文档监控已在运行中", "warn")
    DOC_SYNC_NOT_RUNNING = ("DOC_SYNC_NOT_RUNNING", "文档监控未启动", "warn")
    DOC_SYNC_DIFF_FAILED = ("DOC_SYNC_DIFF_FAILED", "文档差异对比失败，将在下一轮重试", "retry")

    @classmethod
    def to_dict(cls, error_tuple, detail: str = "") -> dict:
        """转换为 API 返回格式

        Args:
            error_tuple: (code, message, severity)
            detail: 附加详情（可选，覆盖默认 message）

        Returns:
            {"code": -1, "error_code": "DOC_QUOTA_EXCEEDED",
             "msg": "...", "severity": "retry", "detail": "..."}
        """
        code, message, severity = error_tuple
        return {
            "code": -1,
            "error_code": code,
            "msg": detail or message,
            "severity": severity,
        }
