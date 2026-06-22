"""FastAPI 应用工厂"""
import logging

logger = logging.getLogger(__name__)

_monitor_service = None


def create_app():
    """创建并返回 FastAPI 应用实例"""
    from core.api.app import app
    return app


def shutdown_monitor():
    """停止监控服务"""
    global _monitor_service
    try:
        from core.monitor.monitor import MonitorService
        from core.utils.database import db
        service = MonitorService(db)
        result = service.stop_monitor()
        logger.info(f"[shutdown_monitor] 停止结果: {result}")
        return result
    except Exception as e:
        logger.error(f"[shutdown_monitor] 停止失败: {e}")
        return {"code": -1, "msg": str(e)}
