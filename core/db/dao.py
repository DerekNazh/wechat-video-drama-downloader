"""统一 DAO 三件（YZPQ-304）：create / get / update。

通用实现：表名 + 主键列 + 数据 dict。所有 id / 大整数入参按 str 落库（TEXT），
出参读出即字符串，避免 JS Number 53 位舍入。
"""
from __future__ import annotations

import sqlite3
from typing import Any, Optional

from core.db.connection import Connection


class DAO:
    def __init__(self, conn: Connection, table: str, pk: str):
        self.conn = conn
        self.table = table
        self.pk = pk

    def create(self, data: dict[str, Any]) -> bool:
        """INSERT OR REPLACE。pk 必须在 data 中。"""
        if self.pk not in data:
            raise ValueError(f"create: data 缺少主键 {self.pk}")
        cols = list(data.keys())
        ph = ",".join("?" for _ in cols)
        collist = ",".join(cols)
        sql = f"INSERT OR REPLACE INTO {self.table} ({collist}) VALUES ({ph})"
        with self.conn.cursor() as cur:
            cur.execute(sql, [data[c] for c in cols])
        return True

    def get(self, pk_value: Any) -> Optional[dict[str, Any]]:
        with self.conn.cursor() as cur:
            cur.execute(
                f"SELECT * FROM {self.table} WHERE {self.pk} = ?", (pk_value,)
            )
            row = cur.fetchone()
            if row is None:
                return None
            cols = [d[0] for d in cur.description]
            return dict(zip(cols, row))

    def update(self, pk_value: Any, data: dict[str, Any]) -> bool:
        """按主键更新 data 中的列；pk 本身不可在此改。"""
        if not data:
            return False
        sets = ",".join(f"{c} = ?" for c in data)
        sql = f"UPDATE {self.table} SET {sets} WHERE {self.pk} = ?"
        with self.conn.cursor() as cur:
            cur.execute(sql, [*data.values(), pk_value])
            return cur.rowcount >= 0
