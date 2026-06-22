"""FastAPI 应用"""
import asyncio
import logging
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from core.api.routers import video, search, inputer, monitor, player, task, base_service, sse, leader, config, author, sniff_proxy

logger = logging.getLogger("app")

# 全局组件实例
_event_bus = None
_orphan_cleaner = None
_progress_synchronizer = None


async def _periodic_log_cleanup():
    """每小时清理过期任务记录"""
    while True:
        await asyncio.sleep(3600)
        try:
            from core.utils.database import get_database
            _db = get_database()
            deleted = _db.cleanup_task_logs(7)
            if deleted > 0:
                logger.info(f"定时清理了 {deleted} 条过期任务记录")
        except Exception as e:
            logger.warning(f"定时清理过期记录失败: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时初始化所有组件"""
    threading.Thread(target=_startup_sequence, daemon=True).start()
    asyncio.create_task(_periodic_log_cleanup())
    yield
    _shutdown_sequence()


def _startup_sequence():
    """启动序列（按依赖顺序）"""
    import time

    # 1. 创建事件总线（最先）
    global _event_bus
    from core.utils.event_bus import get_event_bus, GO_DISCONNECTED, GO_CONNECTED
    _event_bus = get_event_bus()
    logger.info("[启动] 事件总线已创建")

    # 1.1 订阅 GO_DISCONNECTED：Go 崩溃时自动保存任务为 pending
    def _on_go_offline_save_tasks(event_data):
        """Go 后端离线时自动将 running/wait 任务保存为 pending"""
        from core.utils.database import db
        for status in ("running", "wait"):
            tasks = db.list_download_tasks(status=status, limit=1000)
            for task in tasks:
                db.update_download_task_status(task.task_id, "pending")
            if tasks:
                logger.info("[GO_DISCONNECTED] 已保存 %d 个 %s 任务为 pending", len(tasks), status)

    _event_bus.subscribe(GO_DISCONNECTED, _on_go_offline_save_tasks)

    # 2. 文件校验器 - 启动时校验
    from core.utils.file_validator import FileValidator
    file_validator = FileValidator()
    file_validator.validate_on_startup()
    logger.info("[启动] 文件校验完成")

    # 2.1 清理过期任务记录
    try:
        from core.utils.database import get_database
        _db = get_database()
        deleted = _db.cleanup_task_logs(7)
        if deleted > 0:
            logger.info(f"清理了 {deleted} 条过期任务记录")
    except Exception as e:
        logger.warning(f"清理过期记录失败: {e}")

    # 3. 启动 res_download（短剧嗅探服务，必须先于 weixin_download）
    _auto_start_res_download()

    # 4. 启动 weixin_download（视频号后端）
    _auto_start_go_backend()

    # 4. 恢复待处理任务（断点续传：重新创建 Go 下载任务）
    # 使用 resume_pending_tasks 而非 resume_all_running_tasks，
    # 因为停止服务时任务已保存为 pending，冷启动需要恢复 pending 状态的任务
    # 注意：必须在 cleanup_stale 之前执行，否则任务会被清理掉
    from core.service.task import resume_pending_tasks
    resume_result = resume_pending_tasks()
    if resume_result["resumed"] > 0:
        logger.info("[启动] 已恢复 %d 个下载任务（断点续传）", resume_result["resumed"])
    if resume_result["failed"] > 0:
        logger.warning("[启动] %d 个任务恢复失败", resume_result["failed"])

    # 5. 孤立任务清理器 - 启动时清理（清理 Go 端不存在但本地有的残留任务）
    global _orphan_cleaner
    from core.utils.orphan_cleaner import OrphanTaskCleaner
    _orphan_cleaner = OrphanTaskCleaner()
    _orphan_cleaner.cleanup_on_startup()

    # 5.1 订阅 GO_CONNECTED/GO_DISCONNECTED：控制孤儿清理器暂停/恢复
    _event_bus.subscribe(GO_CONNECTED, lambda e: _orphan_cleaner.set_go_online(True) if _orphan_cleaner else None)
    _event_bus.subscribe(GO_DISCONNECTED, lambda e: _orphan_cleaner.set_go_online(False) if _orphan_cleaner else None)

    logger.info("[启动] 孤立任务清理完成")

    # 6. 启动 WebSocket 监听器（发布连接事件）
    threading.Thread(target=_start_progress_listener_with_event_bus, daemon=True).start()

    # 7. 启动进度同步器
    global _progress_synchronizer
    from core.utils.progress_synchronizer import ProgressSynchronizer
    _progress_synchronizer = ProgressSynchronizer(event_bus=_event_bus)
    logger.info("[启动] 进度同步器已创建")

    # 8. 启动定期清理
    if _orphan_cleaner:
        _orphan_cleaner.start_periodic_cleanup()
        logger.info("[启动] 定期清理已启动")


def _clear_go_tasks_safe():
    """安全清空 Go 后端任务记录（不删除磁盘文件）

    直接删除 gopeed.db 数据库文件，Go 重启时会自动重建。
    绝不调用 clear_all_tasks() API，因为该接口会执行 os.RemoveAll 删除已下载的视频文件。
    """
    import os
    from config.settings import settings
    db_path = str(settings.gopeed_db_path)
    try:
        if os.path.exists(db_path):
            os.remove(db_path)
            logger.info(f"[启动] 已删除 Go 后端任务数据库: {db_path}")
        else:
            logger.info("[启动] Go 后端任务数据库不存在，无需清理")
    except Exception as e:
        logger.warning(f"[启动] 删除 Go 后端任务数据库失败: {e}")


def _start_progress_listener_with_event_bus():
    """启动 WS 进度监听器（带事件总线）"""
    import time
    from core.utils.socket_client import DownloadProgressListener
    from core.utils.event_bus import emit, get_event_bus

    time.sleep(5)  # 等 Go 后端先启动

    event_bus = get_event_bus()

    while True:
        try:
            listener = DownloadProgressListener(event_bus=event_bus)

            def on_progress(data):
                # 保存进度到数据库
                from core.service.task import save_progress_from_sse
                save_progress_from_sse(data)
                emit("task_progress", data)

            listener.start(on_progress)
            logger.info("[进度监听] WS 进度监听器已启动")

            if listener._thread:
                listener._thread.join()

            logger.warning("[进度监听] WS 连接断开，3 秒后重连...")
            time.sleep(3)
        except Exception as e:
            logger.error(f"[进度监听] 异常: {e}，5 秒后重试")
            time.sleep(5)


def _auto_start_res_download():
    """启动 res_download 短剧嗅探服务

    启动序列：
    1. 启动 res_download.exe
    2. 等待就绪 + 注入配置
    3. 开启系统代理
    """
    try:
        from core.utils.res_download_service import ResDownloadService

        svc = ResDownloadService()

        if svc.is_running():
            logger.info("[启动] res_download 已在运行，先停止...")
            svc.stop()

        logger.info("[启动] 自动启动 res_download 短剧嗅探服务...")
        success = svc.start(wait_seconds=30)
        if success:
            logger.info("[启动] res_download 启动成功")
        else:
            logger.warning("[启动] res_download 启动失败，短剧嗅探功能不可用")
            return

        # 启动后开启系统代理
        if settings.res_auto_proxy:
            svc.open_proxy()
            logger.info("[启动] 系统代理已开启")

    except Exception as e:
        logger.warning(f"[启动] 自动启动 res_download 异常: {e}")


def _auto_start_go_backend():
    """后台线程：自动启动 Go 后端服务

    stop() 现在会等待进程退出和端口释放，无需额外 sleep。
    start() 也会在端口被占用时自动等待。
    """
    try:
        from core.utils.base_servier import WechatVideoService

        svc = WechatVideoService()

        if svc.is_running():
            logger.info("[启动] Go 后端已在运行，先停止再清空旧任务数据库...")
            svc.stop()

        # 启动前先清数据库，避免旧任务残留（此时 Go 已停止，文件不再占用）
        _clear_go_tasks_safe()

        logger.info("[启动] 自动启动微信视频号后端...")
        success = svc.start(wait_seconds=15)
        if success:
            logger.info("[启动] 微信视频号后端启动成功")
        else:
            logger.warning("[启动] 微信视频号后端启动失败，部分功能可能不可用")
    except Exception as e:
        logger.warning(f"[启动] 自动启动微信视频号后端异常: {e}")


def _shutdown_sequence():
    """关闭序列（反向：先关 weixin_download，再关 res_download）"""
    global _orphan_cleaner

    logger.info("[关闭] 开始关闭组件...")

    # 保存运行中任务的进度
    _save_running_tasks_progress()

    if _orphan_cleaner:
        _orphan_cleaner.stop()
        logger.info("[关闭] 孤立任务清理器已停止")

    # 关闭 weixin_download
    try:
        from core.utils.base_servier import WechatVideoService
        svc = WechatVideoService()
        if svc.is_process_running():
            logger.info("[关闭] 正在停止 weixin_download...")
            svc.stop()
            logger.info("[关闭] weixin_download 已停止")
    except Exception as e:
        logger.error(f"[关闭] weixin_download 停止异常: {e}")

    # 关闭 res_download（含系统代理清理）
    try:
        from core.utils.res_download_service import ResDownloadService
        svc = ResDownloadService()
        if svc.is_process_running():
            logger.info("[关闭] 正在停止 res_download...")
            # 先关闭系统代理
            svc.unset_proxy()
            svc.stop()
            logger.info("[关闭] res_download 已停止")
        else:
            logger.info("[关闭] res_download 未在运行，仅清理系统代理")
            svc.unset_proxy()
    except Exception as e:
        logger.error(f"[关闭] res_download 停止异常: {e}")

    logger.info("[关闭] 所有组件已关闭")


def _save_running_tasks_progress():
    """保存运行中任务的进度（应用关闭时调用）

    将 running 和 wait 状态的任务保存为 pending，
    pending 状态保持不变，确保下次启动时能恢复。
    """
    from core.utils.database import db

    try:
        # 保存 running 和 wait 状态的任务为 pending
        running_tasks = db.list_download_tasks(status="running", limit=1000)
        wait_tasks = db.list_download_tasks(status="wait", limit=1000)
        pending_tasks = db.list_download_tasks(status="pending", limit=1000)

        total_count = len(running_tasks) + len(wait_tasks) + len(pending_tasks)
        if total_count == 0:
            logger.info("[关闭] 没有运行中的任务需要保存")
            return

        saved_count = 0
        for task in running_tasks:
            db.update_download_task_status(task.task_id, "pending")
            saved_count += 1

        for task in wait_tasks:
            db.update_download_task_status(task.task_id, "pending")
            saved_count += 1

        for task in pending_tasks:
            # pending 状态保持不变，确保下次启动能恢复
            saved_count += 1

        logger.info("[关闭] 已保存 %d 个任务（running=%d, wait=%d, pending=%d）",
                    saved_count, len(running_tasks), len(wait_tasks), len(pending_tasks))
    except Exception as e:
        logger.warning("[关闭] 保存运行中任务进度失败: %s", e)


app = FastAPI(title="微信视频号监控 API", lifespan=lifespan)

# 注册路由
app.include_router(video.router)
app.include_router(author.router)
app.include_router(search.router)
app.include_router(inputer.router)
app.include_router(inputer.public_router)
app.include_router(monitor.router)
app.include_router(player.router)
app.include_router(task.router)
app.include_router(base_service.router)
app.include_router(sse.router)
app.include_router(leader.router)
app.include_router(config.router)
app.include_router(sniff_proxy.router)

# 静态文件目录（使用 settings.app_root 兼容打包和开发模式）
from config.settings import settings
STATIC_DIR = settings.static_dir

# 挂载静态资源（CSS、JS、图片等）
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/")
def serve_index():
    """返回前端页面"""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return {"message": "微信视频号监控 API - index.html 未找到"}


@app.get("/health")
def health():
    return {"status": "ok"}
