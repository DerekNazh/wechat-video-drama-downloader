"""自动更新（YZPQ-315）：检查 latest.json + 版本比较 + sha256 校验。

网络下载由注入的 fetcher，失败静默不阻塞自用。纯逻辑可单测。
"""
from __future__ import annotations

import hashlib

UPDATE_URL = "https://lemon-kami-artifacts.oss-cn-beijing.aliyuncs.com/haoxia/updates/latest.json"


def parse_ver(v: str) -> tuple:
    return tuple(int(x) for x in v.lstrip("v").split("."))


def has_update(current: str, latest: str) -> bool:
    return parse_ver(latest) > parse_ver(current)


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def verify(data: bytes, expected_sha256: str) -> bool:
    return sha256_hex(data) == expected_sha256.lower()


class Updater:
    def __init__(self, fetcher, current_version: str, timeout: float = 10.0):
        self.fetcher = fetcher          # fetcher(url, timeout)->bytes
        self.current = current_version
        self.timeout = timeout

    def check(self) -> dict | None:
        """返回 {version, url, sha256}；无更新或失败返回 None（静默）。"""
        try:
            import json
            raw = self.fetcher(UPDATE_URL, self.timeout)
            meta = json.loads(raw.decode("utf-8"))
        except Exception:
            return None
        if not has_update(self.current, meta.get("version", self.current)):
            return None
        return {
            "version": meta["version"], "url": meta["url"],
            "sha256": meta.get("sha256", ""),
        }

    def download_and_verify(self, info: dict) -> bytes | None:
        try:
            data = self.fetcher(info["url"], self.timeout)
        except Exception:
            return None
        if not verify(data, info["sha256"]):
            return None  # sha256 不匹配拒绝安装
        return data
