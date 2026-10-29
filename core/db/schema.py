"""号匣（haoxia）DB 表结构 DDL（YZPQ-303）。

权威依据：Spec §2 基础 5 表 + v1.58 collections + v1.60 video_comments
+ v1.42 全 TEXT 大整数 + v1.84⑨ WAL。

纪律：
- 所有 id / 大整数（export_id/decode_key/互动数）一律 TEXT，避免 SQLite INTEGER
  精度丢失（JS Number 安全整数 2^53）。
- 建库即开 WAL + busy_timeout(5000)。
- 本模块只负责「建表/加列」，不写业务 DAO（那是 YZPQ-304）。
- 幂等：可对已存在的旧库重复执行（CREATE IF NOT EXISTS + 列存在则跳过）。
"""
from __future__ import annotations

import sqlite3

SCHEMA_VERSION = "1.0.0"

# ---- 基础 5 表 ----
_DDL_BASE = [
    """
    CREATE TABLE IF NOT EXISTS authors (
        id TEXT PRIMARY KEY,
        source_author_id TEXT UNIQUE,
        username TEXT,
        name TEXT,
        bio TEXT,
        avatar_url TEXT,
        cover_img_url TEXT,
        follower_count TEXT DEFAULT '0',
        following_count TEXT DEFAULT '0',
        like_total TEXT DEFAULT '0',
        cover_updated_at TEXT,
        latest_publish_date TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS author_videos (
        video_id TEXT PRIMARY KEY,
        author_id TEXT NOT NULL,
        title TEXT NOT NULL,
        object_nonce_id TEXT,
        url TEXT,
        spec TEXT,
        file_size TEXT DEFAULT '0',
        cover_url TEXT,
        decode_key TEXT DEFAULT '0',
        author_avatar TEXT,
        duration TEXT DEFAULT '0',
        create_time TEXT,
        is_downloaded INTEGER DEFAULT 0,
        download_path TEXT,
        downloaded_at TEXT,
        video_type TEXT DEFAULT 'short_video',
        export_id TEXT,
        share_url TEXT,
        read_count TEXT DEFAULT '0',
        like_count TEXT DEFAULT '0',
        fav_count TEXT DEFAULT '0',
        forward_count TEXT DEFAULT '0',
        comment_count TEXT DEFAULT '0',
        collection_id TEXT,
        url_updated_at TEXT,
        width_height TEXT,
        topic TEXT,
        FOREIGN KEY (author_id) REFERENCES authors(id) ON DELETE CASCADE
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS download_tasks (
        task_id TEXT PRIMARY KEY,
        video_id TEXT NOT NULL,
        url TEXT NOT NULL,
        title TEXT NOT NULL,
        filename TEXT NOT NULL,
        spec TEXT NOT NULL,
        suffix TEXT NOT NULL,
        key TEXT DEFAULT '0',
        status TEXT DEFAULT 'pending',
        progress INTEGER DEFAULT 0,
        downloaded INTEGER DEFAULT 0,
        total_size TEXT DEFAULT '0',
        speed INTEGER DEFAULT 0,
        error_msg TEXT,
        video_type TEXT DEFAULT 'short_video',
        create_time TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        completed_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS task_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        video_id TEXT NOT NULL,
        author_id TEXT,
        username TEXT,
        title TEXT,
        cover_url TEXT,
        duration TEXT DEFAULT '0',
        file_size TEXT DEFAULT '0',
        completed_at TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS resume_states (
        task_id TEXT PRIMARY KEY,
        state TEXT NOT NULL,
        created_at TEXT
    )
    """,
]

# ---- v1.58 collections（合集）----
_DDL_COLLECTIONS = """
    CREATE TABLE IF NOT EXISTS collections (
        topic_id TEXT PRIMARY KEY,
        topic TEXT,
        topic_type TEXT,
        author_username TEXT,
        cover_url TEXT,
        video_count TEXT DEFAULT '0',
        fetched_at TEXT
    )
"""

# ---- v1.60 video_comments（视频评论）----
_DDL_COMMENTS = """
    CREATE TABLE IF NOT EXISTS video_comments (
        object_id TEXT,
        comment_id TEXT PRIMARY KEY,
        nickname TEXT,
        username TEXT,
        head_url TEXT,
        content TEXT,
        like_count TEXT DEFAULT '0',
        reply_count TEXT DEFAULT '0',
        create_time TEXT,
        ip_region TEXT,
        fetched_at TEXT
    )
"""

# ---- Spec §4 缓存/链路表 ----
_DDL_CACHE = [
    """
    CREATE TABLE IF NOT EXISTS channel_alias (
        alias TEXT PRIMARY KEY,
        channel_id TEXT,
        resolved_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS author_list_snapshot (
        author_id TEXT,
        snapshot_key TEXT,
        data TEXT,
        fetched_at TEXT,
        PRIMARY KEY (author_id, snapshot_key)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS search_cache (
        cache_key TEXT PRIMARY KEY,
        data TEXT,
        expire_at TEXT,
        fetched_at TEXT
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS api_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        channel TEXT,
        endpoint TEXT,
        cost TEXT DEFAULT '0',
        status TEXT,
        called_at TEXT
    )
    """,
]

_DDL_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_author_videos_author_id ON author_videos(author_id)",
    "CREATE INDEX IF NOT EXISTS idx_download_tasks_video_id ON download_tasks(video_id)",
    "CREATE INDEX IF NOT EXISTS idx_download_tasks_status ON download_tasks(status)",
    "CREATE UNIQUE INDEX IF NOT EXISTS idx_task_log_unique ON task_log(video_id, completed_at)",
    "CREATE INDEX IF NOT EXISTS idx_video_comments_object ON video_comments(object_id)",
]


def _exec_safe_alter(conn: sqlite3.Connection, ddl: str) -> None:
    """旧库补列：列已存在则忽略 OperationalError。"""
    try:
        conn.execute(ddl)
    except sqlite3.OperationalError:
        pass


def apply_pragmas(conn: sqlite3.Connection) -> None:
    """WAL + busy_timeout(5000) + 外键。"""
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")


def init_schema(conn: sqlite3.Connection) -> None:
    """按当前 DDL 初始化全部表（幂等）。"""
    apply_pragmas(conn)
    for ddl in _DDL_BASE:
        conn.execute(ddl)
    conn.execute(_DDL_COLLECTIONS)
    conn.execute(_DDL_COMMENTS)
    for ddl in _DDL_CACHE:
        conn.execute(ddl)
    for idx in _DDL_INDEXES:
        conn.execute(idx)
    conn.commit()


def open_db(db_path: str) -> sqlite3.Connection:
    """打开库并初始化 schema，返回连接。"""
    conn = sqlite3.connect(db_path, timeout=5.0)
    init_schema(conn)
    return conn
