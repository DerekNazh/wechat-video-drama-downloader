"""Go 微信视频号后端服务接口

提供 wx_video_download.exe 的启动、停止、状态检测，
微信视频号客户端连接状态检查，日志查询。
配置接口已迁移到 config.py
"""
import json
import logging
from fastapi import APIRouter

from config.settings import settings

logger = logging.getLogger("api_base_service")

router = APIRouter(prefix="/api/service", tags=["base_service"])


@router.get("/status")
def get_service_status():
    """获取 Go 后端服务和微信连接状态

    返回:
        service_online: Go 后端服务是否在线
        wechat_connected: 微信视频号客户端是否已连接
        process_running: wx_video_download.exe 进程是否存在
    """
    from core.utils.base_servier import WechatVideoService
    from core.utils.weixin_client import WechatVideoAPIClient
    from core.monitor.monitor import is_monitor_active
    from core.utils.database import db

    svc = WechatVideoService()
    client = WechatVideoAPIClient()

    service_online = False
    wechat_connected = False
    process_running = svc.is_process_running()

    if process_running:
        service_online = client.check_service()
        if service_online:
            wechat_connected = client.check_wechat_connected()

    return {
        "code": 0,
        "data": {
            "service_online": service_online,
            "wechat_connected": wechat_connected,
            "process_running": process_running,
            "monitor_running": is_monitor_active(),
            "today_count": db.count_videos_today(),
            "today_downloaded": db.count_downloaded_today(),
            "total_videos": db.count_videos_total(),
        },
        "msg": "",
    }


@router.post("/start")
def start_service():
    """启动 Go 后端服务（wx_video_download.exe）"""
    from core.utils.base_servier import WechatVideoService

    svc = WechatVideoService()

    if svc.is_running():
        return {"code": 0, "data": {"already_running": True}, "msg": "服务已在运行"}

    if not svc.is_process_running():
        exe_exists = __import__("os").path.exists(svc.exe_path)
        if not exe_exists:
            return {"code": -1, "msg": f"服务程序不存在: {svc.exe_path}"}

    # 清空 Go 后端旧任务数据库（避免 taskkill /F 导致的 BoltDB 损坏）
    from core.api.app import _clear_go_tasks_safe
    _clear_go_tasks_safe()

    success = svc.start(wait_seconds=10)

    if success:
        logger.info("[start_service] Go 后端服务启动成功")

        # 后台线程：等 Go 后端稳定后再恢复断点续传任务（不阻塞 API 响应）
        import threading
        import time

        def _resume_tasks_async():
            # 等 Go 后端完全就绪（WS 连接建立、事件总线初始化）
            time.sleep(5)
            from core.service.task import resume_pending_tasks
            try:
                resume_result = resume_pending_tasks()
                resumed = resume_result.get("resumed", 0)
                failed = resume_result.get("failed", 0)
                if resumed > 0:
                    logger.info("[start_service] 已恢复 %d 个下载任务（断点续传）", resumed)
                if failed > 0:
                    logger.warning("[start_service] %d 个任务恢复失败", failed)
            except Exception as e:
                logger.error("[start_service] 断点续传恢复异常: %s", e)

        threading.Thread(target=_resume_tasks_async, daemon=True).start()

        return {"code": 0, "data": {"already_running": False}, "msg": "服务启动成功"}
    else:
        logger.error("[start_service] Go 后端服务启动失败")
        return {"code": -1, "msg": "服务启动超时，请检查 wx_video_download.exe"}


@router.post("/stop")
def stop_service():
    """停止 Go 后端服务"""
    from core.utils.base_servier import WechatVideoService

    svc = WechatVideoService()

    if not svc.is_process_running():
        return {"code": 0, "data": {"already_stopped": True}, "msg": "服务未在运行"}

    success = svc.stop()

    if success:
        # 将 running 任务保存为 pending（断点续传）
        from core.utils.database import db
        running_tasks = db.list_download_tasks(status="running", limit=1000)
        for task in running_tasks:
            db.update_download_task_status(task.task_id, "pending")
        if running_tasks:
            logger.info("[stop_service] 已保存 %d 个任务为 pending（断点续传）", len(running_tasks))

        logger.info("[stop_service] Go 后端服务已停止")
        return {"code": 0, "data": {"already_stopped": False}, "msg": "服务已停止"}
    else:
        logger.error("[stop_service] Go 后端服务停止失败")
        return {"code": -1, "msg": "服务停止失败"}


@router.post("/restart")
def restart_service():
    """重启 Go 后端服务"""
    from core.utils.base_servier import WechatVideoService

    svc = WechatVideoService()
    success = svc.restart()

    if success:
        # 重启前保存 running 任务为 pending（restart 内部会 stop 再 start）
        from core.utils.database import db
        running_tasks = db.list_download_tasks(status="running", limit=1000)
        for task in running_tasks:
            db.update_download_task_status(task.task_id, "pending")
        if running_tasks:
            logger.info("[restart_service] 已保存 %d 个任务为 pending（断点续传）", len(running_tasks))

        # 后台恢复断点续传任务
        import threading
        import time

        def _resume_tasks_async():
            time.sleep(8)  # restart 需要更长时间
            from core.service.task import resume_pending_tasks
            try:
                resume_pending_tasks()
            except Exception as e:
                logger.error("[restart_service] 断点续传恢复异常: %s", e)

        threading.Thread(target=_resume_tasks_async, daemon=True).start()

        logger.info("[restart_service] Go 后端服务重启成功")
        return {"code": 0, "msg": "服务重启成功"}
    else:
        logger.error("[restart_service] Go 后端服务重启失败")
        return {"code": -1, "msg": "服务重启失败"}


@router.get("/wechat-status")
def check_wechat_connection():
    """单独检查微信视频号客户端连接状态

    前端可独立于服务状态调用此接口，
    用于在服务在线时显示微信连接状态。
    """
    from core.utils.weixin_client import WechatVideoAPIClient

    client = WechatVideoAPIClient()

    service_online = client.check_service()
    if not service_online:
        return {
            "code": -1,
            "data": {"connected": False, "service_online": False},
            "msg": "Go 后端服务未启动",
        }

    connected = client.check_wechat_connected()
    return {
        "code": 0,
        "data": {
            "connected": connected,
            "service_online": True,
        },
        "msg": "",
    }


# ==================== GET /api/service/logs ====================

@router.get("/logs")
def get_logs():
    """获取最近日志"""
    try:
        log_file = settings.log_dir / "app.log"
        if not log_file.exists():
            return {"logs": []}
        lines = log_file.read_text(encoding="utf-8").splitlines()
        logs = []
        for line in lines[-200:]:
            try:
                logs.append(json.loads(line))
            except (json.JSONDecodeError, ValueError):
                logs.append({"message": line, "level": "INFO", "time": ""})
        return {"logs": logs}
    except Exception as e:
        logger.error(f"[get_logs] {e}")
        return {"logs": []}
