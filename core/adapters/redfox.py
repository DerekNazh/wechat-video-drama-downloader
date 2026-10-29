"""红狐适配层（YZPQ-300）：5 端点 + 统一能力面。

红狐直链免解密。HTTP 由注入 http_fn，字段按映射表归一化，id 全 str。
"""
from __future__ import annotations

from .resilient_parse import safe_get


def _norm_user(raw: dict) -> dict:
    return {
        "username": raw.get("findName") or "",
        "nickname": raw.get("nickname") or "",
        "signature": raw.get("signature") or "",
        "head_url": raw.get("headUrl") or "",
        "cover_url": raw.get("coverImgUrl") or "",
    }


def _norm_work(raw: dict) -> dict:
    return {
        "video_id": str(raw.get("videoId", "")),
        "media_url": raw.get("videoUrl") or "",   # 直链免解密
        "cover": raw.get("cover") or "",
        "create_time": raw.get("createTime"),
        "description": raw.get("title") or "",
    }


class RedFoxAdapter:
    def __init__(self, http_fn, base_url: str, token: str):
        self.http = http_fn
        self.base = base_url.rstrip("/")
        self.token = token

    # --- 5 端点 ---
    def search_users(self, keyword: str):
        data = self.http("GET", f"{self.base}/search_users", params={"keyword": keyword})
        return [_norm_user(u) for u in safe_get(data, "users", default=[]) or []]

    def get_user_works(self, nickname: str):
        data = self.http("GET", f"{self.base}/get_user_works", params={"nickname": nickname})
        return [_norm_work(w) for w in safe_get(data, "works", default=[]) or []]

    def get_work(self, video_id: str):
        data = self.http("GET", f"{self.base}/get_work", params={"videoId": video_id})
        return _norm_work(data or {})

    def get_work_by_link(self, share_url: str):
        data = self.http("GET", f"{self.base}/get_work_by_link", params={"url": share_url})
        return {
            "export_id": str(safe_get(data, "exportId", default="")),
            "object_nonce_id": str(safe_get(data, "objectNonceId", default="")),
            "metadata": data or {},
        }

    def video_download(self, url: str):
        data = self.http("GET", f"{self.base}/sph/videoDownload", params={"url": url})
        return safe_get(data, "videoUrl", default="")

    # --- 统一能力面 ---
    def list_videos(self, author: str):
        return self.get_user_works(author)

    def get_detail(self, video_id: str):
        return self.get_work(video_id)

    def resolve_link(self, share_url: str):
        return self.get_work_by_link(share_url)

    def get_direct_url(self, url: str):
        return self.video_download(url)
