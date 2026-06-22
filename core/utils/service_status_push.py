"""服务状态推送 — 后台线程定期检测 Go 服务和微信连接状态

通过 SSE 推送给前端，替代高频 HTTP 轮询。
"""
import logging
import threading
import time
from typing import Optional

logger = logging.getLogger("service_status_push")

# 检测间隔（秒）
CHECK_INTERVAL = 1.0

# Go 服务启动后的稳定期（秒）- 在这段时间内不检测微信连接
STARTUP_GRACE_PERIOD = 3.0

# 上一次状态缓存（用于检测变化）
_last_status: Optional[dict] = None
_status_lock = threading.Lock()
_push_thread: Optional[threading.Thread] = None
_running = False

# Go 服务启动时间（用于计算稳定期）
_service_startup_time: Optional[float] = None


def start_status_push():
    """启动状态推送线程"""
    global _push_thread, _running, _last_status

    if _push_thread is not None and _push_thread.is_alive():
        return

    _running = True
    _last_status = None  # 重置缓存，确保首次推送
    _push_thread = threading.Thread(target=_status_loop, daemon=True, name="ServiceStatusPush")
    _push_thread.start()
    logger.info("[状态推送] 线程已启动，检测间隔 %.1fs", CHECK_INTERVAL)


def stop_status_push():
    """停止状态推送线程"""
    global _running
    _running = False


def _status_loop():
    """状态检测循环"""
    global _last_status, _service_startup_time

    from core.utils.base_servier import WechatVideoService
    from core.utils.weixin_client import WechatVideoAPIClient

    svc = WechatVideoService()
    client = WechatVideoAPIClient(timeout=3)  # 缩短 timeout，避免阻塞

    # 记录上一次服务状态，用于检测服务是否刚启动
    last_service_online = False

    while _running:
        try:
            # 检测进程
            process_running = svc.is_process_running()

            # 检测 Go 服务
            service_online = False
            wechat_connected = False

            if process_running:
                service_online = client.check_service()

                # 检测服务是否刚启动（从离线变为在线）
                if service_online and not last_service_online:
                    _service_startup_time = time.time()
                    logger.info("[状态推送] Go 服务刚启动，进入稳定期 (%.1f秒)", STARTUP_GRACE_PERIOD)

                # 只有在稳定期之后才检测微信连接
                if service_online:
                    in_grace_period = (
                        _service_startup_time is not None and
                        time.time() - _service_startup_time < STARTUP_GRACE_PERIOD
                    )

                    if in_grace_period:
                        # 稳定期内，不检测微信连接，保持 False
                        wechat_connected = False
                        logger.debug("[状态推送] 稳定期内，跳过微信连接检测")
                    else:
                        wechat_connected = client.check_wechat_connected()

                last_service_online = service_online

            else:
                # 进程不存在，重置启动时间
                _service_startup_time = None
                last_service_online = False

            current_status = {
                "service_online": service_online,
                "wechat_connected": wechat_connected,
            }

            # 检查是否有变化
            with _status_lock:
                if _last_status is None or _last_status != current_status:
                    prev_status = _last_status
                    _last_status = current_status
                    _emit_status(current_status, prev_status)

        except Exception as e:
            logger.warning("[状态推送] 检测异常: %s", e)

        time.sleep(CHECK_INTERVAL)


def _emit_status(status: dict, prev_status: Optional[dict] = None):
    """推送状态变化"""
    from core.utils.event_bus import emit

    emit("service_status", status)
    logger.info("[状态推送] 状态变化: service=%s, wechat=%s",
                status["service_online"], status["wechat_connected"])

    # 微信刚连接（从 False → True）+ Go 在线 → 尝试恢复 pending 任务
    prev_wechat = prev_status.get("wechat_connected", False) if prev_status else False
    if status["wechat_connected"] and not prev_wechat and status["service_online"]:
        _try_resume_pending()


def _try_resume_pending():
    """微信刚连接时，尝试恢复 pending 下载任务"""
    import threading
    from core.utils.database import db

    # 检查是否有 pending 任务需要恢复
    pending = db.list_download_tasks(status="pending", limit=1000)
    if not pending:
        logger.debug("[状态推送] 无 pending 任务，无需恢复")
        return

    logger.info("[状态推送] 微信已连接，发现 %d 个 pending 任务，启动恢复", len(pending))

    def _resume_thread():
        try:
            from core.service.task import resume_pending_tasks
            result = resume_pending_tasks()
            logger.info("[状态推送] 恢复完成: resumed=%d, failed=%d",
                        result.get("resumed", 0), result.get("failed", 0))
        except Exception as e:
            logger.error("[状态推送] 恢复异常: %s", e)

    threading.Thread(target=_resume_thread, daemon=True, name="ResumeOnWeChatConnect").start()
