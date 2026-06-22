"""下载任务数据访问层"""

import logging
import sqlite3
from typing import List, Optional

from core.utils.database.crud.models import DownloadTask

logger = logging.getLogger("task_dao")


class TaskDAO:
    """下载任务 CRUD 操作"""

    def create(self, cursor, task: DownloadTask) -> bool:
        """创建下载任务"""
        try:
            cursor.execute(
                """
                INSERT INTO download_tasks (
                    task_id, video_id, url, title, filename, spec, suffix,
                    key, status, progress, downloaded, total_size, speed,
                    error_msg, created_at, updated_at, completed_at, video_type, create_time
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task.task_id,
                    task.video_id,
                    task.url,
                    task.title,
                    task.filename,
                    task.spec,
                    task.suffix,
                    task.key,
                    task.status,
                    task.progress,
                    task.downloaded,
                    task.total_size,
                    task.speed,
                    task.error_msg,
                    task.created_at,
                    task.updated_at,
                    task.completed_at,
                    task.video_type,
                    task.create_time,
                ),
            )
            logger.info(f"[task_dao] 创建任务: id={task.task_id}, video_id={task.video_id}, status={task.status}")
            return True
        except sqlite3.IntegrityError:
            logger.warning(f"[task_dao] 任务已存在: {task.task_id}")
            return False
        except Exception as e:
            logger.error(f"[task_dao] 创建异常: id={task.task_id}, error={e}")
            return False

    def get_by_id(self, cursor, task_id: str) -> Optional[DownloadTask]:
        """通过 task_id 获取任务"""
        try:
            cursor.execute(
                "SELECT * FROM download_tasks WHERE task_id = ?",
                (task_id,),
            )
            row = cursor.fetchone()
            return DownloadTask(*row) if row else None
        except Exception as e:
            logger.error(f"[get_by_id] 异常: {e}")
            return None

    def get_by_video_id(self, cursor, video_id: str) -> Optional[DownloadTask]:
        """通过视频ID获取任务"""
        try:
            cursor.execute(
                "SELECT * FROM download_tasks WHERE video_id = ?",
                (video_id,),
            )
            row = cursor.fetchone()
            return DownloadTask(*row) if row else None
        except Exception as e:
            logger.error(f"[get_by_video_id] 异常: {e}")
            return None

    def update(self, cursor, task: DownloadTask) -> bool:
        """更新任务"""
        cursor.execute(
            """
            UPDATE download_tasks SET
                video_id = ?, url = ?, title = ?, filename = ?,
                spec = ?, suffix = ?, key = ?, status = ?,
                progress = ?, downloaded = ?, total_size = ?,
                speed = ?, error_msg = ?, updated_at = ?, completed_at = ?
            WHERE task_id = ?
            """,
            (
                task.video_id,
                task.url,
                task.title,
                task.filename,
                task.spec,
                task.suffix,
                task.key,
                task.status,
                task.progress,
                task.downloaded,
                task.total_size,
                task.speed,
                task.error_msg,
                task.updated_at,
                task.completed_at,
                task.task_id,
            ),
        )
        return cursor.rowcount > 0

    def update_progress(
        self, cursor, task_id: str, progress: int, downloaded: int,
        total_size: int, speed: int, status: str = None
    ) -> bool:
        """更新下载进度"""
        if status:
            cursor.execute(
                """
                UPDATE download_tasks SET
                    progress = ?, downloaded = ?, total_size = ?,
                    speed = ?, status = ?, updated_at = datetime('now')
                WHERE task_id = ?
                """,
                (progress, downloaded, total_size, speed, status, task_id),
            )
        else:
            cursor.execute(
                """
                UPDATE download_tasks SET
                    progress = ?, downloaded = ?, total_size = ?,
                    speed = ?, updated_at = datetime('now')
                WHERE task_id = ?
                """,
                (progress, downloaded, total_size, speed, task_id),
            )
        return cursor.rowcount > 0

    def update_status(
        self, cursor, task_id: str, status: str,
        error_msg: str = None, completed_at: str = None
    ) -> bool:
        """更新任务状态"""
        cursor.execute(
            """
            UPDATE download_tasks SET
                status = ?, error_msg = ?, completed_at = ?,
                updated_at = datetime('now')
            WHERE task_id = ?
            """,
            (status, error_msg, completed_at, task_id),
        )
        logger.info(f"[task_dao] 更新状态: id={task_id}, status={status}")
        return cursor.rowcount > 0

    def delete(self, cursor, task_id: str) -> bool:
        """删除任务（幂等：不存在的任务视为已删除）"""
        cursor.execute(
            "DELETE FROM download_tasks WHERE task_id = ?",
            (task_id,),
        )
        logger.info(f"[task_dao] 删除任务: id={task_id}, affected={cursor.rowcount}")
        return True

    def list_all(
        self, cursor, status: str = None, limit: int = 0, offset: int = 0
    ) -> List[DownloadTask]:
        """列表任务"""
        try:
            if limit > 0:
                if status:
                    cursor.execute(
                        """
                        SELECT * FROM download_tasks
                        WHERE status = ?
                        ORDER BY created_at DESC
                        LIMIT ? OFFSET ?
                        """,
                        (status, limit, offset),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT * FROM download_tasks
                        ORDER BY created_at DESC
                        LIMIT ? OFFSET ?
                        """,
                        (limit, offset),
                    )
            else:
                if status:
                    cursor.execute(
                        """
                        SELECT * FROM download_tasks
                        WHERE status = ?
                        ORDER BY created_at DESC
                        """,
                        (status,),
                    )
                else:
                    cursor.execute(
                        """
                        SELECT * FROM download_tasks
                        ORDER BY created_at DESC
                        """
                    )
            return [DownloadTask(*row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"[list_all] 异常: {e}")
            return []

    def clear_all(self, cursor) -> bool:
        """清空所有任务"""
        cursor.execute("DELETE FROM download_tasks")
        return True
