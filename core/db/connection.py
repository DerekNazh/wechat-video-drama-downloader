"""统一 DB 连接管理（YZPQ-304）。

线程安全：check_same_thread=False + 线程本地连接。
建连即应用 WAL / foreign_keys / busy_timeout(5000)（与 core/db/schema 对齐）。
"""
from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager


class Connection:
    """按 db_path 持有线程本地连接的连接管理器。"""

    def __init__(self, db_path: str):
        self.db_path = str(db_path)
        self._local = threading.local()

    def _conn(self) -> sqlite3.Connection:
        if not hasattr(self._local, "conn"):
            conn = sqlite3.connect(
                self.db_path, timeout=5.0, check_same_thread=False
            )
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA foreign_keys = ON")
            conn.execute("PRAGMA busy_timeout = 5000")
            self._local.conn = conn
        return self._local.conn

    @contextmanager
    def cursor(self):
        conn = self._conn()
        cur = conn.cursor()
        try:
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def close(self):
        if hasattr(self._local, "conn"):
            self._local.conn.close()
            del self._local.conn
