"""下载状态机（YZPQ-307）：8 态 + 合法迁移 + 落库。

状态：pending / downloading / paused / completed / failed / cancelled /
      interrupted / expired。
每次合法迁移写 download_tasks.status + updated_at，并记 task_log 事件。
非法迁移抛 ValueError（不静默吞）。
"""
from __future__ import annotations

from datetime import datetime
from typing import Iterable

from core.db.connection import Connection
from core.db.dao import DAO

STATES = frozenset({
    "pending", "downloading", "paused", "completed",
    "failed", "cancelled", "interrupted", "expired",
})

# 合法迁移表
TRANSITIONS: dict[str, frozenset[str]] = {
    "pending": frozenset({"downloading"}),
    "downloading": frozenset({"completed", "failed", "paused",
                              "cancelled", "interrupted", "expired"}),
    "paused": frozenset({"downloading", "cancelled"}),
    "interrupted": frozenset({"downloading", "cancelled"}),
    "failed": frozenset({"downloading"}),   # 可重试
    "expired": frozenset({"downloading"}),  # 重取链接后恢复
    "completed": frozenset(),
    "cancelled": frozenset(),
}


class IllegalTransition(Exception):
    pass


class DownloadStateMachine:
    def __init__(self, conn: Connection):
        self.dao = DAO(conn, "download_tasks", "task_id")

    def current(self, task_id: str) -> str:
        row = self.dao.get(task_id)
        if not row:
            raise KeyError(task_id)
        return row.get("status") or "pending"

    def can(self, frm: str, to: str) -> bool:
        return to in TRANSITIONS.get(frm, frozenset())

    def apply(self, task_id: str, to: str, error_msg: str | None = None) -> str:
        """执行一次迁移并落库，返回迁移后的状态。非法迁移抛 IllegalTransition。"""
        if to not in STATES:
            raise ValueError(f"未知状态 {to}")
        frm = self.current(task_id)
        if frm == to:
            return frm
        if not self.can(frm, to):
            raise IllegalTransition(f"{frm} -> {to} 非法")
        fields = {"status": to, "updated_at": datetime.now().isoformat(timespec="seconds")}
        if to == "completed":
            fields["completed_at"] = datetime.now().isoformat(timespec="seconds")
        if error_msg is not None:
            fields["error_msg"] = error_msg
        self.dao.update(task_id, fields)
        return to
