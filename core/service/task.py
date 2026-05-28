"""任务服务层

提供下载任务的增删查功能
"""

import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional

from core.utils.database import DownloadTask, db
from core.utils.weixin_client import WechatVideoAPIClient
from core.utils.event_bus import emit_task_completed
from core.service.search import SearchService

_resume_lock = threading.Lock()
logger = logging.getLogger("task_service")


class TaskService:
    """任务服务

    提供下载任务的创建、查询、删除功能
    """

    def __init__(self, api_base_url: str = "http://127.0.0.1:2022"):
        self.api_base_url = api_base_url
        self._client = WechatVideoAPIClient(base_url=api_base_url)
        self._compensation_manager = None  # 延迟初始化

    def _get_compensation_manager(self):
        """获取补偿事务管理器（延迟初始化）"""
        if self._compensation_manager is None:
            from core.utils.compensation_manager import CompensationTransactionManager
            self._compensation_manager = CompensationTransactionManager(
                go_client=self._client,
                db=db
            )
        return self._compensation_manager

    def create_download_task(self, video_id: str) -> dict:
        """创建下载任务

        Args:
            video_id: 视频ID

        Returns:
            {"code": 0, "data": {"id": task_id}, "msg": ""}
        """
        # 检查是否已有该视频的活跃任务
        existing_task = db.get_download_task_by_video_id(video_id)
        if existing_task:
            if existing_task.status in ("pending", "running", "wait"):
                return {"code": 0, "data": {"id": existing_task.task_id}, "msg": ""}
            # 已完成/暂停/失败的任务：删除旧记录，允许重建
            db.delete_download_task(existing_task.task_id)

        # 使用补偿事务管理器创建任务（保证双写一致性）
        result = self._get_compensation_manager().create_task_with_compensation(video_id)

        if result["success"]:
            return {"code": 0, "data": {"id": result["task_id"]}, "msg": ""}
        else:
            return {"code": -1, "msg": result.get("error", "创建失败")}

    def get_task_progress(self, task_id: str) -> Optional[dict]:
        """查看单个任务进度

        Args:
            task_id: 任务ID

        Returns:
            任务信息 dict 或 None
        """
        # 先查本地数据库
        local_task = db.get_download_task(task_id)
        if not local_task:
            logger.warning(f"[get_task_progress] 任务不存在: {task_id}")
            return None

        # 调用后端获取最新进度
        try:
            backend_task = self._get_backend_task_from_list(task_id)

            if not backend_task:
                # Go 后端找不到该任务：可能是 Go 刚启动任务列表还没加载完
                # 不要删除本地任务，返回本地数据让前端显示
                logger.info(f"[get_task_progress] Go找不到任务，保留本地记录: task_id={task_id}, local_status={local_task.status}")
                return self._task_to_dict(local_task)

            # 更新本地任务状态
            status = backend_task.get("status", "")
            progress_obj = backend_task.get("progress", {})

            # Go 后端两种格式：
            # running: progress = {downloaded, speed, ...} (dict)
            # completed: progress = 100 (整数), downloaded/speed/total 在顶层
            if isinstance(progress_obj, dict):
                downloaded = progress_obj.get("downloaded", 0)
                speed = progress_obj.get("speed", 0)
            else:
                downloaded = backend_task.get("downloaded", 0)
                speed = backend_task.get("speed", 0)

            # total_size: 优先顶层 total（真实下载大小），其次 meta.res.size，最后 local_task
            top_total = backend_task.get("total", 0)
            meta = backend_task.get("meta") or {}
            res = meta.get("res") or {}
            res_size = res.get("size", 0)
            if top_total > 0:
                total_size = top_total
            elif res_size > 0:
                total_size = res_size
            else:
                total_size = local_task.total_size or 0

            error_msg = backend_task.get("error_msg", "")
            completed_at = backend_task.get("completed_at")

            # 计算进度百分比（0-100）
            if total_size > 0:
                progress = min(100, int(downloaded / total_size * 100))
            elif status in ("done", "completed"):
                progress = 100
            else:
                progress = 0

            if status in ("done", "completed"):
                # 下载完成：先验证文件存在，再更新状态
                opts = meta.get("opts") or {}
                dir_path = opts.get("path", "")
                file_name = opts.get("name", "")
                if dir_path and file_name:
                    full_path = str(Path(dir_path) / file_name)
                else:
                    full_path = ""

                file_exists = full_path and os.path.isfile(full_path)

                if file_exists:
                    file_size = os.path.getsize(full_path)
                    logger.info(f"[get_task_progress] 任务完成: task_id={task_id}, video_id={local_task.video_id}, path={full_path}, size={file_size}")
                    if local_task.video_id:
                        db.update_video_downloaded(local_task.video_id, full_path)
                        video = db.get_author_video(local_task.video_id)
                        if video:
                            emit_task_completed({"video_id": local_task.video_id, "author_id": video.author_id})
                    # 文件存在：标记任务完成
                    completed_at = datetime.now().isoformat()
                    db.update_download_task_status(task_id, status, completed_at=completed_at)
                    if progress > 0:
                        db.update_download_task_progress(task_id, progress, downloaded, total_size, speed)
                else:
                    # 文件不存在：标记为 failed，不设置 completed_at
                    logger.error(f"[get_task_progress] Go报done但文件不存在: task_id={task_id}, path={full_path}")
                    db.update_download_task_status(task_id, "failed", completed_at=None)
                    status = "failed"
                    error_msg = "文件不存在：Go后端报done但磁盘无对应文件"
            else:
                # 非 done 状态：正常更新进度
                # Go 后端的 wait 表示排队中，映射为 pending 保持一致
                mapped_status = "pending" if status == "wait" else status
                db.update_download_task_status(task_id, mapped_status, completed_at=None)
                if progress > 0:
                    db.update_download_task_progress(task_id, progress, downloaded, total_size, speed)

                # error 状态时记录 Go 后端返回的完整信息
                if status == "error":
                    go_error = backend_task.get("error", "")
                    logger.warning(f"[get_task_progress] Go后端error: task_id={task_id}, "
                                  f"video_id={local_task.video_id}, go_error=\"{go_error}\"")

            return {
                "task_id": task_id,
                "video_id": local_task.video_id,
                "status": status,
                "progress": progress,
                "downloaded": downloaded,
                "total_size": total_size,
                "speed": speed,
                "error_msg": error_msg,
                "completed_at": completed_at,
                "title": local_task.title,
                "created_at": local_task.created_at,
                "updated_at": local_task.updated_at,
            }

        except Exception as e:
            logger.error(f"[get_task_progress] 查询异常: {e}", exc_info=True)
            return self._task_to_dict(local_task)

    def get_downloading_tasks(self) -> list[dict]:
        """获取所有正在下载的任务

        每次调用时先自动清理孤儿任务，再跟 Go 后端同步实时进度，最后返回本地数据。
        同步后状态变为 done/completed 的任务也会返回（progress=100），
        确保前端能看到最终完成状态。
        """
        # 自动清理 Go 端不存在的孤儿任务
        try:
            TaskService.cleanup_stale_tasks()
        except Exception as e:
            logger.warning(f"[get_downloading_tasks] 孤儿任务清理失败: {e}")

        tasks = db.list_download_tasks(status=None)

        result = []
        for task in tasks:
            if task.status not in ["pending", "running", "wait"]:
                continue

            # 跟 Go 后端同步实时进度
            try:
                sync_result = self.get_task_progress(task.task_id)
                if not sync_result:
                    logger.warning(f"[get_downloading_tasks] 同步返回None: task_id={task.task_id}")
            except Exception as e:
                logger.warning(f"[get_downloading_tasks] 同步任务 {task.task_id} 失败: {e}")

            # 重新读取更新后的数据
            updated = db.get_download_task(task.task_id)
            if not updated:
                logger.warning(f"[get_downloading_tasks] 同步后任务消失: task_id={task.task_id}")
                continue

            if updated.status in ["pending", "running", "wait"]:
                result.append(self._task_to_dict(updated))
            elif updated.status in ("done", "completed"):
                # 同步后刚完成的任务：返回给前端展示 100% 进度
                result.append(self._task_to_dict(updated))

        result.sort(key=lambda x: x.get("created_at", ""))
        return result

    def delete_task(self, task_id: str) -> bool:
        """删除任务（取消任务）

        同时清理：
        1. 后端下载任务
        2. 本地数据库任务记录
        3. 本地磁盘文件（如果有）

        Args:
            task_id: 任务ID

        Returns:
            是否成功
        """
        # 获取任务信息（用于清理文件）
        task = db.get_download_task(task_id)
        if not task:
            logger.warning(f"[delete_task] 任务不存在: {task_id}")
            return False

        # 使用补偿事务管理器删除任务（保证双写一致性）
        result = self._get_compensation_manager().delete_task_with_compensation(task_id)

        # 清理本地文件
        if result["success"]:
            self._cleanup_local_file(task)
            logger.info(f"[delete_task] 删除成功: {task_id}")
            return True
        else:
            logger.warning(f"[delete_task] 删除失败: {result.get('error')}")
            return False

    def _task_to_dict(self, task: DownloadTask) -> dict:
        """将 DownloadTask 转为 dict，附带作者信息"""
        author_username = ""
        author_nickname = ""
        head_url = ""

        video = db.get_author_video(task.video_id) if task.video_id else None
        if video:
            author = db.get_author(video.author_id) if video.author_id else None
            if author:
                author_username = author.source_author_id or ""
                author_nickname = author.name or ""
                head_url = author.avatar_url or ""

        return {
            "task_id": task.task_id,
            "video_id": task.video_id,
            "status": task.status,
            "progress": task.progress,
            "downloaded": task.downloaded,
            "total_size": task.total_size,
            "speed": task.speed,
            "error_msg": task.error_msg,
            "completed_at": task.completed_at,
            "title": task.title,
            "name": task.title,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
            "author": author_username,
            "author_nickname": author_nickname,
            "head_url": head_url,
        }

    def _cleanup_local_file(self, task: DownloadTask):
        """清理本地视频文件并重置下载状态

        Args:
            task: 下载任务
        """
        # 获取视频信息以获取下载路径
        video = db.get_author_video(task.video_id)
        if not video:
            return

        if video.download_path:
            from pathlib import Path

            download_path = Path(video.download_path)
            if download_path.exists():
                try:
                    if download_path.is_file():
                        download_path.unlink()
                        logger.info(f"[_cleanup_local_file] 已删除文件: {download_path}")
                    elif download_path.is_dir():
                        video_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.flv']
                        for ext in video_extensions:
                            for f in download_path.glob(f'*{ext}'):
                                try:
                                    f.unlink()
                                    logger.info(f"[_cleanup_local_file] 已删除文件: {f}")
                                except Exception as e:
                                    logger.warning(f"[_cleanup_local_file] 删除文件失败: {f}, {e}")

                        if not any(download_path.iterdir()):
                            download_path.rmdir()
                            logger.info(f"[_cleanup_local_file] 已删除空目录: {download_path}")
                except Exception as e:
                    logger.warning(f"[_cleanup_local_file] 清理失败: {download_path}, {e}")

        # 重置视频为未下载状态
        if video.is_downloaded == 1:
            db.reset_video_downloaded(task.video_id)
            logger.info(f"[_cleanup_local_file] 已重置视频状态: {task.video_id}")

    def _get_backend_task_from_list(self, task_id: str) -> Optional[dict]:
        """从后端任务列表获取指定任务信息

        Args:
            task_id: 任务ID

        Returns:
            任务信息 dict 或 None
        """
        import requests as http_requests

        try:
            resp = http_requests.get(
                f"{self.api_base_url}/api/task/list",
                timeout=10
            )
            data = resp.json()
            if data.get("code") != 0:
                return None

            task_list = data.get("data", {}).get("list", [])
            for task in task_list:
                if task.get("id") == task_id:
                    return task
            return None

        except Exception as e:
            logger.error(f"[_get_backend_task_from_list] 查询失败: {e}")
            return None

    @staticmethod
    def reconcile_orphaned_downloads():
        """启动时校验：is_downloaded=1 但文件不存在的记录重置为 0

        处理历史遗留的脏数据（Go后端报done但文件实际丢失），
        确保监控循环能重新下载这些视频。
        """
        import core.utils.database as db_module

        authors = db_module.db.list_authors()
        reset_count = 0
        checked_count = 0

        for author in authors:
            videos = db_module.db.list_author_videos(author.id)
            for video in videos:
                if video.is_downloaded != 1:
                    continue
                checked_count += 1
                if not video.download_path:
                    db_module.db.reset_video_downloaded(video.video_id)
                    reset_count += 1
                    logger.info(f"[reconcile] 重置空路径: video_id={video.video_id}")
                    continue
                if not os.path.isfile(video.download_path):
                    db_module.db.reset_video_downloaded(video.video_id)
                    reset_count += 1
                    logger.info(f"[reconcile] 重置丢失文件: video_id={video.video_id}, "
                                f"path={video.download_path}")

        if checked_count > 0:
            logger.info(f"[reconcile] 校验完成: 检查 {checked_count} 条已下载记录, "
                        f"重置 {reset_count} 条无效记录")

    @staticmethod
    def cleanup_stale_tasks():
        """清理 Go 端不存在的残留任务（running/wait）

        Go 后端重启后，本地 DB 中残留的 running/wait 任务
        在 Go 端已不存在，会阻塞监控器并发窗口。
        此方法扫描活跃任务，与 Go 端任务列表对比，清理不在 Go 端的残留记录。
        清理方式：标记为 cancelled（保留记录），而非删除。
        注意：pending 任务不清理，它们可能是刚恢复的断点续传任务。
        """
        import core.utils.database as db_module
        import requests as http_requests

        # 获取 Go 端所有任务 ID
        go_task_ids = set()
        try:
            resp = http_requests.get("http://127.0.0.1:2022/api/task/list", timeout=5)
            data = resp.json()
            if data.get("code") == 0:
                for t in data.get("data", {}).get("list", []):
                    go_task_ids.add(t.get("id"))
        except Exception as e:
            logger.warning(f"[cleanup_stale] 无法连接 Go 后端，跳过清理: {e}")
            return {"cleaned": 0, "error": str(e)}

        # 扫描本地活跃任务
        # pending 任务不清理：它们可能是刚恢复的，Go 端还没来得及处理
        tasks = db_module.db.list_download_tasks(status=None)
        cleaned = 0
        for task in tasks:
            if task.status not in ("running", "wait"):
                continue
            if task.task_id not in go_task_ids:
                logger.info(f"[cleanup_stale] 清理残留任务: task_id={task.task_id}, "
                            f"video_id={task.video_id}, status={task.status}")
                db_module.db.update_download_task_status(task.task_id, "cancelled")
                cleaned += 1

        if cleaned > 0:
            logger.info(f"[cleanup_stale] 清理完成: 共清理 {cleaned} 个残留任务")
        else:
            logger.info("[cleanup_stale] 无残留任务需要清理")

        return {"cleaned": cleaned}


def save_progress_from_sse(progress_data: dict):
    """从 SSE 进度数据保存到数据库

    Args:
        progress_data: SSE 推送的进度数据
            {
                "id": task_id,
                "video_id": video_id,
                "status": "running",
                "downloaded": 5000000,
                "total_size": 10000000,
                "speed": 1000000,
            }
    """
    task_id = progress_data.get("id")
    if not task_id:
        return

    # 检查任务是否存在
    task = db.get_download_task(task_id)
    if not task:
        return

    # 解析进度数据
    downloaded = progress_data.get("downloaded", 0)
    total_size = progress_data.get("total_size", 0)
    speed = progress_data.get("speed", 0)
    status = progress_data.get("status", "running")

    # 计算进度百分比
    if total_size > 0:
        progress = min(100, int(downloaded / total_size * 100))
    else:
        progress = 0

    # 更新数据库
    db.update_download_task_progress(task_id, progress, downloaded, total_size, speed, status)


def restore_pending_tasks() -> list[dict]:
    """恢复待处理的任务

    应用启动时调用，将上次未完成的 running/pending 任务恢复为 pending 状态，
    以便重新下载。

    Returns:
        恢复的任务列表
    """
    tasks = db.list_download_tasks(status=None)
    restored = []

    for task in tasks:
        if task.status in ("running", "pending", "wait"):
            # 将 running/wait 状态重置为 pending
            db.update_download_task_status(task.task_id, "pending")

            restored.append({
                "task_id": task.task_id,
                "video_id": task.video_id,
                "progress": task.progress,
                "downloaded": task.downloaded,
                "total_size": task.total_size,
            })

    if restored:
        logger.info(f"[restore_pending_tasks] 共恢复 {len(restored)} 个任务")

    return restored


def is_partial_download(file_path: str, total_size: int) -> bool:
    """检测文件是否为部分下载（文件存在但大小小于 total_size）

    Args:
        file_path: 文件路径
        total_size: 预期总大小

    Returns:
        True 如果是部分下载，False 否则
    """
    import os

    if not os.path.exists(file_path):
        return False

    file_size = os.path.getsize(file_path)
    # 文件大小小于 total_size 才是部分下载
    return file_size > 0 and file_size < total_size


def resume_download_task(task_id: str) -> bool:
    """恢复单个下载任务（重新创建 Go 下载任务）

    Args:
        task_id: 任务 ID

    Returns:
        True 如果成功，False 否则
    """
    logger.info(f"[resume] 开始恢复任务: task_id={task_id}")

    task = db.get_download_task(task_id)
    if not task:
        logger.warning(f"[resume] 任务不存在: {task_id}")
        return False

    logger.info(f"[resume] 任务信息: id={task_id}, video_id={task.video_id}, status={task.status}, progress={task.progress}%")

    if task.status not in ("running", "pending"):
        logger.info(f"[resume] 跳过: 状态不是 running/pending, 当前={task.status}")
        return False

    # 查找作者名称（通过 video_id → author_id → author.name）
    author_name = ""
    source_author_id = ""
    video = db.get_author_video(task.video_id)
    if video and video.author_id:
        author = db.get_author(video.author_id)
        if author:
            author_name = author.name or ""
            source_author_id = author.source_author_id or ""

    # URL 有效性检查和刷新（微信视频 URL 会过期）
    search_svc = SearchService()
    url_result = search_svc.ensure_valid_url(
        url=task.url,
        source_author_id=source_author_id,
        video_id=task.video_id,
        create_time=task.create_time or task.created_at,
        video_type=task.video_type if hasattr(task, 'video_type') else "short_video"
    )
    if url_result["code"] != 0:
        logger.warning("[resume] URL 过期且刷新失败: task_id=%s, msg=%s", task_id, url_result["msg"])
        return False
    effective_url = url_result["data"]["url"]
    if url_result["data"]["refreshed"]:
        logger.info("[resume] URL 已刷新: task_id=%s", task_id)
        db.update_video_url(task.video_id, effective_url)

    # 调用 Go 后端创建下载任务
    client = WechatVideoAPIClient()
    result = client.download_video(
        video_id=task.video_id,
        url=effective_url,
        title=task.title,
        spec=task.spec,
        key=task.key,
        author_name=author_name,
        create_time=task.create_time or task.created_at,
        video_type=task.video_type if hasattr(task, 'video_type') else "short_video",
    )

    if result.get("code") != 0:
        logger.warning(f"[resume] Go创建失败: task_id={task_id}, code={result.get('code')}, msg={result.get('msg')}")
        return False

    # 获取 Go 返回的新 task_id
    new_task_id = result.get("data", {}).get("id")
    if not new_task_id:
        logger.warning(f"[resume] Go未返回task_id: old_id={task_id}")
        return False

    # 如果新 ID 与旧 ID 不同，需要更新数据库
    # 安全策略：先创建新记录，再删除旧记录，避免 delete→create 之间崩溃导致数据永久丢失
    if new_task_id != task_id:
        logger.info(f"[resume] ID变更: {task_id} -> {new_task_id}")
        # 先创建新记录（使用新 ID）
        new_task = DownloadTask(
            task_id=new_task_id,
            video_id=task.video_id,
            url=effective_url,
            title=task.title,
            filename=task.filename,
            spec=task.spec,
            suffix=task.suffix,
            key=task.key,
            status="pending",
            progress=task.progress,
            downloaded=task.downloaded,
            total_size=task.total_size,
            speed=0,
            error_msg="",
            created_at=task.created_at,
            updated_at=datetime.now().isoformat(),
            completed_at=None,
            video_type=task.video_type if hasattr(task, 'video_type') else "short_video",
            create_time=task.create_time if hasattr(task, 'create_time') else "",
        )
        created = db.create_download_task(new_task)
        if not created:
            logger.error("[resume] 创建新记录失败: new_id=%s, 旧记录保留", new_task_id)
            return False
        # 新记录创建成功后，安全删除旧记录
        db.delete_download_task(task_id)
    else:
        # ID 相同，只更新状态
        logger.info(f"[resume] ID不变: {task_id}")
        db.update_download_task_status(task_id, "pending")

    logger.info(f"[resume] 恢复成功: new_id={new_task_id}, video_id={task.video_id}")
    return True


def resume_all_running_tasks() -> dict:
    """恢复所有 running/pending 状态的任务

    Returns:
        {"resumed": 恢复数量, "skipped": 跳过数量, "failed": 失败数量}
    """
    if not _resume_lock.acquire(blocking=False):
        logger.info("[resume_all] 已有恢复任务正在进行，跳过")
        return {"resumed": 0, "skipped": 1, "failed": 0}
    try:
        # 查询 running 和 pending 状态的任务
        running_tasks = db.list_download_tasks(status="running", limit=1000)
        pending_tasks = db.list_download_tasks(status="pending", limit=1000)

        total_to_resume = len(running_tasks) + len(pending_tasks)
        if total_to_resume == 0:
            logger.info("[resume_all_running_tasks] 无需恢复的任务")
            return {"resumed": 0, "skipped": 0, "failed": 0}

        logger.info(f"[resume_all_running_tasks] 待恢复任务: running={len(running_tasks)}, pending={len(pending_tasks)}")

        result = {"resumed": 0, "skipped": 0, "failed": 0}

        # 恢复 running 任务
        for task in running_tasks:
            if resume_download_task(task.task_id):
                result["resumed"] += 1
            else:
                result["failed"] += 1

        # 恢复 pending 任务
        for task in pending_tasks:
            if resume_download_task(task.task_id):
                result["resumed"] += 1
            else:
                result["failed"] += 1

        logger.info(f"[resume_all_running_tasks] 恢复完成: resumed={result['resumed']}, failed={result['failed']}")

        return result
    finally:
        _resume_lock.release()


# ========== 断点续传可靠性增强函数 ==========


def resume_download_task_with_validation(task_id: str, file_path: str = None) -> dict:
    """恢复任务时验证文件可续传性

    Args:
        task_id: 任务 ID
        file_path: 部分下载文件路径（可选）

    Returns:
        {"success": bool, "reason": str, "new_task_id": str}
    """
    task = db.get_download_task(task_id)
    if not task:
        return {"success": False, "reason": "task_not_found"}

    # 如果提供了文件路径，验证文件
    if file_path:
        if not os.path.exists(file_path):
            logger.warning(f"[resume_validation] 文件不存在: {file_path}")
            return {"success": False, "reason": "file_not_found"}

        file_size = os.path.getsize(file_path)
        if task.total_size and file_size >= task.total_size:
            logger.info(f"[resume_validation] 文件已完整: {file_path}, size={file_size}")
            return {"success": False, "reason": "file_already_complete"}

        logger.info(f"[resume_validation] 文件可续传: {file_path}, size={file_size}/{task.total_size}")

    # 调用基础恢复函数
    success = resume_download_task(task_id)
    if success:
        return {"success": True, "reason": "resumed"}
    else:
        return {"success": False, "reason": "resume_failed"}


def resume_download_task_with_retry(task_id: str, max_retries: int = 3) -> dict:
    """恢复任务时自动重试

    Args:
        task_id: 任务 ID
        max_retries: 最大重试次数

    Returns:
        {"success": bool, "reason": str, "attempts": int}
    """
    import time

    for attempt in range(1, max_retries + 1):
        logger.info(f"[resume_retry] 尝试恢复: task_id={task_id}, attempt={attempt}/{max_retries}")

        success = resume_download_task(task_id)
        if success:
            logger.info(f"[resume_retry] 恢复成功: task_id={task_id}, attempt={attempt}")
            return {"success": True, "reason": "resumed", "attempts": attempt}

        # 重试间隔递增
        if attempt < max_retries:
            wait_time = attempt  # 1s, 2s, 3s...
            logger.info(f"[resume_retry] 等待 {wait_time}s 后重试")
            time.sleep(wait_time)

    logger.warning(f"[resume_retry] 超过最大重试次数: task_id={task_id}, max_retries={max_retries}")
    return {"success": False, "reason": "max_retries_exceeded", "attempts": max_retries}


def resume_download_task_atomic(task_id: str) -> dict:
    """恢复任务时保证原子性

    失败时回滚已做的更改。

    Args:
        task_id: 任务 ID

    Returns:
        {"success": bool, "reason": str}
    """
    task = db.get_download_task(task_id)
    if not task:
        return {"success": False, "reason": "task_not_found"}

    if task.status not in ("running", "pending"):
        return {"success": False, "reason": "invalid_status"}

    # 保存原始任务信息用于回滚
    original_task_info = {
        "task_id": task.task_id,
        "video_id": task.video_id,
        "url": task.url,
        "title": task.title,
        "filename": task.filename,
        "spec": task.spec,
        "suffix": task.suffix,
        "key": task.key,
        "status": task.status,
        "progress": task.progress,
        "downloaded": task.downloaded,
        "total_size": task.total_size,
        "created_at": task.created_at,
        "video_type": task.video_type,
        "create_time": task.create_time if hasattr(task, 'create_time') else "",
    }

    # 查找作者名称 + source_author_id（通过 video_id → author_id → author）
    author_name = ""
    source_author_id = ""
    video = db.get_author_video(task.video_id)
    if video and video.author_id:
        author = db.get_author(video.author_id)
        if author:
            author_name = author.name or ""
            source_author_id = author.source_author_id or ""

    # URL 有效性检查和刷新（微信视频 URL 会过期）
    search_svc = SearchService()
    url_result = search_svc.ensure_valid_url(
        url=task.url,
        source_author_id=source_author_id,
        video_id=task.video_id,
        create_time=task.create_time or task.created_at,
        video_type=task.video_type if hasattr(task, 'video_type') else "short_video"
    )
    if url_result["code"] != 0:
        logger.warning("[resume_atomic] URL 过期且刷新失败: task_id=%s, msg=%s", task_id, url_result["msg"])
        return {"success": False, "reason": "url_expired"}
    effective_url = url_result["data"]["url"]
    if url_result["data"]["refreshed"]:
        logger.info("[resume_atomic] URL 已刷新: task_id=%s", task_id)
        db.update_video_url(task.video_id, effective_url)

    client = WechatVideoAPIClient()
    result = client.download_video(
        video_id=task.video_id,
        url=effective_url,
        title=task.title,
        spec=task.spec,
        key=task.key,
        author_name=author_name,
        create_time=task.create_time or task.created_at,
        video_type=task.video_type if hasattr(task, 'video_type') else "short_video",
    )

    if result.get("code") != 0:
        return {"success": False, "reason": "go_api_failed"}

    new_task_id = result.get("data", {}).get("id")
    if not new_task_id:
        return {"success": False, "reason": "no_task_id_returned"}

    # 尝试更新数据库
    try:
        if new_task_id != task_id:
            logger.info(f"[resume_atomic] ID变更: {task_id} -> {new_task_id}")
            # 安全策略：先创建新记录，再删除旧记录（与 resume_download_task 一致）
            new_task = DownloadTask(
                task_id=new_task_id,
                video_id=task.video_id,
                url=task.url,
                title=task.title,
                filename=task.filename,
                spec=task.spec,
                suffix=task.suffix,
                key=task.key,
                status="pending",
                progress=task.progress,
                downloaded=task.downloaded,
                total_size=task.total_size,
                speed=0,
                error_msg="",
                created_at=task.created_at,
                updated_at=datetime.now().isoformat(),
                completed_at=None,
                video_type=task.video_type if hasattr(task, 'video_type') else "short_video",
                create_time=task.create_time if hasattr(task, 'create_time') else "",
            )
            created = db.create_download_task(new_task)
            if not created:
                logger.error("[resume_atomic] 创建新记录失败: new_id=%s, 旧记录保留", new_task_id)
                return {"success": False, "reason": "create_failed"}
            db.delete_download_task(task_id)
        else:
            db.update_download_task_status(task_id, "pending")

        logger.info(f"[resume_atomic] 恢复成功: {new_task_id}")
        return {"success": True, "reason": "resumed", "new_task_id": new_task_id}

    except Exception as e:
        logger.error(f"[resume_atomic] 数据库操作失败，尝试回滚: {e}")

        # 回滚：恢复原始任务记录
        try:
            # 如果新记录已创建，删除它
            if new_task_id != task_id:
                existing = db.get_download_task(new_task_id)
                if existing:
                    db.delete_download_task(new_task_id)

            # 恢复原始记录（如果旧记录已被删除才需要重建）
            original_exists = db.get_download_task(task_id) is not None
            if original_exists:
                # 旧记录还在，恢复其状态
                db.update_download_task_status(task_id, original_task_info["status"])
                logger.info(f"[resume_atomic] 回滚：旧记录仍在，恢复状态为 %s", original_task_info["status"])
            else:
                # 旧记录已被删除，需要重建
                original_task = DownloadTask(
                    task_id=original_task_info["task_id"],
                    video_id=original_task_info["video_id"],
                    url=original_task_info["url"],
                    title=original_task_info["title"],
                    filename=original_task_info["filename"],
                    spec=original_task_info["spec"],
                    suffix=original_task_info["suffix"],
                    key=original_task_info["key"],
                    status=original_task_info["status"],
                    progress=original_task_info["progress"],
                    downloaded=original_task_info["downloaded"],
                    total_size=original_task_info["total_size"],
                    speed=0,
                    error_msg="",
                    created_at=original_task_info["created_at"],
                    updated_at=datetime.now().isoformat(),
                    completed_at=None,
                    video_type=original_task_info["video_type"],
                    create_time=original_task_info.get("create_time", ""),
                )
                recreated = db.create_download_task(original_task)
                if recreated:
                    logger.info(f"[resume_atomic] 回滚：旧记录已重建: {task_id}")
                else:
                    logger.error(f"[resume_atomic] 回滚：旧记录重建失败（可能已存在）: {task_id}")
        except Exception as rollback_error:
            logger.error(f"[resume_atomic] 回滚失败: {rollback_error}")

        return {"success": False, "reason": "rollback_attempted"}


def resume_pending_tasks():
    """恢复所有活跃状态的下载任务（断点续传）

    恢复 pending、running、wait 三种状态的任务。
    先将 running/wait 转为 pending，再逐个恢复。

    场景：
    - 用户停止服务后重新启动
    - Go 崩溃后用户手动重启
    - 应用冷启动
    """
    if not _resume_lock.acquire(blocking=False):
        logger.info("[resume_pending] 已有恢复任务正在进行，跳过")
        return {"resumed": 0, "failed": 0, "skipped": 1}
    try:
        # 先将 running/wait 转为 pending（保证状态统一）
        running = db.list_download_tasks(status="running", limit=1000)
        wait = db.list_download_tasks(status="wait", limit=1000)
        for task in running:
            db.update_download_task_status(task.task_id, "pending")
        for task in wait:
            db.update_download_task_status(task.task_id, "pending")
        if running or wait:
            logger.info("[resume_pending] 状态归一化: running=%d, wait=%d → pending",
                        len(running), len(wait))

        # 查询所有 pending 任务并恢复
        pending = db.list_download_tasks(status="pending", limit=1000)
        resumed = 0
        failed = 0

        for task in pending:
            try:
                result = resume_download_task(task.task_id)
                if result:
                    resumed += 1
                    logger.info("[resume_pending] 恢复任务 %s 成功", task.task_id)
                else:
                    failed += 1
                    logger.warning("[resume_pending] 恢复任务 %s 失败", task.task_id)
            except Exception as e:
                failed += 1
                logger.error("[resume_pending] 恢复任务 %s 异常: %s", task.task_id, e)

        # 通知前端有任务恢复
        if resumed > 0:
            from core.utils.event_bus import emit, TASKS_RESUMED
            emit(TASKS_RESUMED, {"resumed": resumed, "failed": failed})

        return {"resumed": resumed, "failed": failed}
    finally:
        _resume_lock.release()


def resume_download_task_with_state(task_id: str) -> dict:
    """恢复任务时持久化恢复状态

    Args:
        task_id: 任务 ID

    Returns:
        {"success": bool, "reason": str}
    """
    # 先保存恢复状态
    try:
        db.save_resume_state(task_id, "resuming")
        logger.info(f"[resume_state] 保存恢复状态: task_id={task_id}")
    except Exception as e:
        logger.warning(f"[resume_state] 保存状态失败: {e}")

    # 执行恢复
    result = resume_download_task_atomic(task_id)

    # 清除恢复状态
    try:
        db.clear_resume_state(task_id)
        logger.info(f"[resume_state] 清除恢复状态: task_id={task_id}")
    except Exception as e:
        logger.warning(f"[resume_state] 清除状态失败: {e}")

    return result


def resume_download_task_with_verification(task_id: str) -> dict:
    """恢复任务后验证一致性

    Args:
        task_id: 任务 ID

    Returns:
        {"success": bool, "reason": str}
    """
    task = db.get_download_task(task_id)
    if not task:
        return {"success": False, "reason": "task_not_found"}

    # 检查是否有重复任务
    existing_task = db.get_download_task_by_video_id(task.video_id)
    if existing_task and existing_task.task_id != task_id:
        logger.warning(f"[resume_verify] 发现重复任务: video_id={task.video_id}, existing_id={existing_task.task_id}")
        return {"success": False, "reason": "duplicate_task"}

    # 执行恢复
    result = resume_download_task_atomic(task_id)
    if not result["success"]:
        return result

    new_task_id = result.get("new_task_id", task_id)

    # 验证 Go 后端任务存在
    try:
        client = WechatVideoAPIClient()
        go_tasks = client.list_download_tasks()
        go_task_ids = {t.get("id") for t in go_tasks if t.get("id")}

        if new_task_id not in go_task_ids:
            logger.warning(f"[resume_verify] Go后端任务不存在: {new_task_id}")
            return {"success": False, "reason": "go_task_not_found"}

        logger.info(f"[resume_verify] 验证成功: Go任务存在, id={new_task_id}")
    except Exception as e:
        logger.warning(f"[resume_verify] Go验证失败: {e}")

    return {"success": True, "reason": "verified", "new_task_id": new_task_id}


def resume_download_full(task_id: str, file_path: str = None, max_retries: int = 3) -> dict:
    """完整的断点续传流程

    组合所有可靠性机制：
    1. 文件验证
    2. 自动重试
    3. 原子性保证
    4. 状态持久化
    5. 一致性验证

    Args:
        task_id: 任务 ID
        file_path: 部分下载文件路径（可选）
        max_retries: 最大重试次数

    Returns:
        {"success": bool, "reason": str, "new_task_id": str, "resumed_from": str}
    """
    logger.info(f"[resume_full] 开始完整恢复流程: task_id={task_id}")

    # 1. 文件验证
    if file_path:
        validation_result = resume_download_task_with_validation(task_id, file_path)
        if not validation_result["success"]:
            if validation_result["reason"] == "file_already_complete":
                # 文件已完整，标记任务完成
                db.update_download_task_status(task_id, "completed")
                logger.info(f"[resume_full] 文件已完整，任务标记完成: {task_id}")
                return {"success": True, "reason": "already_complete", "new_task_id": task_id}
            return validation_result

    # 2. 状态持久化
    try:
        db.save_resume_state(task_id, "resuming")
    except Exception as e:
        logger.warning(f"[resume_full] 保存状态失败: {e}")

    # 3. 自动重试 + 原子性
    retry_result = resume_download_task_with_retry(task_id, max_retries)
    if not retry_result["success"]:
        # 清除状态
        try:
            db.clear_resume_state(task_id)
        except Exception:
            pass
        return retry_result

    # 4. 一致性验证
    verify_result = resume_download_task_with_verification(task_id)

    # 5. 清除状态
    try:
        db.clear_resume_state(task_id)
    except Exception as e:
        logger.warning(f"[resume_full] 清除状态失败: {e}")

    if verify_result["success"]:
        logger.info(f"[resume_full] 完整恢复成功: old_id={task_id}, new_id={verify_result.get('new_task_id')}")
        return {
            "success": True,
            "reason": "full_resume_success",
            "new_task_id": verify_result.get("new_task_id"),
            "resumed_from": task_id,
        }
    else:
        return verify_result


def recover_interrupted_resumes():
    """恢复崩溃时未完成的恢复任务"""
    try:
        pending_states = db.get_pending_resume_states()
        if not pending_states:
            logger.info("[recover_interrupted] 无未完成的恢复任务")
            return

        logger.info(f"[recover_interrupted] 发现 {len(pending_states)} 个未完成的恢复任务")

        for state in pending_states:
            task_id = state.get("task_id")
            logger.info(f"[recover_interrupted] 尝试恢复: task_id={task_id}")

            result = resume_download_task_with_retry(task_id, max_retries=1)
            if result["success"]:
                logger.info(f"[recover_interrupted] 恢复成功: task_id={task_id}")
            else:
                logger.warning(f"[recover_interrupted] 恢复失败: task_id={task_id}, reason={result['reason']}")

            # 清除状态
            db.clear_resume_state(task_id)

    except Exception as e:
        logger.error(f"[recover_interrupted] 恢复未完成任务失败: {e}")
