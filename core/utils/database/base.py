"""Database 基类 - 连接管理、事务、初始化"""

import logging
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from abc import ABC

logger = logging.getLogger("database")


class DatabaseBase(ABC):
    """数据库基类

    提供连接管理、事务处理、表初始化等基础功能
    子类实现具体的 CRUD 操作
    """

    def __init__(self, db_path: str):
        self.db_path = Path(db_path)
        self._local = threading.local()
        self._init_db()

    def close(self):
        """关闭数据库连接"""
        if hasattr(self._local, 'conn'):
            self._local.conn.close()
            del self._local.conn

    def _get_conn(self) -> sqlite3.Connection:
        """获取线程本地连接"""
        if not hasattr(self._local, 'conn'):
            # timeout=30: 等待锁释放最多30秒
            # check_same_thread=False: 允许多线程访问
            conn = sqlite3.connect(str(self.db_path), timeout=30.0, check_same_thread=False)
            conn.execute("PRAGMA foreign_keys = ON")
            # 启用 WAL 模式：写入不阻塞读取，并发性能更好
            conn.execute("PRAGMA journal_mode = WAL")
            # FULL 模式：每次 commit 都确保 WAL 写入磁盘，防止 OS 崩溃丢失最后几个事务
            conn.execute("PRAGMA synchronous = FULL")
            # 设置 busy_timeout，SQLite 会自动重试
            conn.execute("PRAGMA busy_timeout = 30000")
            self._local.conn = conn
        return self._local.conn

    @contextmanager
    def _cursor(self):
        """获取游标（自动提交/回滚）"""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            yield cursor
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_db(self):
        """初始化数据库表（子类可重写添加更多表）"""
        with self._cursor() as cursor:
            # 作者表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS authors (
                    id TEXT PRIMARY KEY,
                    source_author_id TEXT UNIQUE,
                    name TEXT NOT NULL,
                    tag TEXT,
                    bio TEXT,
                    avatar_url TEXT,
                    cover_img_url TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    latest_publish_date TEXT
                )
            """)
            # 升级：添加 latest_publish_date 字段（如果不存在）
            try:
                cursor.execute("""
                    ALTER TABLE authors ADD COLUMN latest_publish_date TEXT
                """)
            except sqlite3.OperationalError:
                pass

            # 作者视频表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS author_videos (
                    video_id TEXT PRIMARY KEY,
                    author_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    object_nonce_id TEXT,
                    url TEXT,
                    spec TEXT,
                    file_size INTEGER DEFAULT 0,
                    cover_url TEXT,
                    decode_key INTEGER DEFAULT 0,
                    author_avatar TEXT,
                    duration INTEGER DEFAULT 0,
                    create_time TEXT,
                    is_downloaded INTEGER DEFAULT 0,
                    download_path TEXT,
                    downloaded_at TEXT,
                    video_type TEXT DEFAULT 'short_video',
                    FOREIGN KEY (author_id) REFERENCES authors(id) ON DELETE CASCADE
                )
            """)
            # 索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_author_videos_author_id
                ON author_videos(author_id)
            """)
            # 旧库迁移：添加 downloaded_at 字段
            try:
                cursor.execute("ALTER TABLE author_videos ADD COLUMN downloaded_at TEXT")
            except sqlite3.OperationalError:
                pass

            # 旧库迁移：添加 video_type 字段
            try:
                cursor.execute("ALTER TABLE author_videos ADD COLUMN video_type TEXT DEFAULT 'short_video'")
            except sqlite3.OperationalError:
                pass

            # 下载任务表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS download_tasks (
                    task_id TEXT PRIMARY KEY,
                    video_id TEXT NOT NULL,
                    url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    filename TEXT NOT NULL,
                    spec TEXT NOT NULL,
                    suffix TEXT NOT NULL,
                    key INTEGER DEFAULT 0,
                    status TEXT DEFAULT 'pending',
                    progress INTEGER DEFAULT 0,
                    downloaded INTEGER DEFAULT 0,
                    total_size INTEGER DEFAULT 0,
                    speed INTEGER DEFAULT 0,
                    error_msg TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    video_type TEXT DEFAULT 'short_video'
                )
            """)
            # 索引
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_download_tasks_video_id
                ON download_tasks(video_id)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_download_tasks_status
                ON download_tasks(status)
            """)

            # 旧库迁移：添加 video_type 字段
            try:
                cursor.execute("ALTER TABLE download_tasks ADD COLUMN video_type TEXT DEFAULT 'short_video'")
            except sqlite3.OperationalError:
                pass

            # 旧库迁移：添加 create_time 字段（视频发布时间）
            try:
                cursor.execute("ALTER TABLE download_tasks ADD COLUMN create_time TEXT DEFAULT ''")
            except sqlite3.OperationalError:
                pass

            # 任务完成记录表
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS task_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    video_id TEXT NOT NULL,
                    author_id TEXT,
                    username TEXT,
                    title TEXT,
                    cover_url TEXT,
                    duration INTEGER DEFAULT 0,
                    file_size INTEGER DEFAULT 0,
                    completed_at TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
                )
            """)
            cursor.execute("""
                CREATE UNIQUE INDEX IF NOT EXISTS idx_task_log_unique
                ON task_log(video_id, completed_at)
            """)
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_task_log_video_id
                ON task_log(video_id)
            """)

        logger.info(f"[Database] 初始化完成: {self.db_path}")


# ========== Database 主类 ==========

from core.utils.database.crud.models import Author, AuthorVideo, DownloadTask
from core.utils.database.crud.author_dao import AuthorDAO
from core.utils.database.crud.video_dao import VideoDAO
from core.utils.database.crud.task_dao import TaskDAO
from core.utils.database.crud.log_dao import LogDAO


class Database(DatabaseBase):
    """统一数据库类

    整合所有 DAO 操作，提供完整的数据库接口
    """

    def __init__(self, db_path: str):
        super().__init__(db_path)
        self._author_dao = AuthorDAO()
        self._video_dao = VideoDAO()
        self._task_dao = TaskDAO()
        self._log_dao = LogDAO()

    # ========== 作者操作 ==========

    def create_author(self, author: Author) -> bool:
        with self._cursor() as cursor:
            return self._author_dao.create(cursor, author)

    def get_author(self, author_id: str) -> Author:
        with self._cursor() as cursor:
            return self._author_dao.get_by_id(cursor, author_id)

    def get_author_by_source_id(self, source_author_id: str) -> Author:
        with self._cursor() as cursor:
            return self._author_dao.get_by_source_id(cursor, source_author_id)

    def get_author_by_name(self, name: str) -> Author:
        with self._cursor() as cursor:
            return self._author_dao.get_by_name(cursor, name)

    def update_author(self, author: Author) -> bool:
        with self._cursor() as cursor:
            return self._author_dao.update(cursor, author)

    def update_author_latest_publish_date(self, author_id: str, latest_publish_date: str) -> bool:
        with self._cursor() as cursor:
            return self._author_dao.update_latest_publish_date(cursor, author_id, latest_publish_date)

    def delete_author(self, author_id: str) -> bool:
        """删除作者，同时清理关联的视频记录和下载任务（幂等：不存在的作者视为已删除）

        所有步骤在同一事务中执行，任何步骤失败都会触发整体回滚。
        """
        with self._cursor() as cursor:
            # 1. 查询该作者所有视频的 video_id
            cursor.execute(
                "SELECT video_id FROM author_videos WHERE author_id = ?",
                (author_id,),
            )
            video_ids = [row[0] for row in cursor.fetchall()]

            # 2. 删除关联的下载任务
            if video_ids:
                placeholders = ",".join("?" * len(video_ids))
                cursor.execute(
                    f"DELETE FROM download_tasks WHERE video_id IN ({placeholders})",
                    video_ids,
                )

            # 3. 删除关联的视频记录
            cursor.execute(
                "DELETE FROM author_videos WHERE author_id = ?",
                (author_id,),
            )

            # 4. 删除作者记录（直接 execute，让异常冒泡触发 rollback）
            cursor.execute(
                "DELETE FROM authors WHERE id = ?",
                (author_id,),
            )
            return True

    def list_authors(self, limit: int = 0, offset: int = 0):
        with self._cursor() as cursor:
            return self._author_dao.list_all(cursor, limit, offset)

    # ========== 视频操作 ==========

    def create_author_video(self, video: AuthorVideo) -> bool:
        with self._cursor() as cursor:
            return self._video_dao.create(cursor, video)

    def get_author_video(self, video_id: str) -> AuthorVideo:
        with self._cursor() as cursor:
            return self._video_dao.get_by_id(cursor, video_id)

    def list_author_videos(self, author_id: str, limit: int = 0, offset: int = 0):
        with self._cursor() as cursor:
            return self._video_dao.list_by_author(cursor, author_id, limit, offset)

    def list_author_videos_by_type(self, author_id: str, video_type: str, limit: int = 0, offset: int = 0):
        with self._cursor() as cursor:
            return self._video_dao.list_by_author_and_type(cursor, author_id, video_type, limit, offset)

    def list_undownloaded_videos(self, limit: int = 10):
        with self._cursor() as cursor:
            return self._video_dao.list_undownloaded(cursor, limit)

    def delete_author_video(self, video_id: str) -> bool:
        with self._cursor() as cursor:
            return self._video_dao.delete(cursor, video_id)

    def update_video_downloaded(self, video_id: str, download_path: str) -> bool:
        with self._cursor() as cursor:
            return self._video_dao.update_downloaded(cursor, video_id, download_path)

    def update_video_url(self, video_id: str, new_url: str) -> bool:
        """更新视频 URL（用于刷新过期 URL）"""
        with self._cursor() as cursor:
            return self._video_dao.update_url(cursor, video_id, new_url)

    def reset_video_downloaded(self, video_id: str) -> bool:
        with self._cursor() as cursor:
            return self._video_dao.reset_downloaded(cursor, video_id)

    def count_videos_today(self) -> int:
        with self._cursor() as cursor:
            return self._video_dao.count_today(cursor)

    def count_downloaded_today(self) -> int:
        with self._cursor() as cursor:
            return self._video_dao.count_downloaded_today(cursor)

    def count_videos_total(self) -> int:
        with self._cursor() as cursor:
            return self._video_dao.count_total(cursor)

    def get_author_download_stats(self, author_id: str) -> dict:
        """单条 SQL 查询作者的 total/downloaded 统计"""
        with self._cursor() as cursor:
            return self._video_dao.get_author_download_stats(cursor, author_id)

    def get_author_video_type_stats(self, author_id: str) -> dict:
        """按 video_type 统计作者视频"""
        with self._cursor() as cursor:
            return self._video_dao.get_type_stats(cursor, author_id)

    def get_video(self, video_id: str) -> AuthorVideo:
        with self._cursor() as cursor:
            return self._video_dao.get_by_id(cursor, video_id)

    # ========== 下载任务操作 ==========

    def create_download_task(self, task: DownloadTask) -> bool:
        with self._cursor() as cursor:
            return self._task_dao.create(cursor, task)

    def get_download_task(self, task_id: str) -> DownloadTask:
        with self._cursor() as cursor:
            return self._task_dao.get_by_id(cursor, task_id)

    def get_download_task_by_video_id(self, video_id: str) -> DownloadTask:
        with self._cursor() as cursor:
            return self._task_dao.get_by_video_id(cursor, video_id)

    def update_download_task(self, task: DownloadTask) -> bool:
        with self._cursor() as cursor:
            return self._task_dao.update(cursor, task)

    def update_download_task_progress(
        self, task_id: str, progress: int, downloaded: int,
        total_size: int, speed: int, status: str = None
    ) -> bool:
        with self._cursor() as cursor:
            return self._task_dao.update_progress(
                cursor, task_id, progress, downloaded, total_size, speed, status
            )

    def update_download_task_status(
        self, task_id: str, status: str, error_msg: str = None, completed_at: str = None
    ) -> bool:
        with self._cursor() as cursor:
            return self._task_dao.update_status(cursor, task_id, status, error_msg, completed_at)

    def delete_download_task(self, task_id: str) -> bool:
        with self._cursor() as cursor:
            return self._task_dao.delete(cursor, task_id)

    def list_download_tasks(self, status: str = None, limit: int = 0, offset: int = 0):
        with self._cursor() as cursor:
            return self._task_dao.list_all(cursor, status, limit, offset)

    def clear_download_tasks(self) -> bool:
        with self._cursor() as cursor:
            return self._task_dao.clear_all(cursor)

    # ========== 恢复状态持久化 ==========

    def save_resume_state(self, task_id: str, state: str) -> bool:
        """保存恢复状态

        Args:
            task_id: 任务 ID
            state: 状态（resuming, completed, failed）
        """
        with self._cursor() as cursor:
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS resume_states (
                    task_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            cursor.execute(
                """INSERT OR REPLACE INTO resume_states (task_id, state, created_at)
                   VALUES (?, ?, datetime('now'))""",
                (task_id, state)
            )
            return True

    def get_pending_resume_states(self) -> list:
        """获取所有未完成的恢复状态"""
        with self._cursor() as cursor:
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS resume_states (
                    task_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            cursor.execute(
                "SELECT task_id, state FROM resume_states WHERE state = 'resuming'"
            )
            return [{"task_id": row[0], "state": row[1]} for row in cursor.fetchall()]

    def clear_resume_state(self, task_id: str) -> bool:
        """清除恢复状态"""
        with self._cursor() as cursor:
            cursor.execute(
                """CREATE TABLE IF NOT EXISTS resume_states (
                    task_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            cursor.execute("DELETE FROM resume_states WHERE task_id = ?", (task_id,))
            return True

    # ========== 任务完成记录 ==========

    def log_task_completion(
        self, video_id: str, author_id: str = "",
        username: str = "", title: str = "",
        cover_url: str = "", duration: int = 0,
        file_size: int = 0, completed_at: str = ""
    ) -> bool:
        """记录任务完成"""
        with self._cursor() as cursor:
            if not completed_at:
                from datetime import datetime
                completed_at = datetime.now().isoformat()
            return self._log_dao.insert_log(
                cursor, video_id, author_id, username, title,
                cover_url, duration, file_size, completed_at
            )

    def get_task_logs(self, limit: int = 50, offset: int = 0) -> list:
        """查询任务完成记录"""
        with self._cursor() as cursor:
            return self._log_dao.query_logs(cursor, limit, offset)

    def count_task_logs(self) -> int:
        """统计任务完成记录数量"""
        with self._cursor() as cursor:
            return self._log_dao.count_logs(cursor)

    def cleanup_task_logs(self, days: int = 7) -> int:
        """清理旧任务完成记录"""
        with self._cursor() as cursor:
            return self._log_dao.cleanup_old_logs(cursor, days)


# ========== 单例模式 ==========

_db_instance = None
_db_path = None


def get_database(db_path: str = None) -> Database:
    """获取数据库单例

    Args:
        db_path: 数据库路径（可选，默认使用 settings.app_root/data/app.db）

    Returns:
        Database 单例
    """
    global _db_instance, _db_path

    if db_path is None:
        from config.settings import settings
        db_path = str(settings.app_root / "data" / "app.db")

    if _db_instance is None or _db_path != db_path:
        if _db_instance is not None:
            _db_instance.close()
        _db_instance = Database(db_path)
        _db_path = db_path

    return _db_instance


# 全局单例实例，其他模块直接 import db 使用
db = get_database()
