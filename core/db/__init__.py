"""号匣 DB 包：schema DDL（YZPQ-303）+ 连接/DAO（YZPQ-304）。"""
from core.db.schema import SCHEMA_VERSION, init_schema, open_db, apply_pragmas
from core.db.connection import Connection
from core.db.dao import DAO

__all__ = ["SCHEMA_VERSION", "init_schema", "open_db", "apply_pragmas",
           "Connection", "DAO"]
