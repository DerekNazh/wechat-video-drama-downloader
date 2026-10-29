"""单实例锁 + 优雅退出落 interrupted（YZPQ-312）。

Windows 用进程级文件锁（msvcrt/portalocker 思路，这里用 OS 文件锁）。
退出时把所有 downloading/paused 任务落 interrupted，供下次恢复探测。
"""
from __future__ import annotations

import os
from typing import Optional


class SingleInstance:
    """基于锁文件的单实例；第二个实例 acquire 失败即被拦截。"""

    def __init__(self, lock_path: str):
        self.lock_path = lock_path
        self._fh: Optional[int] = None

    def acquire(self) -> bool:
        try:
            self._fh = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_RDWR)
            os.write(self._fh, str(os.getpid()).encode())
            return True
        except FileExistsError:
            return False

    def release(self):
        if self._fh is not None:
            os.close(self._fh)
            self._fh = None
        try:
            os.remove(self.lock_path)
        except OSError:
            pass


def on_graceful_shutdown(running_tasks: list[str], mark_interrupted) -> int:
    """退出事件：把在跑的任务落 interrupted，返回落库条数。mark_interrupted 由调用方注入。"""
    n = 0
    for tid in running_tasks:
        mark_interrupted(tid)
        n += 1
    return n


def key_invalid_hint(status: int) -> Optional[str]:
    """401/402 → 提示检查 Key/余额；其余返回 None。"""
    if status in (401, 402):
        return "Key 失效或余额不足，请检查 API Key 与账户余额"
    return None
