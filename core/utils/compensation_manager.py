"""补偿事务管理器

处理双写操作的一致性：
- 创建任务：同时写入 Go 数据库和 App 数据库
- 删除任务：同时删除 Go 任务和 App 数据库记录

当 App 写入失败时，自动回滚 Go 任务（重试机制）。
"""
import logging
import time
from datetime import datetime
from typing import Optional

logger = logging.getLogger("compensation_manager")


class CompensationTransactionManager:
    """补偿事务管理器

    处理双写操作的一致性问题，确保 Go 后端和 App 数据库的数据一致。
    """

    ROLLBACK_MAX_RETRIES = 3  # 回滚最大重试次数
    ROLLBACK_RETRY_INTERVAL = 1  # 回滚重试间隔（秒）

    def __init__(self, go_client=None, file_validator=None, db=None, search_service=None):
        """初始化补偿事务管理器

        Args:
            go_client: Go API 客户端（支持依赖注入）
            file_validator: 文件校验器（支持依赖注入）
            db: 数据库实例（支持依赖注入）
            search_service: 搜索服务（用于 URL 刷新）
        """
        if go_client is None:
            from core.utils.weixin_client import WechatVideoAPIClient
            self._go_client = WechatVideoAPIClient()
        else:
            self._go_client = go_client

        if file_validator is None:
            from core.utils.file_validator import FileValidator
            self._file_validator = FileValidator()
        else:
            self._file_validator = file_validator

        if db is None:
            from core.utils.database import db as global_db
            self._db = global_db
        else:
            self._db = db

        if search_service is None:
            from core.service.search import SearchService
            self._search_service = SearchService()
        else:
            self._search_service = search_service

        logger.info("[CompensationTransactionManager] 初始化完成")

    def create_task_with_compensation(self, video_id: str) -> dict:
        """创建任务（带补偿）

        流程：
        1. 文件校验器检查目标文件
        2. 检查 URL 有效性，过期则刷新
        3. 调用 Go API 创建任务
        4. 写入 app.db
        5. 步骤 4 失败 → 回滚 Go 任务（重试 3 次）

        Args:
            video_id: 视频 ID

        Returns:
            成功: {"success": True, "task_id": "..."}
            失败: {"success": False, "error": "..."}
        """
        logger.info(f"[create_task_with_compensation] 开始创建任务: video_id={video_id}")

        # Step 1: 文件校验器检查目标文件
        if not self._file_validator.check_before_create_task(video_id):
            error_msg = f"视频不存在或校验失败: video_id={video_id}"
            logger.warning(f"[create_task_with_compensation] {error_msg}")
            return {"success": False, "error": error_msg}

        # 获取视频信息
        video = self._db.get_author_video(video_id)
        if not video:
            error_msg = f"视频不存在: video_id={video_id}"
            logger.warning(f"[create_task_with_compensation] {error_msg}")
            return {"success": False, "error": error_msg}

        # 获取作者信息
        author_name = ""
        source_author_id = ""
        if video.author_id:
            author = self._db.get_author(video.author_id)
            if author:
                author_name = author.name or ""
                source_author_id = author.source_author_id or ""

        # Step 2: 检查 URL 有效性，过期则刷新
        current_url = video.url
        url_result = self._search_service.ensure_valid_url(
            url=current_url,
            source_author_id=source_author_id,
            video_id=video.video_id,
            create_time=video.create_time,
            video_type=video.video_type
        )

        if url_result["code"] != 0:
            error_msg = f"URL 刷新失败: {url_result['msg']}"
            logger.error(f"[create_task_with_compensation] {error_msg}")
            return {"success": False, "error": error_msg}

        # 如果 URL 被刷新，更新数据库
        if url_result["data"]["refreshed"]:
            new_url = url_result["data"]["url"]
            logger.info(f"[create_task_with_compensation] URL 已刷新: video_id={video_id}, old_url长度={len(current_url)}, new_url长度={len(new_url)}")
            # 更新数据库中的 URL
            self._db.update_video_url(video_id, new_url)
            current_url = new_url

        # Step 3: 调用 Go API 创建任务
        go_result = self._go_client.download_video(
            video_id=video.video_id,
            url=current_url,  # 使用可能已刷新的 URL
            title=video.title,
            spec=video.spec,
            key=video.decode_key,
            author_name=author_name,
            create_time=video.create_time,
            video_type=video.video_type,
        )

        if go_result.get("code") != 0:
            error_msg = f"Go API 创建任务失败: {go_result.get('msg', '未知错误')}"
            logger.error(f"[create_task_with_compensation] {error_msg}")
            return {"success": False, "error": error_msg}

        task_id = go_result.get("data", {}).get("id")
        if not task_id:
            error_msg = "Go API 返回的 task_id 为空"
            logger.error(f"[create_task_with_compensation] {error_msg}")
            return {"success": False, "error": error_msg}

        logger.info(f"[create_task_with_compensation] Go创建成功: task_id={task_id}, video_id={video_id}")

        # Step 3: 写入 app.db
        try:
            from core.utils.database.crud.models import DownloadTask

            now = datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
            task = DownloadTask(
                task_id=task_id,
                video_id=video.video_id,
                url=current_url,  # 使用可能已刷新的 URL
                title=video.title,
                filename=video.title[:80],  # 截断文件名
                spec=video.spec,
                suffix=".mp4",
                key=video.decode_key,
                status="pending",
                progress=0,
                downloaded=0,
                total_size=video.file_size,
                speed=0,
                error_msg="",
                created_at=now,
                updated_at=now,
                completed_at=None,
                video_type=video.video_type,
                create_time=video.create_time,
            )

            if not self._db.create_download_task(task):
                raise Exception("数据库写入返回 False")

            logger.info(f"[create_task_with_compensation] App写入成功: task_id={task_id}, video_id={video_id}")
            return {"success": True, "task_id": task_id}

        except Exception as e:
            # Step 4: App 写入失败 → 回滚 Go 任务
            error_msg = f"数据库写入失败: {e}"
            logger.error(f"[create_task_with_compensation] {error_msg}, 开始回滚 Go 任务")

            rollback_success = self._rollback_go_task(task_id, "create")
            if rollback_success:
                logger.info(f"[create_task_with_compensation] 回滚成功: task_id={task_id}")
            else:
                logger.error(f"[create_task_with_compensation] 回滚失败: task_id={task_id}, 需要人工干预")

            return {"success": False, "error": error_msg}

    def delete_task_with_compensation(self, task_id: str) -> dict:
        """删除任务（带补偿）

        流程：
        1. 从 app.db 获取任务信息
        2. 调用 Go API 删除任务
        3. 删除 app.db 记录
        4. 步骤 2 失败 → 重试 3 次

        Args:
            task_id: 任务 ID

        Returns:
            成功: {"success": True, "task_id": "..."}
            失败: {"success": False, "error": "..."}
        """
        logger.info(f"[delete_task_with_compensation] 开始删除任务: task_id={task_id}")

        # Step 1: 从 app.db 获取任务信息
        task = self._db.get_download_task(task_id)
        if not task:
            error_msg = f"任务不存在: task_id={task_id}"
            logger.warning(f"[delete_task_with_compensation] {error_msg}")
            return {"success": False, "error": error_msg}

        # Step 2: 调用 Go API 删除任务（带重试）
        rollback_success = self._rollback_go_task(task_id, "delete")

        if not rollback_success:
            error_msg = f"Go API 删除任务失败（重试 {self.ROLLBACK_MAX_RETRIES} 次后仍失败）"
            logger.error(f"[delete_task_with_compensation] {error_msg}")
            # 即使 Go 删除失败，仍然删除本地记录（避免阻塞）
            logger.warning(f"[delete_task_with_compensation] 仍然删除本地记录: task_id={task_id}")

        # Step 3: 删除 app.db 记录
        try:
            if self._db.delete_download_task(task_id):
                logger.info(f"[delete_task_with_compensation] 数据库删除成功: task_id={task_id}")
                return {"success": True, "task_id": task_id}
            else:
                error_msg = "数据库删除返回 False"
                logger.error(f"[delete_task_with_compensation] {error_msg}")
                return {"success": False, "error": error_msg}
        except Exception as e:
            error_msg = f"数据库删除异常: {e}"
            logger.error(f"[delete_task_with_compensation] {error_msg}")
            return {"success": False, "error": error_msg}

    def _rollback_go_task(self, task_id: str, operation: str) -> bool:
        """回滚 Go 任务

        Args:
            task_id: 任务 ID
            operation: 操作类型（create/delete，用于日志）

        Returns:
            True 表示回滚成功，False 表示失败
        """
        logger.info(f"[_rollback_go_task] 开始回滚: task_id={task_id}, operation={operation}")

        for attempt in range(1, self.ROLLBACK_MAX_RETRIES + 1):
            try:
                result = self._go_client.cancel_task(task_id)
                if result:
                    logger.info(f"[_rollback_go_task] 回滚成功: task_id={task_id}, attempt={attempt}")
                    return True
                else:
                    logger.warning(
                        f"[_rollback_go_task] 回滚返回 False: task_id={task_id}, "
                        f"attempt={attempt}/{self.ROLLBACK_MAX_RETRIES}"
                    )
            except Exception as e:
                logger.error(
                    f"[_rollback_go_task] 回滚异常: task_id={task_id}, "
                    f"attempt={attempt}/{self.ROLLBACK_MAX_RETRIES}, error={e}"
                )

            # 重试前等待
            if attempt < self.ROLLBACK_MAX_RETRIES:
                logger.info(f"[_rollback_go_task] 等待 {self.ROLLBACK_RETRY_INTERVAL} 秒后重试")
                time.sleep(self.ROLLBACK_RETRY_INTERVAL)

        logger.error(
            f"[_rollback_go_task] 回滚全部失败: task_id={task_id}, "
            f"operation={operation}, retries={self.ROLLBACK_MAX_RETRIES}"
        )
        return False
