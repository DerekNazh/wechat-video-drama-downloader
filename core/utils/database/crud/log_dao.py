"""任务完成记录数据访问层"""

import logging
from typing import List, Dict

logger = logging.getLogger("log_dao")


class LogDAO:
    """任务完成记录 CRUD 操作"""

    def insert_log(
        self, cursor, video_id: str, author_id: str = "",
        username: str = "", title: str = "",
        cover_url: str = "", duration: int = 0,
        file_size: int = 0, completed_at: str = ""
    ) -> bool:
        """插入任务完成记录"""
        try:
            cursor.execute(
                """
                INSERT OR IGNORE INTO task_log
                (video_id, author_id, username, title, cover_url, duration, file_size, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (video_id, author_id, username, title, cover_url, duration, file_size, completed_at),
            )
            return True
        except Exception as e:
            logger.error(f"[insert_log] 异常: video_id={video_id}, error={e}")
            return False

    def query_logs(self, cursor, limit: int = 50, offset: int = 0) -> List[Dict]:
        """查询任务完成记录"""
        try:
            cursor.execute(
                """
                SELECT
                    tl.id, tl.video_id, tl.author_id, tl.username,
                    COALESCE(a.name, '') as author_name,
                    tl.title, tl.cover_url, tl.duration, tl.file_size, tl.completed_at
                FROM task_log tl
                LEFT JOIN authors a ON tl.author_id = a.id
                ORDER BY tl.completed_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
            columns = [
                'id', 'video_id', 'author_id', 'username', 'author_name',
                'title', 'cover_url', 'duration', 'file_size', 'completed_at'
            ]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"[query_logs] 异常: {e}")
            return []

    def count_logs(self, cursor) -> int:
        """统计任务完成记录数量"""
        try:
            cursor.execute("SELECT COUNT(*) FROM task_log")
            return cursor.fetchone()[0]
        except Exception as e:
            logger.error(f"[count_logs] 异常: {e}")
            return 0

    def cleanup_old_logs(self, cursor, days: int = 7) -> int:
        """清理旧记录"""
        try:
            cursor.execute(
                """
                DELETE FROM task_log
                WHERE created_at < datetime('now', ? || ' days', 'localtime')
                """,
                (str(-days),),
            )
            affected = cursor.rowcount
            logger.info(f"[cleanup_old_logs] 清理 {affected} 条 {days} 天前的记录")
            return affected
        except Exception as e:
            logger.error(f"[cleanup_old_logs] 异常: {e}")
            return 0
