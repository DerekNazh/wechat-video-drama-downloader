"""号匣（haoxia）Pydantic Settings 环境骨架（YZPQ-288）。

18 键权威清单（见票 desc，v1.46/v1.30/v1.45/v1.84⑥）：
 密钥类（.env，不入库/不打印）：
   1 REDFOX_API_KEY
   2 TIKHUB_KEY
 服务类：
   3 HAOXIA_HOST=127.0.0.1
   4 HAOXIA_PORT=8000
   5 HAOXIA_LOCAL_TOKEN（首启生成 UUID 回写 .env）
 目录类：
   6 HAOXIA_DATA_DIR（默认 %LOCALAPPDATA%/haoxia）
   7 HAOXIA_DB_NAME=haoxia.db（DATA_DIR 下）
   8 HAOXIA_DOWNLOAD_DIR
   9 HAOXIA_LOG_DIR（默认 DATA_DIR/logs）
 网络类：
  10 HTTP_CONNECT_TIMEOUT=5
  11 REDFOX_READ_TIMEOUT=30
  12 TIKHUB_READ_TIMEOUT=90
  13 RETRY_MAX=3（指数退避 2s→4s→8s+jitter，仅连接失败/429/5xx）
 行为类：
  14 HAOXIA_FALLBACK_ENABLED=true
  15 HAOXIA_MAX_CONCURRENT=3
  16 HAOXIA_UA（浏览器 UA）
  17 HAOXIA_LOG_LEVEL=INFO
  18 HAOXIA_VERSION=1.0.0（唯一权威版本号）

纪律：
- 敏感键（REDFOX_API_KEY / TIKHUB_KEY / HAOXIA_LOCAL_TOKEN）不入日志。
- Settings 单例全局注入：`from core.config import settings`。
- 首启：用户 .env 不存在时从 core/config/.env.example 复制；HAOXIA_LOCAL_TOKEN
  为空时生成 UUID 回写 .env（不覆盖用户已填值）。
"""
from __future__ import annotations

import os
import secrets
import shutil
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_REPO_CONFIG_DIR = Path(__file__).resolve().parent
_REPO_ENV_EXAMPLE = _REPO_CONFIG_DIR / ".env.example"


def _default_data_dir() -> Path:
    local = os.getenv("LOCALAPPDATA")
    if local:
        return Path(local) / "haoxia"
    return Path.home() / ".haoxia"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # —— 密钥类（敏感，不入 log）——
    redfox_api_key: str = Field(default="", alias="REDFOX_API_KEY")
    tikhub_key: str = Field(default="", alias="TIKHUB_KEY")

    # —— 服务类 ——
    haoxia_host: str = Field(default="127.0.0.1", alias="HAOXIA_HOST")
    haoxia_port: int = Field(default=8000, alias="HAOXIA_PORT")
    haoxia_local_token: str = Field(default="", alias="HAOXIA_LOCAL_TOKEN")

    # —— 目录类 ——
    haoxia_data_dir: Path | None = Field(default=None, alias="HAOXIA_DATA_DIR")
    haoxia_db_name: str = Field(default="haoxia.db", alias="HAOXIA_DB_NAME")
    haoxia_download_dir: Path | None = Field(default=None, alias="HAOXIA_DOWNLOAD_DIR")
    haoxia_log_dir: Path | None = Field(default=None, alias="HAOXIA_LOG_DIR")

    # —— 网络类 ——
    http_connect_timeout: float = Field(default=5.0, alias="HTTP_CONNECT_TIMEOUT")
    redfox_read_timeout: float = Field(default=30.0, alias="REDFOX_READ_TIMEOUT")
    tikhub_read_timeout: float = Field(default=90.0, alias="TIKHUB_READ_TIMEOUT")
    retry_max: int = Field(default=3, alias="RETRY_MAX")

    # —— 行为类 ——
    haoxia_fallback_enabled: bool = Field(default=True, alias="HAOXIA_FALLBACK_ENABLED")
    haoxia_max_concurrent: int = Field(default=3, alias="HAOXIA_MAX_CONCURRENT")
    haoxia_ua: str = Field(
        default="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        alias="HAOXIA_UA",
    )
    haoxia_log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = Field(
        default="INFO", alias="HAOXIA_LOG_LEVEL"
    )
    haoxia_version: str = Field(default="1.0.0", alias="HAOXIA_VERSION")

    @field_validator("haoxia_data_dir", "haoxia_download_dir", "haoxia_log_dir", mode="before")
    @classmethod
    def _empty_str_to_none(cls, v):
        if isinstance(v, str) and not v.strip():
            return None
        return v

    # —— 派生路径 ——
    @property
    def data_dir(self) -> Path:
        if self.haoxia_data_dir is not None and str(self.haoxia_data_dir).strip():
            return Path(self.haoxia_data_dir)
        return _default_data_dir()

    @property
    def db_path(self) -> Path:
        return self.data_dir / self.haoxia_db_name

    @property
    def download_dir(self) -> Path:
        if self.haoxia_download_dir is not None and str(self.haoxia_download_dir).strip():
            return Path(self.haoxia_download_dir)
        return self.data_dir / "downloads"

    @property
    def log_dir(self) -> Path:
        if self.haoxia_log_dir is not None and str(self.haoxia_log_dir).strip():
            return Path(self.haoxia_log_dir)
        return self.data_dir / "logs"

    # —— 敏感字段脱敏（日志/打印用）——
    def public_dict(self) -> dict:
        data = self.model_dump()
        for k in ("redfox_api_key", "tikhub_key", "haoxia_local_token"):
            if data.get(k):
                data[k] = "***"
        return data


def _find_user_env_file() -> Path:
    """用户 .env 位置：环境变量 ENV_FILE 优先；否则取 DATA_DIR/.env。"""
    env_file = os.getenv("HAOXIA_ENV_FILE")
    if env_file:
        return Path(env_file)
    return _default_data_dir() / ".env"


def ensure_env_bootstrapped() -> Path:
    """首启：用户 .env 不存在则从 .env.example 复制；LOCAL_TOKEN 为空则生成 UUID 回写。

    返回用户 .env 路径。幂等。
    """
    user_env = _find_user_env_file()
    if not user_env.exists():
        user_env.parent.mkdir(parents=True, exist_ok=True)
        if _REPO_ENV_EXAMPLE.exists():
            shutil.copyfile(_REPO_ENV_EXAMPLE, user_env)
        else:
            user_env.touch()

    # 若 HAOXIA_LOCAL_TOKEN 为空，生成一个 UUID 回写（不覆盖用户已填值）
    lines = user_env.read_text(encoding="utf-8").splitlines()
    has_token = any(l.strip().startswith("HAOXIA_LOCAL_TOKEN=") and l.strip().split("=", 1)[1].strip() for l in lines)
    if not has_token:
        token = secrets.token_urlsafe(32)
        # 追加或补写
        replaced = False
        for i, l in enumerate(lines):
            if l.strip().startswith("HAOXIA_LOCAL_TOKEN="):
                lines[i] = f"HAOXIA_LOCAL_TOKEN={token}"
                replaced = True
                break
        if not replaced:
            lines.append(f"HAOXIA_LOCAL_TOKEN={token}")
        user_env.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return user_env


_singleton: Settings | None = None


def get_settings() -> Settings:
    global _singleton
    if _singleton is None:
        env_path = ensure_env_bootstrapped()
        os.environ.setdefault("HAOXIA_ENV_FILE", str(env_path))
        _singleton = Settings(_env_file=str(env_path))
    return _singleton
