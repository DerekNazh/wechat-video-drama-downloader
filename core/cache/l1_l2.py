"""L1+L2 缓存层（YZPQ-305）。

- L1 channel_alias：短链/别名 -> channel_id，TTL 365 天，命中后由下游 verify 兜底，
  失效则回源重取。
- L2 author_list_snapshot：作者视频列表快照，key=username|video_type|page，
  payload 原样存 JSON，软 TTL 120min 重取，硬上限 48h 绝不返回更旧数据。
- 合集列表顺风车：与作者列表同 key 体系、同取同存同过期（v1.55）。
- get_or_fetch 统一门面。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Callable, Optional

from core.db.connection import Connection
from core.db.dao import DAO

L1_TTL_DAYS = 365
L2_TTL_MIN = 120          # 软过期：到点重取
L2_HARD_CAP_HOURS = 48    # 硬上限：超过则视为脏，强制重取


def _now() -> datetime:
    return datetime.now()


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _parse(s: Optional[str]) -> Optional[datetime]:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        return None


class L1ChannelAlias:
    """短链/别名 -> channel_id 缓存。"""

    def __init__(self, conn: Connection):
        self.dao = DAO(conn, "channel_alias", "alias")

    def get(self, alias: str, verify: Optional[Callable[[str], bool]] = None
            ) -> Optional[str]:
        row = self.dao.get(alias)
        if not row:
            return None
        fetched = _parse(row.get("resolved_at"))
        if fetched and (_now() - fetched) > timedelta(days=L1_TTL_DAYS):
            return None  # 惰性过期
        channel_id = row.get("channel_id")
        if channel_id and verify is not None and not verify(channel_id):
            return None  # 下游验证兜底失败，回源
        return channel_id

    def put(self, alias: str, channel_id: str) -> None:
        self.dao.create({"alias": alias, "channel_id": channel_id,
                         "resolved_at": _iso(_now())})


class L2ListSnapshot:
    """作者视频列表 / 合集列表快照（顺风车共用 key 体系）。"""

    def __init__(self, conn: Connection):
        self.dao = DAO(conn, "author_list_snapshot", "author_id")

    def _key(self, username: str, video_type: str, page: str) -> str:
        return f"{username}|{video_type}|{page}"

    def get(self, username: str, video_type: str, page: str
            ) -> Optional[tuple[Any, bool]]:
        """返回 (data, fresh)；fresh=True 软 TTL 内可用。"""
        row = self.dao.get(self._key(username, video_type, page))
        if not row:
            return None
        fetched = _parse(row.get("fetched_at"))
        if not fetched:
            return None
        age = _now() - fetched
        if age > timedelta(hours=L2_HARD_CAP_HOURS):
            return None  # 超硬上限，绝不返回
        fresh = age <= timedelta(minutes=L2_TTL_MIN)
        try:
            return json.loads(row["data"]), fresh
        except (ValueError, TypeError):
            return None

    def put(self, username: str, video_type: str, page: str, data: Any) -> None:
        self.dao.create({
            "author_id": self._key(username, video_type, page),
            "snapshot_key": video_type,
            "data": json.dumps(data, ensure_ascii=False),
            "fetched_at": _iso(_now()),
        })

    def get_or_fetch(self, username: str, video_type: str, page: str,
                     fetch: Callable[[], Any]) -> Any:
        """统一门面：软 TTL 内直接命中；否则回源 fetch 并落库。

        合集顺风车：合集列表与作者列表共用本方法（video_type 传 'collection' 即可
        同取同存同过期）。
        """
        hit = self.get(username, video_type, page)
        if hit is not None and hit[1]:
            return hit[0]
        data = fetch()
        self.put(username, video_type, page, data)
        return data
