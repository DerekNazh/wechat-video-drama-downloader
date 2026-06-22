"""作者服务层

提供作者的增删查功能
"""

import logging
from datetime import datetime
from typing import Optional

from core.utils.database import Author
from core.utils.weixin_client import WechatVideoAPIClient
from core.utils.database import db
logger = logging.getLogger("author_service")


class AuthorService:
    """作者服务

    提供作者的创建、查询、删除功能
    """

    def __init__(self, api_base_url: str = "http://127.0.0.1:2022"):
        self.api_base_url = api_base_url
        self._client = WechatVideoAPIClient(base_url=api_base_url)

    def add_author(self, keyword: str) -> dict:
        """新增作者（强匹配）

        通过关键词搜索后端，找到与关键词完全匹配的作者名才入库。

        Args:
            keyword: 搜索关键词（必须与作者名完全一致）

        Returns:
            {"code": 0, "data": Author, "msg": ""} 或 {"code": -1, "msg": "错误信息"}
        """
        # 搜索后端
        search_result = self._client.search_authors(keyword)
        authors = search_result.get("authors", [])

        if not authors:
            logger.warning(f"[add_author] 搜索无结果: {keyword}")
            return {"code": -1, "msg": f"搜索无结果: {keyword}"}

        # 强匹配：找到与关键词完全一致的作者
        matched_author = None
        for item in authors:
            contact = item.get("contact", {})
            nickname = contact.get("nickname", "")
            if nickname == keyword:
                matched_author = item
                break

        if not matched_author:
            logger.warning(f"[add_author] 未找到精确匹配: {keyword}")
            return {"code": -1, "msg": f"未找到精确匹配的作者: {keyword}"}

        contact = matched_author.get("contact", {})
        source_author_id = contact.get("username", "")
        name = contact.get("nickname", "")

        # 检查是否已存在
        existing = db.get_author_by_name(name)
        if existing:
            logger.info(f"[add_author] 作者已存在: {name}")
            return {"code": 0, "data": existing, "msg": "作者已存在"}

        # 创建作者记录
        now = datetime.now().isoformat()
        author = Author(
            id=f"author_{source_author_id or name}",
            source_author_id=source_author_id,
            name=name,
            tag=None,
            bio=contact.get("signature", ""),
            avatar_url=contact.get("headUrl", ""),
            cover_img_url=contact.get("coverImgUrl", ""),
            created_at=now,
            updated_at=now,
        )

        if db.create_author(author):
            logger.info(f"[add_author] 创建成功: {name}")
            return {"code": 0, "data": author, "msg": ""}
        else:
            logger.error(f"[add_author] 创建失败: {name}")
            return {"code": -1, "msg": "数据库创建失败"}

    def add_authors(self, keywords: list[str]) -> dict:
        """批量新增作者（强匹配）

        Args:
            keywords: 关键词列表

        Returns:
            {"success": int, "failed": int}
        """
        result = {"success": 0, "failed": 0}

        for keyword in keywords:
            add_result = self.add_author(keyword)
            if add_result.get("code") == 0:
                result["success"] += 1
            else:
                result["failed"] += 1

        logger.info(f"[add_authors] 完成: {result}")
        return result

    def get_author(self, author_id: str) -> Optional[Author]:
        """通过ID查询单个作者

        Args:
            author_id: 作者ID

        Returns:
            Author 或 None
        """
        return db.get_author(author_id)

    def get_author_by_name(self, name: str) -> Optional[Author]:
        """通过名称查询单个作者

        Args:
            name: 作者名称

        Returns:
            Author 或 None
        """
        return db.get_author_by_name(name)

    def get_all_authors(self) -> list[Author]:
        """查询所有作者

        Returns:
            作者列表
        """
        return db.list_authors()

    def get_author_delete_info(self, author_id: str) -> dict:
        """获取作者删除前的统计信息

        Args:
            author_id: 作者ID

        Returns:
            {
                "exists": bool,
                "downloaded_count": int,  # 已下载完成
                "downloading_count": int,  # 正在下载
                "pending_count": int,      # 待处理
                "total_count": int,        # 总视频数
            }
        """
        author = db.get_author(author_id)
        if not author:
            return {
                "exists": False,
                "downloaded_count": 0,
                "downloading_count": 0,
                "pending_count": 0,
                "total_count": 0,
            }

        videos = db.list_author_videos(author_id)

        downloaded_count = 0
        downloading_count = 0
        pending_count = 0

        for video in videos:
            if video.is_downloaded == 1:
                downloaded_count += 1
            else:
                # 检查是否有任务记录
                task = db.get_download_task_by_video_id(video.video_id)
                if task and task.status in ["pending", "running"]:
                    downloading_count += 1
                else:
                    pending_count += 1

        return {
            "exists": True,
            "downloaded_count": downloaded_count,
            "downloading_count": downloading_count,
            "pending_count": pending_count,
            "total_count": len(videos),
        }

    def delete_author(self, author_id: str) -> bool:
        """删除作者及其所有视频（用户确认后调用）

        删除内容：
        - 本地磁盘文件及作者文件夹
        - Go后端任务（正在下载或已完成）
        - 我们的任务记录
        - 视频记录
        - 作者记录

        Args:
            author_id: 作者ID

        Returns:
            是否成功
        """
        from pathlib import Path
        import shutil

        author = db.get_author(author_id)
        if not author:
            logger.warning(f"[delete_author] 作者不存在: {author_id}")
            return False

        # 获取该作者的所有视频
        videos = db.list_author_videos(author_id)

        # 收集作者文件夹目录（去重）
        author_dirs = set()

        # 删除视频记录和文件
        for video in videos:
            # 收集作者文件夹路径（从 download_path 的父目录推断）
            if video.download_path:
                p = Path(video.download_path)
                if p.parent.exists():
                    author_dirs.add(p.parent)

            # 删除本地文件
            self._delete_local_file(video.download_path)

            # 取消/删除 Go 后端任务
            self._cancel_backend_task(video.video_id)

            # 删除我们的任务记录（如果有）
            task = db.get_download_task_by_video_id(video.video_id)
            if task:
                db.delete_download_task(task.task_id)
                logger.info(f"[delete_author] 删除任务记录: {task.task_id}")

            # 删除视频记录
            db.delete_author_video(video.video_id)
            logger.info(f"[delete_author] 删除视频记录: {video.video_id}")

        # 删除作者文件夹
        for author_dir in author_dirs:
            try:
                if author_dir.exists():
                    shutil.rmtree(str(author_dir))
                    logger.info(f"[delete_author] 已删除作者文件夹: {author_dir}")
            except Exception as e:
                logger.warning(f"[delete_author] 删除作者文件夹失败: {author_dir}, {e}")

        # 删除作者记录
        if not db.delete_author(author_id):
            logger.error(f"[delete_author] 删除作者失败: {author_id}")
            return False

        logger.info(f"[delete_author] 删除成功: {author_id}, 共删除 {len(videos)} 个视频, {len(author_dirs)} 个文件夹")
        return True

    def _cancel_backend_task(self, video_id: str):
        """取消后端下载任务

        Args:
            video_id: 视频ID
        """
        import requests

        try:
            # 查询任务列表
            resp = requests.get(
                f"{self.api_base_url}/api/task/list",
                timeout=10
            )
            data = resp.json()
            task_list = data.get("data", {}).get("list", [])

            # 找到对应的任务并取消（video_id 可能在 id 或 opts.video_id 中）
            for task in task_list:
                task_id = task.get("id", "")
                meta = task.get("meta", {})
                req = meta.get("req", {})
                labels = req.get("labels", {})

                # 检查 labels.id (video_id)
                if labels.get("id") == video_id:
                    if task_id:
                        requests.post(
                            f"{self.api_base_url}/api/task/delete",
                            json={"id": task_id},
                            timeout=10
                        )
                        logger.info(f"[_cancel_backend_task] 已删除任务: {task_id}")
                    break

        except Exception as e:
            logger.warning(f"[_cancel_backend_task] 取消任务失败: {e}")

    def _delete_local_file(self, download_path: str):
        """删除本地视频文件"""
        if not download_path:
            return

        from pathlib import Path

        path = Path(download_path)
        if not path.exists():
            return

        try:
            if path.is_file():
                path.unlink()
                logger.info(f"[_delete_local_file] 已删除文件: {path}")
            elif path.is_dir():
                # 删除目录下的视频文件
                video_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.flv']
                for ext in video_extensions:
                    for f in path.glob(f'*{ext}'):
                        try:
                            f.unlink()
                            logger.info(f"[_delete_local_file] 已删除文件: {f}")
                        except Exception as e:
                            logger.warning(f"[_delete_local_file] 删除失败: {f}, {e}")

                # 如果目录为空，删除目录
                if not any(path.iterdir()):
                    path.rmdir()
                    logger.info(f"[_delete_local_file] 已删除空目录: {path}")
        except Exception as e:
            logger.warning(f"[_delete_local_file] 清理失败: {download_path}, {e}")
