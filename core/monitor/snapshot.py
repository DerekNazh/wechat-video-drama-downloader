"""监控器改造（YZPQ-317）：打开界面0成本快照 + 标星作者2次/天兜底 + 首页增量对比。

S1 新纯逻辑模块，不动 legacy monitor.py（仍走旧 DB）。数据拉取由注入 loader，
这里只做调度判断与增量比对，可单测。
"""
from __future__ import annotations

import time

STARRED_INTERVAL = 12 * 3600  # 标星作者每天兜底 2 次 = 12h/次


def new_items(old_list: list, new_list: list) -> list:
    """首页增量：new 中 create_time 比 old 最大值更新的项。空 old 视为全新。"""
    if not old_list:
        return list(new_list)
    max_old = max((it.get("create_time") or 0) for it in old_list)
    return [it for it in new_list if (it.get("create_time") or 0) > max_old]


def snapshot_on_open() -> bool:
    """打开界面即 0 成本快照（读本地缓存不发请求），恒可做。"""
    return True


def should_refresh_starred(last_ts: float, now: float | None = None) -> bool:
    """距上次 >12h 才拉标星作者兜底。"""
    now = time.time() if now is None else now
    return (now - last_ts) >= STARRED_INTERVAL


class SnapshotMonitor:
    def __init__(self, loader, now_fn=None):
        self.loader = loader   # loader(username, page=1)->[items]
        self.now = now_fn or time.time

    def on_open_snapshot(self, username: str):
        return self.loader(username, page=1)

    def incremental(self, username: str, old_list: list):
        return new_items(old_list, self.loader(username, page=1))

    def starred_tick(self, username: str, last_ts: float):
        if not should_refresh_starred(last_ts, self.now()):
            return None
        return self.loader(username, page=1)
