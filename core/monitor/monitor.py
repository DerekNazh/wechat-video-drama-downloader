"""监控服务层

提供一键监控功能：自动下载作者最新视频
"""

import logging
import threading
import time
from typing import List, Optional

from core.utils.database import db as _default_db

logger = logging.getLogger("monitor_service")

# 模块级全局监控状态（跨请求持久化）
_monitor_running = False
_monitor_lock = threading.Lock()
_monitor_thread = None


def is_monitor_active() -> bool:
    """检查监控是否正在运行（模块级全局状态）"""
    return _monitor_running


class MonitorService:
    """监控服务

    提供一键监控功能：
    - 启动监控：在后台线程中循环同步作者视频并创建下载任务
    - 停止监控：清理任务、删除损坏文件、保留视频列表
    - 暂停/恢复：订阅事件总线，Go 离线时暂停，Go 恢复时继续
    """

    def __init__(self, db=None, video_service_cls=None, task_service_cls=None, event_bus=None):
        self.db = db or _default_db
        try:
            from config.settings import settings
            self._max_concurrent = settings.max_concurrent
        except Exception:
            self._max_concurrent = 5
        self._video_service_cls = video_service_cls
        self._task_service_cls = task_service_cls
        self._paused = False
        self._event_bus = event_bus
        self._offline_timer = None  # 防抖定时器
        self._OFFLINE_DEBOUNCE_SEC = 3  # 瞬断防抖窗口

        # 订阅事件总线
        if event_bus is not None:
            from core.utils.event_bus import GO_CONNECTED, GO_DISCONNECTED
            event_bus.subscribe(GO_DISCONNECTED, self._on_go_offline)
            event_bus.subscribe(GO_CONNECTED, self._on_go_online)

    def _on_go_offline(self, event_data=None):
        """Go 离线事件处理：防抖后设置暂停状态

        瞬断（WS 短暂断开后立即重连）不应触发完整暂停序列，
        只在连续离线超过 3 秒后才暂停监控。
        """
        if self._offline_timer is not None:
            self._offline_timer.cancel()

        def _do_pause():
            self._paused = True
            logger.warning("[MonitorService] Go 后端持续离线 >3s，监控已暂停")

        self._offline_timer = threading.Timer(self._OFFLINE_DEBOUNCE_SEC, _do_pause)
        self._offline_timer.daemon = True
        self._offline_timer.start()
        logger.info("[MonitorService] Go 后端离线，3s 防抖窗口中...")

    def _on_go_online(self, event_data=None):
        """Go 恢复事件处理：取消暂停 + 自动恢复 pending 任务"""
        # 取消防抖定时器（如果还在等待中）
        if self._offline_timer is not None:
            self._offline_timer.cancel()
            self._offline_timer = None
            logger.info("[MonitorService] 瞬断恢复，取消暂停（未执行）")

        self._paused = False
        logger.info("[MonitorService] Go 后端恢复，监控继续")

        # 自动恢复 pending 下载任务（断点续传）
        # 注意：resume_pending_tasks() 内部会通过 event_bus legacy emit 发送 TASKS_RESUMED 事件给前端，
        # 不需要在此处重复 emit
        try:
            from core.service.task import resume_pending_tasks
            result = resume_pending_tasks()
            resumed = result.get("resumed", 0)
            failed = result.get("failed", 0)
            if resumed > 0:
                logger.info("[MonitorService] 已恢复 %d 个下载任务（断点续传）", resumed)
            if failed > 0:
                logger.warning("[MonitorService] %d 个任务恢复失败", failed)
        except Exception as e:
            logger.error("[MonitorService] 恢复下载任务失败: %s", e)

    def get_max_concurrent(self) -> int:
        return self._max_concurrent

    def set_max_concurrent(self, count: int) -> bool:
        if count < 1 or count > 20:
            return False
        self._max_concurrent = count
        try:
            from config.settings import settings
            settings.max_concurrent = count
        except Exception:
            pass
        return True

    def get_downloading_tasks(self) -> List[dict]:
        TaskService = self._task_service_cls
        if TaskService is None:
            from core.service.task import TaskService
        task_service = TaskService()
        downloading = task_service.get_downloading_tasks()
        return downloading

    def get_waiting_progress(self) -> str:
        downloading = self.get_downloading_tasks()
        if not downloading:
            return "无正在下载的任务"

        progress_info = []
        for task in downloading:
            video = self.db.get_author_video(task['video_id'])
            title = video.title[:20] if video else task['video_id']
            progress_info.append(f"[{title}...] 状态: {task['status']}")

        return f"等待 {len(downloading)} 个任务完成: " + ", ".join(progress_info)

    def start_monitor(self) -> dict:
        """启动监控

        在后台线程中循环执行：
        1. 同步所有作者最新视频
        2. 找到未下载的视频
        3. 为未下载视频创建下载任务（控制并发数）
        4. 等待当前任务完成后进入下一轮
        """
        global _monitor_running, _monitor_thread

        with _monitor_lock:
            if _monitor_running:
                return {"code": 0, "msg": "监控已在运行中"}
            _monitor_running = True

        _monitor_thread = threading.Thread(
            target=self._monitor_loop,
            daemon=True,
            name="monitor-loop",
        )
        _monitor_thread.start()

        logger.info("[start_monitor] 监控后台线程已启动")
        return {"code": 0, "msg": "监控已启动"}

    def stop_monitor(self, keep_tasks: bool = True) -> dict:
        """停止监控

        Args:
            keep_tasks: 是否保留任务记录用于断点续传（默认 True）
        """
        global _monitor_running

        with _monitor_lock:
            _monitor_running = False

        from core.utils.weixin_client import WechatVideoAPIClient
        from config.settings import settings
        import os

        client = WechatVideoAPIClient()

        # 直接从数据库查询活跃任务，不依赖 Go 后端同步
        # 因为关闭时 Go 后端可能已停止，get_downloading_tasks() 会返回空列表
        running_tasks = self.db.list_download_tasks(status="running", limit=1000)
        pending_tasks = self.db.list_download_tasks(status="pending", limit=1000)
        wait_tasks = self.db.list_download_tasks(status="wait", limit=1000)
        downloading_tasks = running_tasks + pending_tasks + wait_tasks
        task_count = len(downloading_tasks)

        logger.info(f"[stop_monitor] 活跃任务数: running={len(running_tasks)}, pending={len(pending_tasks)}, wait={len(wait_tasks)}, keep_tasks={keep_tasks}")

        for task in downloading_tasks:
            task_id = task.task_id
            video_id = task.video_id

            try:
                client.cancel_task(task_id)
            except Exception as e:
                logger.error(f"[stop_monitor] 取消后端任务失败: {task_id}, error={e}")

            if keep_tasks:
                # 断点续传模式：保留任务记录和部分下载的文件
                # running/wait 状态更新为 pending，pending 状态保持不变
                if task.status in ("running", "wait"):
                    self.db.update_download_task_status(task_id, "pending")
            else:
                # 清理模式：删除任务记录和部分下载的文件
                video = self.db.get_author_video(video_id)
                if video and video.download_path:
                    file_path = os.path.join(video.download_path, f"{video_id}.mp4")
                    if os.path.exists(file_path):
                        try:
                            os.remove(file_path)
                        except Exception as e:
                            logger.error(f"[stop_monitor] 删除文件失败: {file_path}, error={e}")

                self.db.delete_download_task(task_id)

        action = "保留" if keep_tasks else "清理"
        logger.info(f"[stop_monitor] 已停止，{action}了 {task_count} 个任务")
        return {"code": 0, "msg": f"已停止，{action}了 {task_count} 个任务"}

    def is_monitoring(self) -> bool:
        return _monitor_running

    def _monitor_loop(self):
        """后台监控循环 — 滑动窗口并发控制

        每轮：
        1. 同步所有作者最新视频
        2. 收集所有未下载的视频（按 created_at + create_time 降序）
        3. 滑动窗口：同一时刻最多 max_concurrent 个活跃任务
        4. 全部完成后进入下一轮
        """
        VideoService = self._video_service_cls
        TaskService = self._task_service_cls
        if VideoService is None:
            from core.service.video import VideoService
        if TaskService is None:
            from core.service.task import TaskService

        global _monitor_running
        round_num = 0

        try:
            while _monitor_running:
                # 检查暂停状态
                if self._paused:
                    logger.info("[_monitor_loop] 监控已暂停，等待 5 秒后重试...")
                    self._wait_or_stop(5)
                    continue

                round_num += 1
                logger.info(f"[_monitor_loop] === 第 {round_num} 轮监控开始 ===")

                # 1. 同步所有作者最新视频
                video_service = VideoService()
                try:
                    sync_result = video_service.add_all_authors_latest_videos()
                    added = sync_result.get('added', 0)
                    if added > 0:
                        logger.info(f"[_monitor_loop] 同步新增 {added} 个视频")
                except Exception as e:
                    logger.error(f"[_monitor_loop] 同步失败: {e}")

                if not _monitor_running:
                    logger.info("[_monitor_loop] 同步后检测到停止信号，退出")
                    break

                # 2. 收集所有未下载的视频
                authors = self.db.list_authors()
                # 按作者 created_at 降序（创建时间越晚的作者越先下载）
                authors.sort(key=lambda a: a.created_at or "", reverse=True)

                all_undownloaded = []
                author_video_counts = {}
                for author in authors:
                    videos = self.db.list_author_videos(author.id)
                    for video in videos:
                        if not video.is_downloaded:
                            all_undownloaded.append(video)
                    undownloaded_count = sum(1 for v in videos if not v.is_downloaded)
                    if undownloaded_count > 0:
                        author_video_counts[author.name] = undownloaded_count

                # 按视频 create_time 降序（最新的视频优先下载）
                all_undownloaded.sort(key=lambda v: v.create_time or "", reverse=True)

                if not all_undownloaded:
                    self._wait_or_stop(30)
                    continue

                logger.info(f"[_monitor_loop] 未下载视频: {len(all_undownloaded)} 个, 并发={self._max_concurrent}")

                # 3. 滑动窗口：控制并发创建任务
                task_service = TaskService()
                task_index = 0
                created_count = 0
                skipped_count = 0

                while _monitor_running and task_index < len(all_undownloaded):
                    # 获取当前活跃任务数
                    active = task_service.get_downloading_tasks()
                    active_count = len([t for t in active if t.get("status") in ("pending", "running", "wait")])

                    if active_count >= self._max_concurrent:
                        self._wait_or_stop(5)
                        continue

                    # 有空位，创建下一个任务
                    video = all_undownloaded[task_index]
                    task_index += 1

                    try:
                        result = task_service.create_download_task(video.video_id)
                        code = result.get("code")

                        if code == 0:
                            created_count += 1
                        else:
                            skipped_count += 1
                            logger.warning(f"[_monitor_loop] 创建失败: video_id={video.video_id}, code={code}")
                    except Exception as e:
                        skipped_count += 1
                        logger.error(f"[_monitor_loop] 创建异常: video_id={video.video_id}, error={e}")

                logger.info(f"[_monitor_loop] 任务分配: 创建={created_count}, 跳过={skipped_count}")

                if not _monitor_running:
                    logger.info("[_monitor_loop] 任务分配后检测到停止信号，退出")
                    break

                # 4. 等待所有活跃任务完成
                wait_round = 0
                while _monitor_running:
                    wait_round += 1
                    active = self.get_downloading_tasks()
                    active_count = len([t for t in active if t.get("status") in ("pending", "running", "wait")])

                    if active_count == 0:
                        break

                    self._wait_or_stop(5)

                if not _monitor_running:
                    break

                logger.info(f"[_monitor_loop] 第 {round_num} 轮监控完成")

        except Exception as e:
            logger.error(f"[_monitor_loop] 监控循环异常退出: {e}")
        finally:
            _monitor_running = False

    def _wait_or_stop(self, seconds):
        """等待指定秒数，期间检查是否应该停止"""
        global _monitor_running
        for _ in range(seconds):
            if not _monitor_running:
                return
            time.sleep(1)
