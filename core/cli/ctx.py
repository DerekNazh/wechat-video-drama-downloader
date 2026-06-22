"""CLI 共享上下文 — 数据库初始化、Service 实例缓存"""

import logging
from functools import lru_cache

logger = logging.getLogger("cli.ctx")

_initialized = False


def ensure_init():
    """确保数据库和配置已初始化（幂等）"""
    global _initialized
    if _initialized:
        return

    from config.settings import settings
    from core.utils.database import db

    _initialized = True
    logger.debug("CLI 上下文初始化完成")


@lru_cache(maxsize=1)
def get_author_service():
    from core.service.author import AuthorService
    return AuthorService()


@lru_cache(maxsize=1)
def get_video_service():
    from core.service.video import VideoService
    return VideoService()


@lru_cache(maxsize=1)
def get_task_service():
    from core.service.task import TaskService
    return TaskService()


@lru_cache(maxsize=1)
def get_search_service():
    from core.service.search import SearchService
    return SearchService()


@lru_cache(maxsize=1)
def get_wechat_service():
    from core.utils.base_servier import WechatVideoService
    return WechatVideoService()


@lru_cache(maxsize=1)
def get_monitor_service():
    from core.monitor.monitor import MonitorService
    return MonitorService()
