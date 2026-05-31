"""任务 API 路由"""
import logging
from typing import Optional
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from core.service.task import TaskService
from core.utils.database import db
from core.api.deps import require_wechat, require_go_online

logger = logging.getLogger("api_task")

router = APIRouter(
    prefix="/api/task",
    tags=["task"],
)


class CancelTaskRequest(BaseModel):
    task_id: str


class BatchCreateRequest(BaseModel):
    video_ids: list[str]


class DownloadAllRequest(BaseModel):
    author_id: Optional[str] = None
    video_type: Optional[str] = None


@router.get("/list", dependencies=[Depends(require_go_online)])
def get_downloading_tasks():
    """获取所有当前正在下载的任务（只要求 Go 在线，不要求微信连接）"""
    try:
        service = TaskService()
        tasks = service.get_downloading_tasks()
        return {"code": 0, "data": {"list": tasks}, "msg": ""}
    except Exception as e:
        logger.error(f"[get_downloading_tasks] 获取失败: {e}")
        return {"code": -1, "msg": str(e)}


@router.post("/batch-create", dependencies=[Depends(require_wechat)])
def batch_create_tasks(request: BatchCreateRequest):
    """批量创建下载任务"""
    try:
        service = TaskService()
        count = 0
        consecutive_failures = 0
        total = len(request.video_ids)
        for video_id in request.video_ids:
            result = service.create_download_task(video_id)
            if result.get("code") == 0:
                count += 1
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                # 连续失败 3 次：检查 Go 是否已离线，离线则提前退出
                if consecutive_failures >= 3:
                    from core.utils.weixin_client import WechatVideoAPIClient
                    if not WechatVideoAPIClient().check_service():
                        logger.warning(f"[batch_create_tasks] Go 已离线，提前退出: 已创建 {count}/{total}")
                        break
                    consecutive_failures = 0
        return {"code": 0, "data": {"count": count, "total": total}, "msg": ""}
    except Exception as e:
        logger.error(f"[batch_create_tasks] 批量创建失败: {e}")
        return {"code": -1, "msg": str(e)}


@router.post("/download-all", dependencies=[Depends(require_wechat)])
def download_all_videos(request: DownloadAllRequest):
    """下载全部未下载视频，可按作者和/或视频类型筛选

    不传参数则下载所有未下载视频；
    传 author_id 则只下载该作者的未下载视频；
    传 video_type 则只下载该类型的未下载视频。
    """
    try:
        service = TaskService()

        # 获取所有未下载视频
        all_videos = db.list_undownloaded_videos(limit=10000)

        # 按 author_id 过滤
        if request.author_id:
            all_videos = [v for v in all_videos if v.author_id == request.author_id]

        # 按 video_type 过滤
        if request.video_type:
            all_videos = [v for v in all_videos if v.video_type == request.video_type]

        count = 0
        consecutive_failures = 0
        total = len(all_videos)
        for video in all_videos:
            result = service.create_download_task(video.video_id)
            if result.get("code") == 0:
                count += 1
                consecutive_failures = 0
            else:
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    from core.utils.weixin_client import WechatVideoAPIClient
                    if not WechatVideoAPIClient().check_service():
                        logger.warning(f"[download_all_videos] Go 已离线，提前退出: 已创建 {count}/{total}")
                        break
                    consecutive_failures = 0

        return {"code": 0, "data": {"count": count, "total": total}, "msg": ""}
    except Exception as e:
        logger.error(f"[download_all_videos] 全部下载失败: {e}")
        return {"code": -1, "msg": str(e)}


@router.post("/cancel", dependencies=[Depends(require_go_online)])
def cancel_task(request: CancelTaskRequest):
    """停止单个正在下载任务"""
    try:
        service = TaskService()
        success = service.delete_task(request.task_id)
        if success:
            return {"code": 0, "msg": "任务已停止"}
        else:
            return {"code": -1, "msg": "任务不存在或停止失败"}
    except Exception as e:
        logger.error(f"[cancel_task] 停止失败: {e}")
        return {"code": -1, "msg": str(e)}


@router.post("/cancel-all", dependencies=[Depends(require_go_online)])
def cancel_all_tasks():
    """停止所有正在下载任务"""
    try:
        service = TaskService()
        tasks = service.get_downloading_tasks()

        success_count = 0
        fail_count = 0

        for task in tasks:
            if service.delete_task(task.get("task_id", "")):
                success_count += 1
            else:
                fail_count += 1

        return {
            "code": 0,
            "data": {
                "success_count": success_count,
                "fail_count": fail_count
            },
            "msg": ""
        }
    except Exception as e:
        logger.error(f"[cancel_all_tasks] 停止失败: {e}")
        return {"code": -1, "msg": str(e)}


@router.get("/completion-log")
async def get_completion_log(limit: int = 50, offset: int = 0):
    """获取任务完成记录"""
    if limit < 1:
        limit = 50
    if limit > 100:
        limit = 100
    if offset < 0:
        offset = 0

    items = db.get_task_logs(limit, offset)
    total = db.count_task_logs()

    return {"code": 0, "data": {"total": total, "items": items}}


@router.delete("/{task_id}", dependencies=[Depends(require_go_online)])
def delete_task(task_id: str):
    """删除正在下载任务"""
    try:
        service = TaskService()
        success = service.delete_task(task_id)
        if success:
            return {"code": 0, "msg": "任务已删除"}
        else:
            return {"code": -1, "msg": "任务不存在或删除失败"}
    except Exception as e:
        logger.error(f"[delete_task] 删除失败: {e}")
        return {"code": -1, "msg": str(e)}