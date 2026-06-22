"""全局 SSE 端点

所有实时事件统一通过 /api/events 推送给前端。
后端任何模块调用 event_bus.emit("event_type", data) 即可推送。

事件类型：
- service_status: Go 后端服务状态 + 微信客户端连接状态
- task_completed: 下载完成，更新作者统计
- task_progress: 下载进度更新
"""
import asyncio
import json
import logging
import threading

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from core.utils.event_bus import subscribe, unsubscribe
from core.utils.database import db

logger = logging.getLogger("api_sse")

router = APIRouter(tags=["sse"])

# SSE 连接计数器（用于控制状态推送线程）
_connection_count = 0
_connection_lock = threading.Lock()


@router.get("/api/events")
def sse_endpoint():
    """全局 SSE 端点 — 前端通过此连接接收所有实时事件"""
    global _connection_count

    logger.info("[SSE] 新客户端连接")
    queue = asyncio.Queue()

    def on_event(payload):
        try:
            queue.put_nowait(payload)
        except Exception as e:
            logger.error(f"[SSE] 事件入队失败: {e}")

    subscribe(on_event)

    # 连接数 +1，首次连接时启动状态推送
    with _connection_lock:
        _connection_count += 1
        if _connection_count == 1:
            _start_status_push()

    async def generate():
        try:
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=30)
                except asyncio.TimeoutError:
                    yield ": heartbeat\n\n"
                    continue

                event_type = payload.get("event_type", "unknown")
                sse_data = _transform_event(event_type, payload)

                if sse_data is None:
                    continue

                yield f"event: {event_type}\ndata: {sse_data}\n\n"

        finally:
            unsubscribe(on_event)

            # 连接数 -1，无连接时停止状态推送
            with _connection_lock:
                _connection_count -= 1
                if _connection_count == 0:
                    _stop_status_push()

            logger.info("[SSE] 客户端断开，当前连接数: %d", _connection_count)

    return StreamingResponse(generate(), media_type="text/event-stream")


def _start_status_push():
    """启动状态推送线程"""
    from core.utils.service_status_push import start_status_push
    start_status_push()
    logger.info("[SSE] 状态推送线程已启动")


def _stop_status_push():
    """停止状态推送线程"""
    from core.utils.service_status_push import stop_status_push
    stop_status_push()
    logger.info("[SSE] 状态推送线程已停止")


def _transform_event(event_type: str, payload: dict) -> str | None:
    """根据事件类型，将内部 payload 转换为前端需要的格式

    Returns:
        JSON 字符串，或 None 表示跳过
    """
    if event_type == "task_completed":
        return _transform_task_completed(payload)
    elif event_type == "task_failed":
        return _transform_task_failed(payload)
    elif event_type == "task_progress":
        return _transform_task_progress(payload)
    elif event_type == "service_status":
        return _transform_service_status(payload)
    elif event_type == "import_progress":
        return _transform_import_progress(payload)
    elif event_type == "video_fetch_progress":
        return _transform_video_fetch_progress(payload)
    elif event_type == "delete_author_progress":
        return _transform_delete_author_progress(payload)

    # 未知事件：原样转发
    data = {k: v for k, v in payload.items() if k != "event_type"}
    return json.dumps(data, ensure_ascii=False)


def _transform_service_status(payload: dict) -> str | None:
    """service_status 事件：直接转发"""
    return json.dumps({
        "service_online": payload.get("service_online", False),
        "wechat_connected": payload.get("wechat_connected", False),
    }, ensure_ascii=False)


def _transform_task_completed(payload: dict) -> str | None:
    """task_completed 事件：查 DB 补充作者统计 + 全局统计 + 下载路径

    即使作者已被删除，仍转发基本信息（video_id + 全局统计），
    确保前端能收到完成通知并刷新历史面板。
    """
    author_id = payload.get("author_id", "")
    video_id = payload.get("video_id", "")

    author = db.get_author(author_id) if author_id else None
    if not author and author_id:
        logger.info(f"[SSE] task_completed 作者已删除: {author_id}，仍转发基本信息")

    stats = db.get_author_download_stats(author_id) if author else {"downloaded": 0, "total": 0}
    username = author.source_author_id if author else ""

    video_record = db.get_video(video_id) if video_id else None
    download_path = video_record.download_path if video_record else ""

    return json.dumps({
        "username": username,
        "video_id": video_id,
        "downloaded": stats["downloaded"],
        "total": stats["total"],
        "download_path": download_path,
        "today_count": db.count_videos_today(),
        "today_downloaded": db.count_downloaded_today(),
        "total_videos": db.count_videos_total(),
    }, ensure_ascii=False)


def _transform_task_failed(payload: dict) -> str | None:
    """task_failed 事件：Go 报 done 但文件不存在，通知前端任务失败"""
    return json.dumps({
        "task_id": payload.get("task_id", ""),
        "video_id": payload.get("video_id", ""),
        "error_msg": payload.get("error_msg", ""),
    }, ensure_ascii=False)


def _transform_task_progress(payload: dict) -> str | None:
    """task_progress 事件：转发 WS 进度数据到前端

    终态（done/completed/error）时查 DB 补充 download_path，
    确保前端能立即渲染播放按钮，无需等待 task_completed 事件。
    """
    task_id = payload.get("id")
    video_id = payload.get("video_id", "")
    status = payload.get("status", "")
    if not task_id:
        logger.warning("[SSE] task_progress 无 id，跳过")
        return None

    # [DEBUG] error 状态时记录完整 payload
    if status == "error":
        logger.warning(f"[SSE][DEBUG] task_progress error: task_id={task_id}, video_id={video_id}, "
                      f"error_msg=\"{payload.get('error_msg', '')}\", "
                      f"full_payload_keys={list(payload.keys())}")
        debug_info = {k: v for k, v in payload.items() if k not in ('downloaded', 'speed', 'total_size', 'used', 'uploaded', 'uploadSpeed')}
        logger.warning(f"[SSE][DEBUG] error payload detail: {debug_info}")

    download_path = ""
    if status in ("done", "completed") and video_id:
        try:
            video_record = db.get_video(video_id)
            if video_record and video_record.download_path:
                download_path = video_record.download_path
        except Exception:
            pass

    return json.dumps({
        "id": task_id,
        "video_id": video_id,
        "status": status,
        "downloaded": payload.get("downloaded", 0),
        "speed": payload.get("speed", 0),
        "total_size": payload.get("total_size", 0),
        "download_path": download_path,
        "error_msg": payload.get("error_msg", ""),
    }, ensure_ascii=False)


def _transform_import_progress(payload: dict) -> str | None:
    """import_progress 事件：前端导入进度实时推送"""
    return json.dumps({
        "phase": payload.get("phase", "processing"),
        "total": payload.get("total", 0),
        "current": payload.get("current", 0),
        "name": payload.get("name", ""),
        "success": payload.get("success", 0),
        "fail": payload.get("fail", 0),
        "import_type": payload.get("import_type", ""),
        "imported": payload.get("imported", 0),
        "new_rows": payload.get("new_rows", 0),
    }, ensure_ascii=False)


def _transform_video_fetch_progress(payload: dict) -> str | None:
    """video_fetch_progress 事件：视频获取进度实时推送"""
    return json.dumps({
        "phase": payload.get("phase", "fetching"),
        "current": payload.get("current", 0),
        "total": payload.get("total"),
        "name": payload.get("name", ""),
        "author_name": payload.get("author_name", ""),
        "added": payload.get("added", 0),
        "video_type": payload.get("video_type", ""),
        "short_video_count": payload.get("short_video_count"),
        "replay_count": payload.get("replay_count"),
    }, ensure_ascii=False)


def _transform_delete_author_progress(payload: dict) -> str | None:
    """delete_author_progress 事件：删除作者进度实时推送"""
    return json.dumps({
        "phase": payload.get("phase", "processing"),
        "author_id": payload.get("author_id", ""),
        "author_name": payload.get("author_name", ""),
        "step": payload.get("step", ""),
        "progress": payload.get("progress", 0),
        "tasks_cancelled": payload.get("tasks_cancelled", 0),
        "tasks_total": payload.get("tasks_total", 0),
        "files_deleted": payload.get("files_deleted", 0),
        "files_total": payload.get("files_total", 0),
        "dirs_deleted": payload.get("dirs_deleted", 0),
        "dirs_total": payload.get("dirs_total", 0),
        "videos_count": payload.get("videos_count", 0),
        "total_videos": payload.get("total_videos", 0),
        "total_tasks": payload.get("total_tasks", 0),
        "total_files": payload.get("total_files", 0),
        "total_dirs": payload.get("total_dirs", 0),
        "error": payload.get("error", ""),
    }, ensure_ascii=False)
