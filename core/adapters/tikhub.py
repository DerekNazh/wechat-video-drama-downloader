"""TikHub 适配层（YZPQ-301）：raw=false 结构按映射表归一化。

HTTP 调用由注入的 http_fn 完成，这里只做字段映射与类型收敛，便于单测。
所有 id 类字段强制 str。
"""
from __future__ import annotations

from .resilient_parse import safe_get


def normalize_video(raw: dict) -> dict:
    """videos[]/lives[]/合集内视频 同构归一化。"""
    media = raw.get("media") or {}
    stats = raw.get("statistics") or {}
    return {
        "video_id": str(raw.get("video_id", "")),
        "create_time": raw.get("create_time"),
        "description": raw.get("caption") or "",
        "cover": raw.get("cover") or "",
        "share_url": raw.get("share_url") or "",
        "export_id": str(raw.get("export_id", "")),
        "object_nonce_id": str(raw.get("object_nonce_id", "")),
        "media_url": media.get("full_url") or "",
        "decode_key": media.get("decode_key") or "",
        "like_count": stats.get("like_count"),
        "comment_count": stats.get("comment_count"),
        "read_count": stats.get("read_count"),
        "forward_count": stats.get("forward_count"),
        "fav_count": stats.get("fav_count"),
    }


def normalize_collection(raw: dict) -> dict:
    return {
        "collection_id": str(raw.get("topic_id", "")),
        "title": raw.get("topic") or "",
        "video_count": raw.get("video_count", 0),
    }


def normalize_comment(raw: dict) -> dict:
    return {
        "comment_id": str(raw.get("comment_id", "")),
        "nickname": raw.get("nickname") or "",
        "username": raw.get("username") or "",
        "head_url": raw.get("head_url") or "",
        "content": raw.get("content") or "",
        "like_count": raw.get("like_count", 0),
        "reply_count": raw.get("reply_count", 0),
        "create_time": raw.get("create_time"),
        "ip_region": raw.get("ip_region") or "",
    }


def normalize_profile(raw: dict) -> dict:
    return {
        "follower_count": raw.get("follower_count"),
        "following_count": raw.get("following_count"),
        "like_total": raw.get("like_total"),
    }


class TikHubAdapter:
    def __init__(self, http_fn, base_url: str, token: str):
        self.http = http_fn
        self.base = base_url.rstrip("/")
        self.token = token

    def list_videos(self, username: str):
        data = self.http("GET", f"{self.base}/aweme/v1/web/aweme/post/",
                         params={"username": username, "raw": "false"})
        return [normalize_video(v) for v in safe_get(data, "videos", default=[]) or []]

    def collections(self, username: str):
        data = self.http("GET", f"{self.base}/web/collection/list/",
                         params={"username": username})
        return [normalize_collection(c) for c in safe_get(data, "collections", default=[]) or []]

    def comments(self, object_id: str):
        data = self.http("GET", f"{self.base}/web/comment/list/",
                         params={"object_id": object_id, "raw": "true"})
        return [normalize_comment(c) for c in safe_get(data, "comments", default=[]) or []]

    def profile(self, username: str):
        data = self.http("GET", f"{self.base}/web/user/profile/",
                         params={"username": username})
        return normalize_profile(data or {})
