"""
数据存储层 - SQLite
兼容层：从 database 模块重新导出
"""

from core.utils.database import (
    Database,
    Author,
    AuthorVideo,
    DownloadTask,
)

__all__ = [
    "Database",
    "Author",
    "AuthorVideo",
    "DownloadTask",
    "generate_id",
]


def generate_id() -> str:
    """生成随机唯一字符串"""
    import secrets
    import string
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(16))
