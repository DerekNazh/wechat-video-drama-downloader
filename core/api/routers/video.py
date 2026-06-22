"""视频 API 路由"""
import logging
from urllib.parse import unquote

import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from typing import Optional
from pydantic import BaseModel

from core.service.video import VideoService
from core.utils.database import db
from core.api.deps import require_wechat

logger = logging.getLogger("api_video")

router = APIRouter(prefix="/api/video", tags=["video"])

_http_client = None


def _get_http_client():
    global _http_client
    if _http_client is None:
        _http_client = httpx.Client(timeout=15, follow_redirects=True)
    return _http_client


class AddVideoRequest(BaseModel):
    author_id: str
    pages: int = 1


class BatchDeleteRequest(BaseModel):
    video_ids: list[str]


@router.get("/all")
def get_all_authors_with_videos():
    """获取所有作者及其视频"""
    try:
        service = VideoService()
        result = service.get_all_authors_with_videos()

        # 转换为 dict 格式
        data = []
        for item in result:
            author = item.get("author")
            videos = item.get("videos", [])

            data.append({
                "author": {
                    "id": author.id,
                    "source_author_id": author.source_author_id,
                    "name": author.name,
                    "tag": author.tag,
                    "bio": author.bio,
                    "avatar_url": author.avatar_url,
                    "cover_img_url": author.cover_img_url,
                    "created_at": author.created_at,
                    "updated_at": author.updated_at,
                },
                "videos": [
                    {
                        "video_id": v.video_id,
                        "author_id": v.author_id,
                        "title": v.title,
                        "object_nonce_id": v.object_nonce_id,
                        "url": v.url,
                        "spec": v.spec,
                        "file_size": v.file_size,
                        "cover_url": v.cover_url,
                        "decode_key": v.decode_key,
                        "author_avatar": v.author_avatar,
                        "duration": v.duration,
                        "create_time": v.create_time,
                        "is_downloaded": v.is_downloaded,
                        "download_path": v.download_path,
                        "video_type": v.video_type,
                    }
                    for v in videos
                ]
            })

        return {"code": 0, "data": data, "msg": ""}
    except Exception as e:
        return {"code": -1, "msg": str(e)}


@router.get("/author/{author_id}")
def get_author_videos(author_id: str, video_type: Optional[str] = None):
    """获取指定作者的所有视频，可选按 video_type 过滤"""
    try:
        service = VideoService()

        if video_type:
            videos = service.get_author_videos_by_type(author_id, video_type)
        else:
            videos = service.get_author_videos(author_id)

        data = [
            {
                "video_id": v.video_id,
                "author_id": v.author_id,
                "title": v.title,
                "object_nonce_id": v.object_nonce_id,
                "url": v.url,
                "spec": v.spec,
                "file_size": v.file_size,
                "cover_url": v.cover_url,
                "decode_key": v.decode_key,
                "author_avatar": v.author_avatar,
                "duration": v.duration,
                "create_time": v.create_time,
                "is_downloaded": v.is_downloaded,
                "download_path": v.download_path,
                "video_type": v.video_type,
            }
            for v in videos
        ]

        type_stats = db.get_author_video_type_stats(author_id)

        return {
            "code": 0,
            "data": data,
            "stats": type_stats,
            "msg": "",
        }
    except Exception as e:
        return {"code": -1, "msg": str(e)}


@router.get("/{video_id}")
def get_video_detail(video_id: str):
    """获取视频详情"""
    try:
        service = VideoService()
        video = service.get_video_detail(video_id)

        if not video:
            return {"code": -1, "msg": "视频不存在", "data": None}

        data = {
            "video_id": video.video_id,
            "author_id": video.author_id,
            "title": video.title,
            "object_nonce_id": video.object_nonce_id,
            "url": video.url,
            "spec": video.spec,
            "file_size": video.file_size,
            "cover_url": video.cover_url,
            "decode_key": video.decode_key,
            "author_avatar": video.author_avatar,
            "duration": video.duration,
            "create_time": video.create_time,
            "is_downloaded": video.is_downloaded,
            "download_path": video.download_path,
            "video_type": video.video_type,
        }

        return {"code": 0, "data": data, "msg": ""}
    except Exception as e:
        return {"code": -1, "msg": str(e)}


@router.post("/author/{author_id}/add", dependencies=[Depends(require_wechat)])
def add_author_latest_videos(author_id: str):
    """新增作者最新视频"""
    try:
        service = VideoService()
        result = service.add_author_latest_videos(author_id)
        return {"code": 0, "data": result, "msg": ""}
    except Exception as e:
        return {"code": -1, "msg": str(e)}


@router.post("/add-all", dependencies=[Depends(require_wechat)])
def add_all_authors_videos():
    """新增所有作者最新视频"""
    try:
        service = VideoService()
        result = service.add_all_authors_latest_videos()
        return {"code": 0, "data": result, "msg": ""}
    except Exception as e:
        return {"code": -1, "msg": str(e)}


@router.post("/sync-new", dependencies=[Depends(require_wechat)])
def sync_new_videos():
    """轮询同步：同步所有作者最新视频，只返回新增的视频详情

    用于前端定时轮询，增量更新视频列表。
    """
    try:
        service = VideoService()
        result = service.sync_and_get_new_videos()
        return {"code": 0, "data": result, "msg": ""}
    except Exception as e:
        return {"code": -1, "msg": str(e)}


@router.delete("/{video_id}")
def delete_video(video_id: str):
    """删除视频"""
    try:
        service = VideoService()
        success = service.delete_video(video_id)

        if success:
            return {"code": 0, "msg": "删除成功"}
        else:
            return {"code": -1, "msg": "删除失败"}
    except Exception as e:
        return {"code": -1, "msg": str(e)}


@router.post("/batch-delete")
def batch_delete_videos(request: BatchDeleteRequest):
    """批量删除视频"""
    try:
        service = VideoService()
        result = service.delete_videos(request.video_ids)
        return {"code": 0, "data": result, "msg": ""}
    except Exception as e:
        return {"code": -1, "msg": str(e)}


@router.delete("/author/{author_id}/all")
def delete_author_all_videos(author_id: str):
    """删除作者：验证后启动后台线程执行删除，通过 SSE 推送进度"""
    import threading
    from pathlib import Path

    logger.info(f"[delete_author_all] 收到请求: author_id={author_id}")

    author = db.get_author(author_id)
    if not author:
        logger.warning(f"[delete_author_all] 作者不存在: author_id={author_id}")
        return {"code": -1, "msg": f"作者不存在: {author_id}"}

    videos = db.list_author_videos(author_id)
    video_ids = [v.video_id for v in videos]
    logger.info(f"[delete_author_all] 作者={author.name or author.source_author_id}, 视频数={len(video_ids)}, author_id={author_id}")

    # 计算工作量（包含所有未完成任务：running/wait/pending/paused）
    total_tasks = 0
    try:
        for task in db.list_download_tasks(status=None):
            if task.video_id in video_ids and task.status in ("running", "wait", "pending", "paused"):
                total_tasks += 1
    except Exception:
        pass

    total_files = sum(1 for v in videos if v.download_path)
    # 收集作者根目录（下载/作者名/），而非视频类型子目录
    download_root = None
    try:
        from config.settings import settings
        download_root = Path(str(settings.wx_download_dir)).resolve()
    except Exception:
        pass
    author_dir_paths = set()
    for v in videos:
        if v.download_path:
            try:
                p = Path(v.download_path).resolve()
                if download_root and str(p).startswith(str(download_root)):
                    rel = p.relative_to(download_root)
                    author_dir_paths.add(download_root / rel.parts[0])
            except Exception:
                pass
    total_dirs = len(author_dir_paths)

    from core.utils.event_bus import emit as emit_event
    emit_event("delete_author_progress", {
        "phase": "start",
        "author_id": author_id,
        "author_name": author.name or unquote(author.source_author_id) if author.source_author_id else "",
        "total_tasks": total_tasks,
        "total_files": total_files,
        "total_dirs": total_dirs,
        "total_videos": len(video_ids),
    })

    thread = threading.Thread(
        target=_do_delete_author_all,
        args=(author_id, author.name or unquote(author.source_author_id) if author.source_author_id else "", video_ids, videos, total_tasks, total_files, total_dirs),
        daemon=True,
    )
    thread.start()

    return {"code": 0, "msg": "删除已启动", "data": {"author_id": author_id}}


def _do_delete_author_all(author_id: str, author_name: str, video_ids: list, videos: list, total_tasks: int, total_files: int, total_dirs: int):
    """后台线程执行删除逻辑，通过 event_bus 推送进度"""
    import shutil
    from pathlib import Path
    from core.utils.event_bus import emit as emit_event

    _logger = logging.getLogger("api_delete_author_all_thread")

    tasks_cancelled = 0
    files_deleted = 0
    dirs_deleted = 0

    try:
        # Step 1: 立即停止该作者所有活跃任务（含 running/wait/pending/paused）
        emit_event("delete_author_progress", {
            "phase": "processing", "author_id": author_id, "step": "cancel_tasks",
            "progress": 5, "tasks_cancelled": 0, "tasks_total": total_tasks,
        })
        active_statuses = ("running", "wait", "pending", "paused")
        try:
            from core.service.task import TaskService
            task_service = TaskService()
            for task in db.list_download_tasks(status=None):
                if task.video_id not in video_ids or task.status not in active_statuses:
                    continue
                try:
                    task_service.delete_task(task.task_id)
                    tasks_cancelled += 1
                except Exception as e:
                    _logger.warning(f"[delete_author_all] 取消任务失败: {task.task_id}, {e}")
                pct = 5 + int(tasks_cancelled / max(total_tasks, 1) * 20)
                emit_event("delete_author_progress", {
                    "phase": "processing", "author_id": author_id, "step": "cancel_tasks",
                    "progress": pct, "tasks_cancelled": tasks_cancelled, "tasks_total": total_tasks,
                })
        except Exception as e:
            _logger.warning(f"[delete_author_all] 取消任务异常: {e}")

        # Step 1.5: 清理该作者所有任务记录（含已取消/done 等）
        try:
            cleaned = 0
            for task in db.list_download_tasks(status=None):
                if task.video_id in video_ids:
                    db.delete_download_task(task.task_id)
                    cleaned += 1
            if cleaned > 0:
                _logger.info(f"[delete_author_all] 已清理 {cleaned} 个任务记录")
        except Exception as e:
            _logger.warning(f"[delete_author_all] 清理任务记录异常: {e}")

        emit_event("delete_author_progress", {
            "phase": "processing", "author_id": author_id, "step": "cancel_tasks",
            "progress": 25, "tasks_cancelled": tasks_cancelled, "tasks_total": total_tasks,
        })

        # 2. 删除视频文件 + 数据库记录 (25% → 70%)
        # 收集作者根目录（下载/作者名/），而非视频类型子目录（下载/作者名/直播回放/）
        download_root = None
        try:
            from config.settings import settings
            download_root = Path(str(settings.wx_download_dir)).resolve()
        except Exception:
            pass

        author_dirs = set()
        for i, v in enumerate(videos):
            if v.download_path:
                try:
                    p = Path(v.download_path).resolve()
                    # 向上遍历到下载根目录的直接子目录（即作者根目录）
                    if download_root and str(p).startswith(str(download_root)):
                        rel = p.relative_to(download_root)
                        # rel.parts[0] 就是作者名目录（如 "女子象棋大师单欣"）
                        author_root = download_root / rel.parts[0]
                        author_dirs.add(author_root)
                    if p.exists():
                        p.unlink()
                        files_deleted += 1
                except Exception:
                    pass
            if v.video_id:
                db.delete_author_video(v.video_id)

            pct = 25 + int((i + 1) / max(len(videos), 1) * 45)
            emit_event("delete_author_progress", {
                "phase": "processing", "author_id": author_id, "step": "delete_files",
                "progress": pct, "files_deleted": i + 1, "files_total": len(videos),
            })

        emit_event("delete_author_progress", {
            "phase": "processing", "author_id": author_id, "step": "delete_files",
            "progress": 70, "files_deleted": len(videos), "files_total": len(videos),
        })

        # 3. 删除作者文件夹 (70% → 90%)
        for i, author_dir in enumerate(author_dirs):
            try:
                if author_dir.exists():
                    shutil.rmtree(str(author_dir))
                    dirs_deleted += 1
                    _logger.info(f"[delete_author_all] 已删除作者文件夹: {author_dir}")
            except Exception as e:
                _logger.warning(f"[delete_author_all] 删除文件夹失败: {author_dir}, {e}")
            pct = 70 + int((i + 1) / max(len(author_dirs), 1) * 20)
            emit_event("delete_author_progress", {
                "phase": "processing", "author_id": author_id, "step": "delete_dirs",
                "progress": pct, "dirs_deleted": i + 1, "dirs_total": len(author_dirs),
            })

        emit_event("delete_author_progress", {
            "phase": "processing", "author_id": author_id, "step": "delete_dirs",
            "progress": 90, "dirs_deleted": dirs_deleted, "dirs_total": len(author_dirs),
        })

        # 4. 删除作者记录 (90% → 95%)
        emit_event("delete_author_progress", {
            "phase": "processing", "author_id": author_id, "step": "delete_records",
            "progress": 95,
        })
        db.delete_author(author_id)

        # done
        emit_event("delete_author_progress", {
            "phase": "done", "author_id": author_id, "author_name": author_name,
            "progress": 100, "videos_count": len(video_ids),
            "files_deleted": files_deleted, "dirs_deleted": dirs_deleted,
            "tasks_cancelled": tasks_cancelled,
        })

        _logger.info(f"[delete_author_all] 删除完成: {author_id}, videos={len(video_ids)}, files={files_deleted}, dirs={dirs_deleted}, tasks={tasks_cancelled}")

    except Exception as e:
        _logger.error(f"[delete_author_all] 线程异常: {e}")
        emit_event("delete_author_progress", {
            "phase": "done", "author_id": author_id, "author_name": author_name,
            "progress": 0, "error": str(e),
            "videos_count": len(video_ids), "files_deleted": files_deleted,
            "dirs_deleted": dirs_deleted, "tasks_cancelled": tasks_cancelled,
        })


# ==================== 图片代理 ====================

@router.get("/cover/{username}/{video_id}")
def get_cover(username: str, video_id: str):
    """代理获取视频封面图

    通过 Python 后端代理图片数据，避免浏览器直连微信域名走代理失败。
    """
    try:
        video = db.get_author_video(video_id)
        if not video or not video.cover_url:
            return Response(status_code=404)

        client = _get_http_client()
        resp = client.get(video.cover_url)
        if resp.status_code == 200:
            content_type = resp.headers.get("content-type", "image/jpeg")
            return Response(
                content=resp.content,
                media_type=content_type,
                headers={"Cache-Control": "public, max-age=86400"},
            )
        logger.warning(f"[get_cover] 上游返回 {resp.status_code}: {video.cover_url}")
    except Exception as e:
        logger.error(f"[get_cover] 代理失败: {e}")
    return Response(status_code=404)


@router.get("/avatar/{username}")
def get_avatar(username: str):
    """代理获取作者头像

    通过 Python 后端代理图片数据，避免浏览器直连 wx.qlogo.cn 走代理失败。
    """
    try:
        author = db.get_author_by_source_id(username)
        if not author or not author.avatar_url:
            return Response(status_code=404)

        client = _get_http_client()
        resp = client.get(author.avatar_url)
        if resp.status_code == 200:
            content_type = resp.headers.get("content-type", "image/jpeg")
            return Response(
                content=resp.content,
                media_type=content_type,
                headers={"Cache-Control": "public, max-age=86400"},
            )
        logger.warning(f"[get_avatar] 上游返回 {resp.status_code}: {author.avatar_url}")
    except Exception as e:
        logger.error(f"[get_avatar] 代理失败: {e}")
    return Response(status_code=404)