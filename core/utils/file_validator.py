"""文件校验器

检测并清理损坏的视频文件，处理以下场景：
1. 启动时校验：is_downloaded=1 但文件不存在 -> 重置状态
2. 启动时校验：is_downloaded=0 但文件存在（残留损坏文件） -> 删除文件
3. 创建任务前检查：文件存在则删除（Go 后端会追加写入）
"""
import logging
import os
import re
from pathlib import Path
from typing import Optional

from core.utils.database.crud.models import AuthorVideo
from core.utils.weixin_client import build_video_filename

logger = logging.getLogger("file_validator")


class FileValidator:
    """文件校验器

    负责检测和清理损坏的视频文件，确保下载状态与实际文件一致。
    """

    def __init__(self, db=None, download_dir: str = None):
        """初始化校验器

        Args:
            db: 数据库实例（支持依赖注入，默认使用全局 db）
            download_dir: 下载目录（支持依赖注入，默认使用 settings.wx_download_dir）
        """
        if db is None:
            from core.utils.database import db as global_db
            self._db = global_db
        else:
            self._db = db

        if download_dir is None:
            from config.settings import settings
            self._download_dir = str(settings.wx_download_dir)
        else:
            self._download_dir = download_dir

        logger.info(f"[FileValidator] 初始化完成: download_dir={self._download_dir}")

    def validate_on_startup(self) -> dict:
        """启动时校验

        检查所有视频记录，处理以下情况：
        1. is_downloaded=1 但文件不存在 -> 重置为未下载状态
        2. is_downloaded=0 但目标路径有残留文件 -> 删除损坏文件

        Returns:
            {"reset_count": int, "deleted_count": int} - 重置和删除的数量
        """
        reset_count = 0
        deleted_count = 0

        # 获取所有作者
        authors = self._db.list_authors()
        if not authors:
            logger.info("[validate_on_startup] 无作者记录，跳过校验")
            return {"reset_count": 0, "deleted_count": 0}

        for author in authors:
            videos = self._db.list_author_videos(author.id)
            for video in videos:
                # Case 1: 已下载标记但文件不存在
                if video.is_downloaded == 1:
                    if not video.download_path:
                        # 空路径：重置状态
                        self._db.reset_video_downloaded(video.video_id)
                        reset_count += 1
                        logger.info(f"[validate_on_startup] 重置空路径: video_id={video.video_id}")
                        continue

                    if not os.path.isfile(video.download_path):
                        # 文件不存在：重置状态
                        self._db.reset_video_downloaded(video.video_id)
                        reset_count += 1
                        logger.info(f"[validate_on_startup] 重置丢失文件: video_id={video.video_id}, "
                                    f"path={video.download_path}")
                        continue

                # Case 2: 未下载标记但目标路径有残留文件
                if video.is_downloaded == 0:
                    target_path = self._calculate_target_path(video)
                    if target_path and os.path.isfile(target_path):
                        # 删除残留损坏文件
                        try:
                            os.remove(target_path)
                            deleted_count += 1
                            logger.info(f"[validate_on_startup] 删除残留文件: video_id={video.video_id}, "
                                        f"path={target_path}")
                        except OSError as e:
                            logger.warning(f"[validate_on_startup] 删除文件失败: path={target_path}, error={e}")

        logger.info(f"[validate_on_startup] 校验完成: 重置 {reset_count} 条记录, 删除 {deleted_count} 个残留文件")
        return {"reset_count": reset_count, "deleted_count": deleted_count}

    def check_before_create_task(self, video_id: str) -> bool:
        """创建任务前检查

        Args:
            video_id: 视频ID

        Returns:
            True 表示可以创建任务，False 表示视频不存在

        说明：
            - 获取视频信息，计算目标路径
            - 文件存在则删除（因为 Go 后端会追加写入）
        """
        # 获取视频信息
        video = self._db.get_author_video(video_id)
        if not video:
            logger.warning(f"[check_before_create_task] 视频不存在: video_id={video_id}")
            return False

        # 计算目标路径
        target_path = self._calculate_target_path(video)

        # 文件存在则删除（Go 后端会追加写入）
        if target_path and os.path.isfile(target_path):
            try:
                os.remove(target_path)
                logger.info(f"[check_before_create_task] 删除已存在文件: video_id={video_id}, path={target_path}")
            except OSError as e:
                logger.warning(f"[check_before_create_task] 删除文件失败: path={target_path}, error={e}")

        return True

    def _calculate_target_path(self, video: AuthorVideo) -> str:
        """计算目标文件路径

        模拟 Go 后端的命名规则：
        - 目录：下载目录/作者名/视频类型/
        - 文件名：日期_标题_规格.mp4

        Args:
            video: 视频信息

        Returns:
            目标文件路径
        """
        author_name = ""
        if video.author_id:
            author = self._db.get_author(video.author_id)
            if author:
                author_name = author.name or ""

        safe_author = re.sub(r'[<>:"/\\|?*\n\r\t]', '_', author_name)[:50] if author_name else ""

        type_folder_map = {"short_video": "短视频", "live_replay": "直播回放"}
        type_folder = type_folder_map.get(video.video_type, "短视频")

        filename = build_video_filename(video.title, video.create_time, video.spec, video_id=video.video_id)

        dir_parts = []
        if safe_author:
            dir_parts.append(safe_author)
        dir_parts.append(type_folder)
        dir_path = Path(self._download_dir) / "/".join(dir_parts)

        full_path = dir_path / filename

        return str(full_path)