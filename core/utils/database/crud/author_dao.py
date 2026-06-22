"""作者数据访问层"""

import logging
import sqlite3
from typing import List, Optional

from core.utils.database.crud.models import Author

logger = logging.getLogger("author_dao")


class AuthorDAO:
    """作者 CRUD 操作"""

    def create(self, cursor, author: Author) -> bool:
        """创建作者"""
        try:
            cursor.execute(
                """
                INSERT INTO authors (
                    id, source_author_id, name, tag, bio,
                    avatar_url, cover_img_url, created_at, updated_at,
                    latest_publish_date
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    author.id,
                    author.source_author_id,
                    author.name,
                    author.tag,
                    author.bio,
                    author.avatar_url,
                    author.cover_img_url,
                    author.created_at,
                    author.updated_at,
                    author.latest_publish_date,
                ),
            )
            return True
        except sqlite3.IntegrityError:
            logger.warning(f"[create] 作者已存在: {author.id}")
            return False
        except Exception as e:
            logger.error(f"[create] 异常: {e}")
            return False

    def get_by_id(self, cursor, author_id: str) -> Optional[Author]:
        """通过 ID 获取作者"""
        try:
            cursor.execute(
                "SELECT * FROM authors WHERE id = ?",
                (author_id,),
            )
            row = cursor.fetchone()
            return Author(*row) if row else None
        except Exception as e:
            logger.error(f"[get_by_id] 异常: {e}")
            return None

    def get_by_source_id(self, cursor, source_author_id: str) -> Optional[Author]:
        """通过来源ID获取作者"""
        try:
            cursor.execute(
                "SELECT * FROM authors WHERE source_author_id = ?",
                (source_author_id,),
            )
            row = cursor.fetchone()
            return Author(*row) if row else None
        except Exception as e:
            logger.error(f"[get_by_source_id] 异常: {e}")
            return None

    def get_by_name(self, cursor, name: str) -> Optional[Author]:
        """通过名称获取作者"""
        try:
            cursor.execute(
                "SELECT * FROM authors WHERE name = ?",
                (name,),
            )
            row = cursor.fetchone()
            return Author(*row) if row else None
        except Exception as e:
            logger.error(f"[get_by_name] 异常: {e}")
            return None

    def update(self, cursor, author: Author) -> bool:
        """更新作者（Upsert：不存在则创建）"""
        cursor.execute(
            """
            UPDATE authors SET
                source_author_id = ?, name = ?, tag = ?, bio = ?,
                avatar_url = ?, cover_img_url = ?, updated_at = ?
            WHERE id = ?
            """,
            (
                author.source_author_id,
                author.name,
                author.tag,
                author.bio,
                author.avatar_url,
                author.cover_img_url,
                author.updated_at,
                author.id,
            ),
        )
        if cursor.rowcount > 0:
            return True
        cursor.execute(
            """
            INSERT INTO authors (
                id, source_author_id, name, tag, bio,
                avatar_url, cover_img_url, created_at, updated_at,
                latest_publish_date
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                author.id,
                author.source_author_id,
                author.name,
                author.tag,
                author.bio,
                author.avatar_url,
                author.cover_img_url,
                author.created_at,
                author.updated_at,
                author.latest_publish_date,
            ),
        )
        return True

    def update_latest_publish_date(self, cursor, author_id: str, latest_publish_date: str) -> bool:
        """更新作者最新视频发布时间"""
        cursor.execute(
            "UPDATE authors SET latest_publish_date = ? WHERE id = ?",
            (latest_publish_date, author_id),
        )
        return cursor.rowcount > 0

    def delete(self, cursor, author_id: str) -> bool:
        """删除作者（幂等：不存在的作者视为已删除）"""
        cursor.execute(
            "DELETE FROM authors WHERE id = ?",
            (author_id,),
        )
        return True

    def list_all(self, cursor, limit: int = 0, offset: int = 0) -> List[Author]:
        """列表作者"""
        try:
            if limit > 0:
                cursor.execute(
                    "SELECT * FROM authors ORDER BY created_at DESC LIMIT ? OFFSET ?",
                    (limit, offset),
                )
            else:
                cursor.execute(
                    "SELECT * FROM authors ORDER BY created_at DESC",
                )
            return [Author(*row) for row in cursor.fetchall()]
        except Exception as e:
            logger.error(f"[list_all] 异常: {e}")
            return []
