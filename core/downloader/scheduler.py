"""下载并发调度（YZPQ-309）：多任务队列互不阻塞 + idle 5s 断开 + 磁盘预检。

调度本身是纯逻辑队列，真实 IO 由执行器注入，便于单测。
"""
from __future__ import annotations

import shutil
import time
from collections import deque
from typing import Callable, Optional

IDLE_TIMEOUT_SEC = 5
MIN_DISK_FREE_BYTES = 50 * 1024 * 1024  # 50MB 底线


def disk_precheck(path: str, need_bytes: int,
                  free_fn: Callable[[str], int] = shutil.disk_usage) -> bool:
    """磁盘预检：剩余空间 >= need_bytes + 底线。不足返回 False 拦截。"""
    try:
        free = free_fn(path).free
    except Exception:
        return True  # 探测不到不硬拦
    return free >= need_bytes + MIN_DISK_FREE_BYTES


class DownloadScheduler:
    """简单并发队列：最多 concurrency 个任务在跑，其余排队，互不阻塞。"""

    def __init__(self, concurrency: int = 3,
                 now: Callable[[], float] = time.monotonic):
        self.concurrency = max(1, concurrency)
        self.queue: deque = deque()
        self.running: dict[str, float] = {}  # task_id -> last_active_ts
        self._now = now

    def submit(self, task_id: str) -> bool:
        if task_id in self.running:
            return False
        self.queue.append(task_id)
        self._drain()
        return True

    def _drain(self):
        while len(self.running) < self.concurrency and self.queue:
            tid = self.queue.popleft()
            self.running[tid] = self._now()

    def touch(self, task_id: str):
        if task_id in self.running:
            self.running[task_id] = self._now()

    def done(self, task_id: str):
        self.running.pop(task_id, None)
        self._drain()

    def idle_expired(self) -> list[str]:
        """返回空闲超过 IDLE_TIMEOUT_SEC 的任务（调用方据此断开）。"""
        now = self._now()
        return [tid for tid, ts in list(self.running.items())
                if now - ts >= IDLE_TIMEOUT_SEC]
