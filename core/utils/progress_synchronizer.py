"""进度同步器

实现 WebSocket + HTTP 轮询双保险机制：
- WebSocket 正常时实时推送进度
- WebSocket 断开时自动切换 HTTP 轮询
"""
import logging
import threading
import time
from typing import Callable, Optional

from core.utils.event_bus import EventBus, GO_CONNECTED, GO_DISCONNECTED

logger = logging.getLogger("progress_synchronizer")


class PollThread:
    """轮询线程封装

    用于在后台定期执行回调函数
    """

    def __init__(self, callback: Callable, interval: int = 5):
        """初始化轮询线程

        Args:
            callback: 轮询回调函数
            interval: 轮询间隔（秒）
        """
        self._callback = callback
        self._interval = int(interval)  # 确保是整数
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """启动轮询线程"""
        if self._running:
            logger.warning("[PollThread] 线程已在运行")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info(f"[PollThread] 轮询线程已启动，间隔: {self._interval}秒")

    def stop(self) -> None:
        """停止轮询线程"""
        if not self._running:
            return

        self._running = False
        logger.info("[PollThread] 轮询线程已停止")

    def _run(self) -> None:
        """轮询循环"""
        while self._running:
            try:
                self._callback()
            except Exception as e:
                logger.error(f"[PollThread] 轮询回调异常: {e}")

            # 分段睡眠，便于快速响应停止
            for _ in range(self._interval):
                if not self._running:
                    break
                time.sleep(1)


class ProgressSynchronizer:
    """进度同步器

    实现 WebSocket + HTTP 轮询双保险：
    - WebSocket 连接时：实时推送进度，停止 HTTP 轮询
    - WebSocket 断开时：自动启动 HTTP 轮询
    """

    def __init__(
        self,
        event_bus: EventBus,
        go_client=None,
        db=None,
        poll_interval: int = 5
    ):
        """初始化进度同步器

        Args:
            event_bus: 事件总线（用于订阅连接状态事件）
            go_client: Go API 客户端（支持依赖注入）
            db: 数据库实例（支持依赖注入）
            poll_interval: HTTP 轮询间隔（秒）
        """
        self._event_bus = event_bus
        self._go_client = go_client
        self._db = db
        self._poll_interval = poll_interval
        self._poll_thread: Optional[PollThread] = None
        self._ws_connected = False
        self._lock = threading.Lock()

        # 订阅事件
        self._event_bus.subscribe(GO_CONNECTED, self._on_ws_connected)
        self._event_bus.subscribe(GO_DISCONNECTED, self._on_ws_disconnected)

        logger.info("[ProgressSynchronizer] 初始化完成，已订阅连接状态事件")

    def _on_ws_connected(self, event_data=None) -> None:
        """WebSocket 连接事件处理

        连接成功后停止 HTTP 轮询

        Args:
            event_data: 事件数据（包含 online: True）
        """
        logger.info(f"[ProgressSynchronizer] WebSocket 已连接: {event_data}")

        with self._lock:
            self._ws_connected = True

            # 停止 HTTP 轮询
            if self._poll_thread is not None:
                logger.info("[ProgressSynchronizer] 停止 HTTP 轮询")
                self._poll_thread.stop()
                self._poll_thread = None

    def _on_ws_disconnected(self, event_data=None) -> None:
        """WebSocket 断开事件处理

        断开后启动 HTTP 轮询

        Args:
            event_data: 事件数据（包含 online: False）
        """
        logger.warning(f"[ProgressSynchronizer] WebSocket 已断开: {event_data}")

        with self._lock:
            self._ws_connected = False

            # 停止旧的轮询线程（如果存在）
            if self._poll_thread is not None:
                logger.info("[ProgressSynchronizer] 停止旧的轮询线程")
                self._poll_thread.stop()

            # 启动 HTTP 轮询
            logger.info(f"[ProgressSynchronizer] 启动 HTTP 轮询，间隔: {self._poll_interval}秒")
            self._poll_thread = PollThread(
                self._poll_progress,
                interval=self._poll_interval
            )
            self._poll_thread.start()

    def _poll_progress(self) -> None:
        """HTTP 轮询进度

        从 Go API 获取任务列表并更新数据库
        """
        if self._go_client is None or self._db is None:
            logger.warning("[ProgressSynchronizer] Go 客户端或数据库未配置")
            return

        try:
            tasks = self._go_client.list_download_tasks()
            if not tasks:
                return

            for task in tasks:
                task_id = task.get("id", "")
                if not task_id:
                    continue

                progress = task.get("progress", 0)
                downloaded = task.get("downloaded", 0)
                total_size = task.get("totalSize", 0)
                speed = task.get("speed", 0)
                status = task.get("status", "")

                # 更新数据库
                try:
                    self._db.update_download_task_progress(
                        task_id=task_id,
                        progress=progress,
                        downloaded=downloaded,
                        total_size=total_size,
                        speed=speed,
                        status=status if status else None
                    )
                except Exception as e:
                    logger.error(f"[ProgressSynchronizer] 更新任务进度失败: task_id={task_id}, error={e}")

        except Exception as e:
            logger.error(f"[ProgressSynchronizer] HTTP 轮询异常: {e}")

    def on_ws_message(self, message: dict) -> None:
        """WebSocket 消息处理

        处理实时推送的进度消息

        Args:
            message: WebSocket 消息，包含任务进度信息
        """
        # WebSocket 断开时忽略消息
        if not self._ws_connected:
            return

        if self._db is None:
            logger.warning("[ProgressSynchronizer] 数据库未配置")
            return

        task_id = message.get("id", "")
        if not task_id:
            return

        try:
            progress = message.get("progress", 0)
            downloaded = message.get("downloaded", 0)
            total_size = message.get("totalSize", 0)
            speed = message.get("speed", 0)
            status = message.get("status", "")

            self._db.update_download_task_progress(
                task_id=task_id,
                progress=progress,
                downloaded=downloaded,
                total_size=total_size,
                speed=speed,
                status=status if status else None
            )

        except Exception as e:
            logger.error(f"[ProgressSynchronizer] WebSocket 消息处理失败: task_id={task_id}, error={e}")

    def stop(self) -> None:
        """停止同步器（清理资源）"""
        with self._lock:
            if self._poll_thread is not None:
                self._poll_thread.stop()
                self._poll_thread = None

            # 取消事件订阅
            self._event_bus.unsubscribe(GO_CONNECTED, self._on_ws_connected)
            self._event_bus.unsubscribe(GO_DISCONNECTED, self._on_ws_disconnected)

        logger.info("[ProgressSynchronizer] 同步器已停止")
