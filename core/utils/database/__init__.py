"""
数据库模块 - 分层架构

结构：
├── __init__.py     # 统一导出
├── base.py         # Database + DatabaseBase + 单例 db
└── crud/
    ├── models.py   # 数据模型
    ├── author_dao.py
    ├── video_dao.py
    └── task_dao.py
"""

from core.utils.database.base import (
    Database,
    DatabaseBase,
    db,
    get_database,
)
from core.utils.database.crud.models import Author, AuthorVideo, DownloadTask
from core.utils.database.crud.author_dao import AuthorDAO
from core.utils.database.crud.video_dao import VideoDAO
from core.utils.database.crud.task_dao import TaskDAO

__all__ = [
    # 主类
    "Database",
    "DatabaseBase",
    # 生产环境单例
    "db",
    "get_database",
    # 数据模型
    "Author",
    "AuthorVideo",
    "DownloadTask",
    # DAO
    "AuthorDAO",
    "VideoDAO",
    "TaskDAO",
]
