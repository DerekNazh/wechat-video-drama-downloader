"""视频数据访问层"""

import logging
import sqlite3
from typing import List, Optional

from core.utils.database.crud.models import AuthorVideo

logger = logging.getLogger("video_dao")


class VideoDAO:
    """视频 CRUD 操作"""

    def create(self, cursor, video: AuthorVideo) -> bool:
        """创建视频"""
        try:
            cursor.execute(
                """
                INSERT INTO author_videos (
                    video_id, author_id, title, object_nonce_id,
                    url, spec, file_size, cover_url, decode_key,
                    author_avatar, duration, create_time,
                    is_downloaded, download_path, downloaded_at, video_type
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    video.video_id,
                    video.author_id,
                    video.title,
                    video.object_nonce_id,
                    video.url,
                    video.spec,
                    video.file_size,
                    video.cover_url,
                    video.decode_key,
                    video.author_avatar,
                    video.duration,
                    video.create_time,
                    video.is_downloaded,
                    video.download_path,
                    video.downloaded_at,
                    video.video_type,
                ),
            )
            return True
        except sqlite3.IntegrityError:
            logger.warning(f"[create] 视频已存在: {video.video_id}")
            return False
        except Exception as e:
            logger.error(f"[create] 异常: {e}")
            return False

    def get_by_id(self, cursor, video_id: str) -> Optional[AuthorVideo]:
        """通过 video_id 获取视频"""
        try:
            cursor.execute(
                "SELECT * FROM author_videos WHERE video_id = ?",
                (video_id,),
            )
            row = cursor.fetchone()
            return AuthorVideo(*row) if row else None
        except Exception as e:
            logger.error(f"[get_by_id] 异常: {e}")
            return None

    def list_by_author(
        self, cursor, author_id: str, limit: int = 0, offset: int = 0
    ) -> List[AuthorVideo]:
        """列表作者视频"""
        try:
            if limit > 0:
                cursor.execute(
                    """
                    SELECT * FROM author_videos
                    WHERE author_id = ?
                    ORDER BY create_time DESC
                    LIMIT ? OFFSET ?
                    """,
                    (author_id, limit, offset),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM author_videos
                    WHERE author_id = ?
                    ORDER BY create_time DESC
                    """,
                    (author_id,),
                )
            return [AuthorVideo(*row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"[list_by_author] 异常: {e}")
            return []

    def list_by_author_and_type(
        self, cursor, author_id: str, video_type: str, limit: int = 0, offset: int = 0
    ) -> List[AuthorVideo]:
        """按 video_type 列表作者视频"""
        try:
            if limit > 0:
                cursor.execute(
                    """
                    SELECT * FROM author_videos
                    WHERE author_id = ? AND video_type = ?
                    ORDER BY create_time DESC
                    LIMIT ? OFFSET ?
                    """,
                    (author_id, video_type, limit, offset),
                )
            else:
                cursor.execute(
                    """
                    SELECT * FROM author_videos
                    WHERE author_id = ? AND video_type = ?
                    ORDER BY create_time DESC
                    """,
                    (author_id, video_type),
                )
            return [AuthorVideo(*row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"[list_by_author_and_type] 异常: {e}")
            return []

    def list_undownloaded(self, cursor, limit: int = 10) -> List[AuthorVideo]:
        """查询未下载的视频（按发布时间从晚到早）"""
        try:
            cursor.execute(
                """
                SELECT * FROM author_videos
                WHERE is_downloaded = 0
                ORDER BY create_time DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [AuthorVideo(*row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"[list_undownloaded] 异常: {e}")
            return []

    def delete(self, cursor, video_id: str) -> bool:
        """删除视频（幂等：不存在的视频视为已删除）"""
        cursor.execute(
            "DELETE FROM author_videos WHERE video_id = ?",
            (video_id,),
        )
        return True

    def update_downloaded(self, cursor, video_id: str, download_path: str) -> bool:
        """标记视频为已下载"""
        from datetime import datetime
        now = datetime.now().isoformat()
        cursor.execute(
            """
            UPDATE author_videos
            SET is_downloaded = 1, download_path = ?, downloaded_at = ?
            WHERE video_id = ?
            """,
            (download_path, now, video_id),
        )
        return cursor.rowcount > 0

    def reset_downloaded(self, cursor, video_id: str) -> bool:
        """重置视频为未下载"""
        cursor.execute(
            """
            UPDATE author_videos
            SET is_downloaded = 0, download_path = '', downloaded_at = NULL
            WHERE video_id = ?
            """,
            (video_id,),
        )
        return cursor.rowcount > 0

    def update_url(self, cursor, video_id: str, new_url: str) -> bool:
        """更新视频 URL"""
        cursor.execute(
            "UPDATE author_videos SET url = ? WHERE video_id = ?",
            (new_url, video_id),
        )
        return cursor.rowcount > 0

    def count_today(self, cursor) -> int:
        """统计今日新增视频数"""
        try:
            cursor.execute(
                "SELECT COUNT(*) FROM author_videos WHERE date(create_time) = date('now', 'localtime')"
            )
            row = cursor.fetchone()
            return row[0] if row else 0
        except Exception as e:
            logger.error(f"[count_today] 异常: {e}")
            return 0

    def count_downloaded_today(self, cursor) -> int:
        """统计今日已下载视频数（基于下载完成时间，非视频发布时间）"""
        try:
            cursor.execute(
                "SELECT COUNT(*) FROM author_videos WHERE date(downloaded_at) = date('now', 'localtime')"
            )
            row = cursor.fetchone()
            return row[0] if row else 0
        except Exception as e:
            logger.error(f"[count_downloaded_today] 异常: {e}")
            return 0

    def count_total(self, cursor) -> int:
        """统计总视频数"""
        try:
            cursor.execute("SELECT COUNT(*) FROM author_videos")
            row = cursor.fetchone()
            return row[0] if row else 0
        except Exception as e:
            logger.error(f"[count_total] 异常: {e}")
            return 0

    def get_author_download_stats(self, cursor, author_id: str) -> dict:
        """单条 SQL 查询作者的 total/downloaded 统计"""
        try:
            cursor.execute(
                "SELECT COUNT(*) as total, SUM(is_downloaded) as downloaded FROM author_videos WHERE author_id = ?",
                (author_id,),
            )
            row = cursor.fetchone()
            if row and row[0] > 0:
                return {"total": row[0], "downloaded": int(row[1] or 0)}
            return {"total": 0, "downloaded": 0}
        except Exception as e:
            logger.error(f"[get_author_download_stats] 异常: {e}")
            return {"total": 0, "downloaded": 0}

    def get_type_stats(self, cursor, author_id: str) -> dict:
        """按 video_type 统计作者视频"""
        try:
            cursor.execute(
                "SELECT video_type, COUNT(*) as cnt, "
                "SUM(CASE WHEN is_downloaded=1 THEN 1 ELSE 0 END) as dl "
                "FROM author_videos WHERE author_id=? GROUP BY video_type",
                (author_id,),
            )
            result = {
                "short_video_count": 0,
                "replay_count": 0,
                "short_video_downloaded": 0,
                "replay_downloaded": 0,
            }
            for row in cursor.fetchall():
                vtype, cnt, dl = row
                if vtype == "live_replay":
                    result["replay_count"] = cnt
                    result["replay_downloaded"] = dl
                else:
                    result["short_video_count"] = cnt
                    result["short_video_downloaded"] = dl
            return result
        except Exception as e:
            logger.error(f"[get_type_stats] 异常: {e}")
            return {
                "short_video_count": 0,
                "replay_count": 0,
                "short_video_downloaded": 0,
                "replay_downloaded": 0,
            }
