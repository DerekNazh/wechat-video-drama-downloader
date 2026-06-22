"""孤立任务清理器

保证 Go 后端和 App 数据库的任务一致性。
启动时全量清理 + 定期后台增量清理。
"""

import logging
import threading
import time
from typing import Optional, Set

logger = logging.getLogger("orphan_cleaner")


class OrphanTaskCleaner:
    """孤立任务清理器

    保证 Go 后端和 App 数据库的任务一致性。

    使用方式:
        cleaner = OrphanTaskCleaner(go_client=client, db=db)
        cleaner.cleanup_on_startup()  # 启动时全量清理
        cleaner.start_periodic_cleanup()  # 启动定期后台清理
        # ...
        cleaner.stop()  # 停止定期清理
    """

    def __init__(
        self,
        go_client=None,
        db=None,
        interval: int = 600,
    ):
        """初始化孤立任务清理器

        Args:
            go_client: Go API 客户端 (WechatVideoAPIClient)，默认使用全局客户端
            db: 数据库实例 (Database)，默认使用全局 db
            interval: 定期清理间隔（秒），默认 600 秒（10 分钟）
        """
        if go_client is None:
            from core.utils.weixin_client import WechatVideoAPIClient
            self.go_client = WechatVideoAPIClient()
        else:
            self.go_client = go_client

        if db is None:
            from core.utils.database import db as global_db
            self.db = global_db
        else:
            self.db = db

        self.interval = interval
        self._thread: Optional[threading.Thread] = None
        self._running: bool = False
        self._go_online: bool = True  # 假设 Go 在线，直到收到 GO_DISCONNECTED

        logger.info("[OrphanTaskCleaner] 初始化完成")

    def cleanup_on_startup(self) -> None:
        """启动时全量清理

        获取 Go 端所有任务列表
        获取 App 端所有任务
        App 有但 Go 无 -> 删除 App 记录（跳过 pending 状态，可能是刚恢复的任务）
        Go 有但 App 无 -> 删除 Go 任务
        """
        logger.info("[cleanup_on_startup] 开始启动时全量清理")

        # 获取 App 端所有任务
        try:
            app_tasks = self.db.list_download_tasks(limit=10000)
            # 终态任务不参与清理（completed/failed/error/cancelled/done 是历史记录）
            _terminal = {"completed", "done", "failed", "error", "cancelled"}
            pending_task_ids: Set[str] = {task.task_id for task in app_tasks if task.status == "pending"}
            active_task_ids: Set[str] = {
                task.task_id for task in app_tasks
                if task.status != "pending" and task.status not in _terminal
            }
        except Exception as e:
            logger.error(f"[cleanup_on_startup] 获取 App 任务列表失败: {e}")
            return

        # 获取 Go 端所有任务 ID
        go_task_ids: Set[str] = set()
        try:
            go_tasks = self.go_client.list_download_tasks()
            go_task_ids = {task.get("id") for task in go_tasks if task.get("id")}
        except Exception as e:
            logger.error(f"[cleanup_on_startup] 获取 Go 任务列表失败: {e}")
            # 如果无法获取 Go 任务列表，保留 App 任务
            return

        logger.info(
            f"[cleanup_on_startup] App 任务: {len(active_task_ids)} active, {len(pending_task_ids)} pending | "
            f"Go 任务: {len(go_task_ids)}"
        )

        # App 有但 Go 无 -> 标记为 cancelled（与 cleanup_stale_tasks 策略一致，保留历史记录）
        orphan_in_app = active_task_ids - go_task_ids
        if orphan_in_app:
            logger.info(f"[cleanup_on_startup] App 孤立任务: {orphan_in_app}")
            for task_id in orphan_in_app:
                try:
                    self.db.update_download_task_status(task_id, "cancelled")
                    logger.info(f"[cleanup_on_startup] 标记 App 孤立任务为 cancelled: {task_id}")
                except Exception as e:
                    logger.error(
                        f"[cleanup_on_startup] 标记 App 任务失败: {task_id}, {e}"
                    )

        # pending 任务不在 Go 中是正常的（刚恢复的任务），打印详情
        pending_not_in_go = pending_task_ids - go_task_ids
        if pending_not_in_go:
            logger.info(f"[cleanup_on_startup] 跳过 {len(pending_not_in_go)} 个 pending 任务（刚恢复）: {pending_not_in_go}")

        # Go 有但 App 无 -> 删除 Go 任务
        all_app_task_ids = active_task_ids | pending_task_ids
        orphan_in_go = go_task_ids - all_app_task_ids
        if orphan_in_go:
            logger.info(f"[cleanup_on_startup] Go 孤立任务: {orphan_in_go}")
            for task_id in orphan_in_go:
                try:
                    self.go_client.cancel_task(task_id)
                    logger.info(f"[cleanup_on_startup] 取消 Go 孤立任务: {task_id}")
                except Exception as e:
                    logger.error(
                        f"[cleanup_on_startup] 取消 Go 任务失败: {task_id}, {e}"
                    )

        logger.info("[cleanup_on_startup] 启动时全量清理完成")

    def start_periodic_cleanup(self) -> None:
        """启动定期后台清理线程"""
        if self._thread is not None and self._thread.is_alive():
            logger.warning("[start_periodic_cleanup] 定期清理已在运行")
            return

        self._running = True
        self._thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._thread.start()
        logger.info(
            f"[start_periodic_cleanup] 定期清理已启动，间隔: {self.interval} 秒"
        )

    def stop(self) -> None:
        """停止定期清理"""
        self._running = False
        logger.info("[stop] 定期清理已停止")

    def set_go_online(self, online: bool) -> None:
        """设置 Go 后端在线状态（由 EventBus 事件调用）

        Go 离线时暂停清理，避免将 running 任务误判为孤立任务而删除。
        """
        if self._go_online == online:
            return
        self._go_online = online
        if not online:
            logger.info("[OrphanTaskCleaner] Go 后端离线，暂停增量清理")
        else:
            logger.info("[OrphanTaskCleaner] Go 后端在线，恢复增量清理")

    def _cleanup_loop(self) -> None:
        """定期清理循环"""
        while self._running:
            try:
                self._incremental_cleanup()
            except Exception as e:
                logger.error(f"[_cleanup_loop] 增量清理异常: {e}")

            # 分段睡眠，以便快速响应停止信号
            for _ in range(self.interval):
                if not self._running:
                    break
                time.sleep(1)

    def _incremental_cleanup(self) -> None:
        """增量清理（只检查活跃任务）

        检查 App 端活跃任务是否在 Go 端存在
        检查 Go 端活跃任务是否在 App 端存在

        注意：pending 状态的任务不会被清理，因为它们可能是刚恢复的任务，还没被 Go 处理
        """
        # Go 离线时跳过清理，避免将 running 任务误判为孤立任务而删除
        if not self._go_online:
            logger.debug("[_incremental_cleanup] Go 后端离线，跳过增量清理")
            return

        # 获取 App 端活跃任务（非 completed/failed/pending）
        # pending 状态的任务可能是刚恢复的，不应该被清理
        try:
            app_tasks = self.db.list_download_tasks(limit=10000)
            active_app_tasks = [
                task
                for task in app_tasks
                if task.status not in ("completed", "failed", "pending")
            ]
            active_app_task_ids = {task.task_id for task in active_app_tasks}
            pending_task_ids = {task.task_id for task in app_tasks if task.status == "pending"}
        except Exception as e:
            logger.error(f"[_incremental_cleanup] 获取 App 任务列表失败: {e}")
            return

        # 获取 Go 端任务列表
        try:
            go_tasks = self.go_client.list_download_tasks()
            go_task_ids = {task.get("id") for task in go_tasks if task.get("id")}
        except Exception as e:
            logger.error(f"[_incremental_cleanup] 获取 Go 任务列表失败: {e}")
            return

        # 打印任务状态追踪（调试用）
        logger.debug(f"[_incremental_cleanup] App: {len(active_app_task_ids)} active, {len(pending_task_ids)} pending | Go: {len(go_task_ids)}")
        for task in app_tasks:
            if task.status in ("pending", "running"):
                in_go = task.task_id in go_task_ids
                logger.info(f"[任务追踪] id={task.task_id}, status={task.status}, in_go={in_go}")

        # App 活跃任务在 Go 不存在 -> 删除 App 记录
        orphan_in_app = active_app_task_ids - go_task_ids
        if orphan_in_app:
            logger.info(f"[_incremental_cleanup] App 孤立任务: {orphan_in_app}")
            for task_id in orphan_in_app:
                try:
                    self.db.delete_download_task(task_id)
                    logger.info(f"[_incremental_cleanup] 删除 App 孤立任务: {task_id}")
                except Exception as e:
                    logger.error(
                        f"[_incremental_cleanup] 删除 App 任务失败: {task_id}, {e}"
                    )

        # pending 任务不在 Go 中是正常的，打印详情
        pending_not_in_go = pending_task_ids - go_task_ids
        if pending_not_in_go:
            logger.info(f"[_incremental_cleanup] 跳过 {len(pending_not_in_go)} 个 pending 任务: {pending_not_in_go}")

        # Go 任务在 App 不存在 -> 取消 Go 任务
        all_app_task_ids = active_app_task_ids | pending_task_ids
        orphan_in_go = go_task_ids - all_app_task_ids
        if orphan_in_go:
            logger.info(f"[_incremental_cleanup] Go 孤立任务: {orphan_in_go}")
            for task_id in orphan_in_go:
                try:
                    self.go_client.cancel_task(task_id)
                    logger.info(f"[_incremental_cleanup] 取消 Go 孤立任务: {task_id}")
                except Exception as e:
                    logger.error(
                        f"[_incremental_cleanup] 取消 Go 任务失败: {task_id}, {e}"
                    )
