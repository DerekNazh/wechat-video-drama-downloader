"""号匣 DB 包：schema DDL（YZPQ-303）。"""
from core.db.schema import SCHEMA_VERSION, init_schema, open_db, apply_pragmas

__all__ = ["SCHEMA_VERSION", "init_schema", "open_db", "apply_pragmas"]
