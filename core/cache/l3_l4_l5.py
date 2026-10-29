"""L3+L4+L5 缓存与空确认（YZPQ-306）。

- L3 详情窗口：decode_key 不长期缓存；media URL 出数前 24h 安全窗口，过期即主动刷新。
- L4 搜索缓存：search_cache 表，键=q|exact|page；有结果 TTL 24h，空结果 TTL 1h。
- L5 下载去重：权威源=文件系统，DB 仅作三态缓存（downloaded/missing/unknown）+ 幂等锁。
- 空确认标记：补拉结果为空 -> 7 天内免补。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from core.db.connection import Connection
from core.db.dao import DAO

MEDIA_WINDOW_HOURS = 24
SEARCH_TTL_HIT_HOURS = 24
SEARCH_TTL_EMPTY_HOURS = 1
EMPTY_CONFIRM_DAYS = 7


def _now() -> datetime:
    return datetime.now()


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _parse(s: Optional[str]) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(s) if s else None
    except ValueError:
        return None


class L3MediaWindow:
    """详情窗口：media URL 在安全窗口内才信任，否则主动刷新（decode_key 不落库）。"""

    @staticmethod
    def is_fresh(fetched_at: Optional[str]) -> bool:
        dt = _parse(fetched_at)
        return bool(dt and (_now() - dt) <= timedelta(hours=MEDIA_WINDOW_HOURS))

    def ensure_valid_url(self, url: Optional[str], fetched_at: Optional[str],
                         refresh: Callable[[], tuple[str, str]]
                         ) -> tuple[str, str]:
        """返回 (url, fetched_at)；窗口过期或无 url 则调 refresh 重取。"""
        if url and self.is_fresh(fetched_at):
            return url, fetched_at or _iso(_now())
        return refresh()  # -> (new_url, new_fetched_at)


class L4SearchCache:
    """搜索缓存：命中 24h，空结果 1h。"""

    def __init__(self, conn: Connection):
        self.dao = DAO(conn, "search_cache", "cache_key")

    def _key(self, q: str, exact: bool, page: str) -> str:
        return f"{q}|{int(exact)}|{page}"

    def get(self, q: str, exact: bool, page: str) -> Optional[Any]:
        row = self.dao.get(self._key(q, exact, page))
        if not row:
            return None
        exp = _parse(row.get("expire_at"))
        if exp and _now() > exp:
            return None
        try:
            return json.loads(row["data"])
        except (ValueError, TypeError):
            return None

    def put(self, q: str, exact: bool, page: str, data: Any) -> None:
        is_empty = (data == [] or data == {} or data is None)
        ttl = SEARCH_TTL_EMPTY_HOURS if is_empty else SEARCH_TTL_HIT_HOURS
        self.dao.create({
            "cache_key": self._key(q, exact, page),
            "data": json.dumps(data, ensure_ascii=False),
            "expire_at": _iso(_now() + timedelta(hours=ttl)),
            "fetched_at": _iso(_now()),
        })


class L5DownloadDedup:
    """下载去重：权威源=文件系统，DB 三态缓存 + 幂等锁。"""

    def __init__(self, conn: Connection):
        self.dao = DAO(conn, "author_videos", "video_id")

    def state(self, video_id: str, file_exists: Callable[[], bool]) -> str:
        """三态：downloaded / missing / unknown。文件系统为准，DB 仅缓存。"""
        if file_exists():
            row = self.dao.get(video_id)
            if not row or row.get("is_downloaded") != 1:
                self.dao.update(video_id, {"is_downloaded": 1})
            return "downloaded"
        # 文件不存在 -> DB 标记清掉（缓存失效）
        row = self.dao.get(video_id)
        if row and row.get("is_downloaded") == 1:
            self.dao.update(video_id, {"is_downloaded": 0})
        return "missing"

    def claim(self, video_id: str) -> bool:
        """幂等锁：并发下只有一个 claim 成功（已下载则拒绝重复下载）。"""
        row = self.dao.get(video_id)
        if row and row.get("is_downloaded") == 1:
            return False  # 已下载，幂等拒绝
        self.dao.update(video_id, {"is_downloaded": 1})
        return True


class EmptyConfirm:
    """补拉空结果 -> 7 天免补（存 search_cache 前缀 empty:）。"""

    def __init__(self, conn: Connection):
        self.dao = DAO(conn, "search_cache", "cache_key")

    def mark_empty(self, scope_key: str) -> None:
        self.dao.create({
            "cache_key": f"empty:{scope_key}",
            "data": "[]",
            "expire_at": _iso(_now() + timedelta(days=EMPTY_CONFIRM_DAYS)),
            "fetched_at": _iso(_now()),
        })

    def is_skippable(self, scope_key: str) -> bool:
        row = self.dao.get(f"empty:{scope_key}")
        if not row:
            return False
        exp = _parse(row.get("expire_at"))
        return bool(exp and _now() <= exp)
