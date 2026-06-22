"""配置管理路由

统一管理所有配置相关的 GET/POST 接口
"""
import logging

from fastapi import APIRouter
from pydantic import BaseModel

from config.settings import settings

logger = logging.getLogger("api_config")
router = APIRouter(prefix="/api/service", tags=["config"])


@router.get("/config")
def get_config():
    """前端启动配置"""
    return {
        "wx_status_interval": settings.wx_status_interval,
        "wx_download_dir": settings._config.wx_download_dir,
        "log_level": settings.log_level,
        "project_version": settings.project_version,
        "max_concurrent": settings.max_concurrent,
        "doc_sync_interval": settings._config.doc_sync_interval,
        "ads_enabled": settings.ads_enabled,
    }


class UpdateConfigRequest(BaseModel):
    max_concurrent: int | None = None
    doc_sync_interval: int | None = None
    wx_status_interval: int | None = None
    wx_download_dir: str | None = None
    log_level: str | None = None


@router.post("/config")
def update_config(request: UpdateConfigRequest):
    """更新前端可修改的配置项"""
    updated = []

    if request.max_concurrent is not None:
        value = request.max_concurrent
        if value < 1 or value > 20:
            return {"code": -1, "msg": "并发数范围 1-20"}
        settings.max_concurrent = value
        _update_env_value("MAX_CONCURRENT", str(value))
        try:
            from core.utils.database import db
            from core.monitor.monitor import MonitorService
            svc = MonitorService(db)
            svc._max_concurrent = value
        except Exception:
            pass
        updated.append(f"最大并发数={value}")
        logger.info(f"[update_config] max_concurrent={value}")

    if request.doc_sync_interval is not None:
        value = request.doc_sync_interval
        if value < 5 or value > 120:
            return {"code": -1, "msg": "文档监控间隔范围 5-120 分钟"}
        settings._config.doc_sync_interval = value
        _update_env_value("DOC_SYNC_INTERVAL", str(value))
        updated.append(f"文档监控间隔={value}分钟")
        logger.info(f"[update_config] doc_sync_interval={value}")

    if request.wx_status_interval is not None:
        value = request.wx_status_interval
        if value < 1 or value > 60:
            return {"code": -1, "msg": "状态轮询间隔范围 1-60 秒"}
        settings._config.wx_status_interval = value
        _update_env_value("WX_STATUS_INTERVAL", str(value))
        updated.append(f"状态轮询间隔={value}秒")
        logger.info(f"[update_config] wx_status_interval={value}")

    if request.wx_download_dir is not None:
        value = request.wx_download_dir
        if not value or not value.strip():
            return {"code": -1, "msg": "下载目录不能为空"}
        settings._config.wx_download_dir = value.strip()
        _update_env_value("WX_DOWNLOAD_DIR", value.strip())
        updated.append(f"下载目录={value.strip()}")
        logger.info(f"[update_config] wx_download_dir={value.strip()}")

    if request.log_level is not None:
        value = request.log_level.upper()
        valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
        if value not in valid_levels:
            return {"code": -1, "msg": f"日志级别必须是 {', '.join(valid_levels)}"}
        settings._config.log_level = value
        _update_env_value("LOG_LEVEL", value)
        updated.append(f"日志级别={value}")
        logger.info(f"[update_config] log_level={value}")

    if not updated:
        return {"code": -1, "msg": "没有需要更新的配置"}

    return {"code": 0, "msg": f"已更新: {', '.join(updated)}"}


def _update_env_value(key: str, value: str):
    """更新 .env 文件中指定 key 的值"""
    env_path = settings.env_path
    if not env_path.exists():
        return

    lines = env_path.read_text(encoding="utf-8").splitlines()
    found = False
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith(f"{key}="):
            lines[i] = f"{key}={value}"
            found = True
            break

    if not found:
        lines.append(f"{key}={value}")

    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
