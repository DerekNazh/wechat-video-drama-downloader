
"""下载进度 WebSocket 监听器"""
import json
import logging
import threading
import websocket
from typing import Optional, Callable

logger = logging.getLogger("socket_client")


class DownloadProgressListener:
    """下载进度 WebSocket 监听器"""

    def __init__(self, base_url: str = "ws://127.0.0.1:2022", event_bus=None):
        self.base_url = base_url
        self.ws = None
        self._running = False
        self._thread = None
        self._callback: Optional[Callable] = None
        self._event_bus = event_bus

    def start(self, on_progress: Callable[[dict], None]):
        """启动监听

        Args:
            on_progress: 回调函数，接收任务进度 dict
        """
        if self._running:
            return
        self._callback = on_progress
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        logger.info("[DownloadProgressListener] 已启动")

    def _run(self):
        try:
            self.ws = websocket.WebSocketApp(
                f"{self.base_url}/ws/downloader",
                on_message=self._on_message,
                on_error=self._on_error,
                on_close=self._on_close,
            )
            self.ws.on_open = self._on_open
            self.ws.run_forever()
        except Exception as e:
            logger.error(f"[DownloadProgressListener] 异常: {e}")

    def _on_open(self, ws):
        logger.info("[DownloadProgressListener] WebSocket 已连接")
        if self._event_bus:
            self._event_bus.set_go_online(True)

    def _normalize_and_callback(self, task):
        """标准化任务数据并回调

        Go 后端 progress 字段有两种格式：
        - 运行中: dict {"used":..., "speed":..., "downloaded":...}
        - 完成: int 100
        """
        raw_progress = task.get("progress", {})
        if isinstance(raw_progress, dict):
            progress = raw_progress
        else:
            progress = {}

        meta = task.get("meta") or {}
        meta_res = meta.get("res") or {}
        total_size = meta_res.get("size", 0) if isinstance(meta_res, dict) else 0
        labels = (meta.get("req") or {}).get("labels") or {}
        video_id = labels.get("id", "")

        # labels 中可能没有 video_id（直播回放等），从数据库补查
        if not video_id:
            task_id = task.get("id")
            if task_id:
                try:
                    from core.utils.database import db
                    dl_task = db.get_download_task(task_id)
                    if dl_task and dl_task.video_id:
                        video_id = dl_task.video_id
                except Exception:
                    pass

        normalized = {
            "id": task.get("id"),
            "video_id": video_id,
            "name": task.get("name"),
            "status": task.get("status"),
            "used": progress.get("used", 0),
            "speed": progress.get("speed", 0),
            "downloaded": progress.get("downloaded", 0),
            "total_size": total_size,
            "uploadSpeed": progress.get("uploadSpeed", 0),
            "uploaded": progress.get("uploaded", 0),
            "error_msg": task.get("error", ""),
            "createdAt": task.get("createdAt"),
            "updatedAt": task.get("updatedAt"),
        }

        # error 状态时记录 Go 后端的错误信息
        status = task.get("status", "")
        if status == "error":
            task_error = task.get("error", "")
            logger.warning(f"[WS] 任务错误: id={task.get('id')}, video_id={video_id}, "
                          f"error=\"{task_error}\", name={task.get('name', '')}")
            # [DEBUG] 记录完整 meta 信息用于诊断
            meta_info = task.get("meta", {})
            if isinstance(meta_info, dict):
                req_info = meta_info.get("req", {})
                res_info = meta_info.get("res", {})
                opts_info = meta_info.get("opts", {})
                logger.warning(f"[WS][DEBUG] error任务meta: req_keys={list(req_info.keys()) if isinstance(req_info, dict) else 'N/A'}, "
                              f"res={res_info}, opts_path={opts_info.get('path', '') if isinstance(opts_info, dict) else 'N/A'}, "
                              f"opts_name={opts_info.get('name', '')[:80] if isinstance(opts_info, dict) else 'N/A'}")

        # 终态时立即写 DB + 触发事件总线，确保 SSE 转发时 DB 已有 download_path
        status = task.get("status", "")
        if status in ("done", "completed") and video_id:
            try:
                from core.utils.database import db
                video_record = db.get_author_video(video_id)
                if video_record and not video_record.is_downloaded:
                    opts = (meta.get("opts") or {}) if isinstance(meta, dict) else {}
                    dir_path = opts.get("path", "")
                    file_name = opts.get("name", "")
                    if dir_path and file_name:
                        from pathlib import Path
                        full_path = str(Path(dir_path) / file_name)
                        import os
                        if os.path.isfile(full_path):
                            db.update_video_downloaded(video_id, full_path)
                            logger.debug(f"[WS] 标记视频已下载: {video_id}, path={full_path}")
                            author = db.get_author(video_record.author_id) if video_record.author_id else None
                            if author:
                                from core.utils.event_bus import emit_task_completed
                                emit_task_completed({"video_id": video_id, "author_id": video_record.author_id})
            except Exception as e:
                logger.debug(f"[WS] 终态处理异常(非致命): {e}")

            # 记录任务完成（非阻塞，防止双触发点重复写入）
            try:
                from core.utils.database import get_database
                _db = get_database()
                if not _db.has_recent_log(video_id, 60):
                    _video_rec = _db.get_author_video(video_id)
                _author_id = _video_rec.author_id if _video_rec else ''
                _username = ''
                if _author_id:
                    _author = _db.get_author(_author_id)
                    _username = _author.source_author_id if _author else ''
                _db.log_task_completion(
                    video_id=video_id,
                    author_id=_author_id,
                    username=_username,
                    title=task.get('name', ''),
                    cover_url=_video_rec.cover_url if _video_rec else '',
                    duration=_video_rec.duration if _video_rec else 0,
                    file_size=total_size,
                )
            except Exception as _le:
                logger.debug(f"[WS] 记录完成日志失败(非致命): {_le}")

        self._callback(normalized)

    def _on_message(self, ws, message):
        try:
            data = json.loads(message)
            msg_type = data.get("type")
            if msg_type == "event":
                event_data = data.get("data", {})
                ws_error = data.get("error")
                task = event_data.get("task") or event_data.get("Task") if isinstance(event_data, dict) else None
                if task:
                    task_status = task.get('status', '')
                    if task_status == "error":
                        task_error = task.get("error", "")
                        logger.warning(f"[WS] 任务error: id={task.get('id')}, error=\"{task_error}\"")
                if ws_error:
                    logger.warning(f"[DownloadProgressListener] WS消息含error字段: {ws_error}")
                if task and self._callback:
                    self._normalize_and_callback(task)
            elif msg_type == "batch_tasks":
                tasks = data.get("data", [])
                if tasks and self._callback:
                    for task in tasks:
                        self._normalize_and_callback(task)
            else:
                logger.warning(f"[DownloadProgressListener] 未知消息类型: type={msg_type}")
        except Exception as e:
            logger.error(f"[DownloadProgressListener] 解析消息失败: {e}")

    def _on_error(self, ws, error):
        logger.error(f"[DownloadProgressListener] 错误: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        logger.info("[DownloadProgressListener] WebSocket 已关闭")
        if self._event_bus:
            self._event_bus.set_go_online(False)

    def stop(self):
        """停止监听"""
        self._running = False
        if self.ws:
            self.ws.close()
        logger.info("[DownloadProgressListener] 已停止")
