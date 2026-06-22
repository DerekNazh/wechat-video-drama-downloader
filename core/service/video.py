"""视频服务层

提供作者和视频的业务逻辑操作
"""

import logging
import requests
from datetime import datetime
from typing import Optional

from core.utils.database import db, Author, AuthorVideo
from core.utils.video_utils import (
    deduplicate_by_title,
    resolve_all_duplicate_titles,
)

logger = logging.getLogger("video_service")


class VideoService:
    """视频服务

    提供作者视频的增删查功能
    """

    def __init__(self, api_base_url: str = "http://127.0.0.1:2022"):
        self.api_base_url = api_base_url

    # ============================================================
    # 查询方法
    # ============================================================

    def get_all_authors_with_videos(self) -> list[dict]:
        """获取所有作者及其视频

        Returns:
            [{"author": Author, "videos": [AuthorVideo, ...]}, ...]
        """
        authors = db.list_authors()
        result = []

        for author in authors:
            videos = db.list_author_videos(author.id)
            result.append({
                "author": author,
                "videos": videos,
            })

        return result

    def get_author_videos(self, author_id: str) -> list[AuthorVideo]:
        """获取指定作者的所有视频

        Args:
            author_id: 作者ID

        Returns:
            视频列表，不存在则返回空列表
        """
        return db.list_author_videos(author_id)

    def get_author_videos_by_type(self, author_id: str, video_type: str) -> list[AuthorVideo]:
        """获取指定作者指定类型的视频

        Args:
            author_id: 作者ID
            video_type: 视频类型 ("short_video" / "live_replay")

        Returns:
            视频列表，不存在则返回空列表
        """
        return db.list_author_videos_by_type(author_id, video_type)

    def get_video_detail(self, video_id: str) -> Optional[AuthorVideo]:
        """获取视频详情

        Args:
            video_id: 视频ID

        Returns:
            AuthorVideo 或 None
        """
        return db.get_author_video(video_id)

    # ============================================================
    # 新增方法
    # ============================================================

    def add_author_latest_videos(self, author_id: str) -> dict:
        """增量同步作者视频

        基于作者的 latest_publish_date 作为基准日期：
        - 首次同步（latest_publish_date 为空）→ 全量拉取
        - 后续同步 → 只入库比基准日期更新的视频，遇到更早的停止翻页
        这样用户删除的旧视频不会被重新拉回。

        包含两轮去重：
        1. 列表内部去重（去除重复标题）
        2. 与数据库已有记录去重（追加随机后缀）

        Args:
            author_id: 作者ID

        Returns:
            {"added": int, "skipped": int, "total": int}
        """
        result = {"added": 0, "skipped": 0, "total": 0, "new_video_ids": []}

        # 获取作者信息
        author = db.get_author(author_id)
        if not author:
            logger.warning(f"[add_author_latest_videos] 作者不存在: {author_id}")
            return result

        # 日期基准：有 latest_publish_date 则增量同步，否则全量同步
        since_date = author.latest_publish_date
        if since_date:
            logger.info(f"[add_author_latest_videos] 增量同步，基准日期: {since_date}")
        else:
            logger.info(f"[add_author_latest_videos] 首次同步，全量拉取")

        # 从后端获取视频列表（短视频+直播回放）
        try:
            videos_data = self._fetch_author_videos_from_backend(author.source_author_id, since_date=since_date)
            replays_data = self._fetch_author_replays_from_backend(author.source_author_id, since_date=since_date)
            # 短视频默认标记类型
            for v in videos_data:
                v.setdefault("video_type", "short_video")
            all_data = videos_data + replays_data
        except Exception as e:
            logger.error(f"[add_author_latest_videos] 获取后端视频失败: {e}")
            return result

        videos_data = all_data

        if not videos_data:
            logger.info(f"[add_author_latest_videos] 作者无视频: {author_id}")
            return result

        result["total"] = len(videos_data)

        # 第一轮去重：列表内部去重
        videos_data = deduplicate_by_title(videos_data, "title")
        logger.info(f"[add_author_latest_videos] 第一轮去重后: {len(videos_data)} 个")

        # 获取本地已有的 video_id 集合
        existing_videos = db.list_author_videos(author_id)
        existing_video_ids = {v.video_id for v in existing_videos}
        existing_titles = {v.title for v in existing_videos}

        # 第二轮去重：与数据库已有记录去重
        videos_data = resolve_all_duplicate_titles(videos_data, existing_titles, "title")
        logger.info(f"[add_author_latest_videos] 第二轮去重后: {len(videos_data)} 个")

        # 遍历入库
        for video_dict in videos_data:
            video_id = video_dict.get("video_id", "")
            if video_id in existing_video_ids:
                result["skipped"] += 1
                continue

            # 创建 AuthorVideo 并入库
            video = AuthorVideo(
                video_id=video_id,
                author_id=author_id,
                title=video_dict.get("title", ""),
                object_nonce_id=video_dict.get("object_nonce_id", ""),
                url=video_dict.get("url", ""),
                spec=video_dict.get("spec", ""),
                file_size=video_dict.get("file_size", 0),
                cover_url=video_dict.get("cover_url", ""),
                decode_key=video_dict.get("decode_key", 0),
                author_avatar=video_dict.get("author_avatar", ""),
                duration=video_dict.get("duration", 0),
                create_time=video_dict.get("create_time", ""),
                is_downloaded=0,
                download_path="",
                downloaded_at=None,
                video_type=video_dict.get("video_type", "short_video"),
            )

            if db.create_author_video(video):
                result["added"] += 1
                result["new_video_ids"].append(video_id)
            else:
                result["skipped"] += 1

        # 更新作者信息：从视频 contact 字段提取最新信息
        for vd in videos_data:
            nickname = vd.get("author_name", "")
            avatar = vd.get("author_avatar", "")
            bio = vd.get("author_bio", "")
            cover_img = vd.get("author_cover_img", "")
            if nickname or avatar:
                if nickname:
                    author.name = nickname
                if avatar:
                    author.avatar_url = avatar
                if bio:
                    author.bio = bio
                if cover_img:
                    author.cover_img_url = cover_img
                author.updated_at = datetime.now().isoformat()
                db.update_author(author)
                logger.info(f"[add_author_latest_videos] 更新作者信息: name={nickname}, avatar={'set' if avatar else 'skip'}")
                break

        # 回写 latest_publish_date：只从本次新增入库的视频取最大时间
        # 这样 latest_publish_date 永远只往前走，删除视频不会导致基准回退
        if result["added"] > 0:
            new_times = []
            for video_dict in videos_data:
                vid = video_dict.get("video_id", "")
                if vid in result["new_video_ids"] and video_dict.get("create_time"):
                    new_times.append(video_dict["create_time"])
            if new_times:
                max_new_time = max(new_times)
                # 只在比当前基准更新时才更新（避免回退）
                current = author.latest_publish_date
                if not current or max_new_time > current:
                    db.update_author_latest_publish_date(author_id, max_new_time)
                    logger.info(f"[add_author_latest_videos] 更新 latest_publish_date: {max_new_time}")

        logger.info(f"[add_author_latest_videos] 完成: {result}")
        return result

    def add_all_authors_latest_videos(self) -> dict:
        """批量同步所有作者的视频

        Returns:
            {
                "added": int,
                "skipped": int,
                "total": int,
                "authors_success": int,
                "authors_failed": int,
            }
        """
        result = {
            "added": 0,
            "skipped": 0,
            "total": 0,
            "authors_success": 0,
            "authors_failed": 0,
        }

        authors = db.list_authors()
        for author in authors:
            try:
                author_result = self.add_author_latest_videos(author.id)
                result["added"] += author_result.get("added", 0)
                result["skipped"] += author_result.get("skipped", 0)
                result["total"] += author_result.get("total", 0)
                if author_result.get("added", 0) > 0 or author_result.get("total", 0) > 0:
                    result["authors_success"] += 1
            except Exception as e:
                logger.error(f"[add_all_authors_latest_videos] 作者 {author.id} 处理失败: {e}")
                result["authors_failed"] += 1

        logger.info(f"[add_all_authors_latest_videos] 完成: {result}")
        return result

    def sync_and_get_new_videos(self) -> dict:
        """同步所有作者最新视频并返回新增视频的详情

        用于前端轮询：只返回本次新增的视频，不做全量返回。

        Returns:
            {
                "added": int,
                "new_videos": [{"video_id", "author_id", "title", ...}, ...],
                "authors_success": int,
                "authors_failed": int,
            }
        """
        new_video_ids = []
        authors_success = 0
        authors_failed = 0

        authors = db.list_authors()
        for author in authors:
            try:
                author_result = self.add_author_latest_videos(author.id)
                added = author_result.get("added", 0)
                if added > 0:
                    authors_success += 1
                    new_video_ids.extend(author_result.get("new_video_ids", []))
            except Exception as e:
                logger.error(f"[sync_and_get_new_videos] 作者 {author.id} 处理失败: {e}")
                authors_failed += 1

        new_videos = []
        for vid in new_video_ids:
            video = db.get_author_video(vid)
            if video:
                new_videos.append({
                    "video_id": video.video_id,
                    "author_id": video.author_id,
                    "title": video.title,
                    "duration": video.duration,
                    "cover_url": video.cover_url,
                    "file_size": video.file_size,
                    "create_time": video.create_time,
                    "is_downloaded": video.is_downloaded,
                    "download_path": video.download_path,
                })

        result = {
            "added": len(new_videos),
            "new_videos": new_videos,
            "authors_success": authors_success,
            "authors_failed": authors_failed,
        }

        logger.info(f"[sync_and_get_new_videos] 完成: added={result['added']}")
        return result

    # ============================================================
    # 删除方法
    # ============================================================

    def delete_video(self, video_id: str) -> bool:
        """删除单个视频

        同时清理：
        1. 本地磁盘文件
        2. 数据库记录
        3. 后端下载任务

        Args:
            video_id: 视频ID

        Returns:
            是否成功
        """
        video = db.get_author_video(video_id)
        if not video:
            logger.warning(f"[delete_video] 视频不存在: {video_id}")
            return False

        # 1. 删除本地磁盘文件
        download_path = video.download_path
        if download_path:
            self._delete_local_file(download_path)

        # 2. 删除数据库记录
        if not db.delete_author_video(video_id):
            logger.error(f"[delete_video] 删除数据库记录失败: {video_id}")
            return False

        # 3. 清理后端任务
        self._cancel_backend_task(video_id)

        logger.info(f"[delete_video] 删除成功: {video_id}")
        return True

    def _delete_local_file(self, download_path: str):
        """删除本地视频文件

        Args:
            download_path: 下载目录或文件路径
        """
        import os
        from pathlib import Path

        path = Path(download_path)
        if not path.exists():
            return

        try:
            if path.is_file():
                # 是文件，直接删除
                path.unlink()
                logger.info(f"[_delete_local_file] 已删除文件: {path}")
            elif path.is_dir():
                # 是目录，删除目录下的视频文件
                video_extensions = ['.mp4', '.avi', '.mkv', '.mov', '.flv']
                for ext in video_extensions:
                    for f in path.glob(f'*{ext}'):
                        try:
                            f.unlink()
                            logger.info(f"[_delete_local_file] 已删除文件: {f}")
                        except Exception as e:
                            logger.warning(f"[_delete_local_file] 删除文件失败: {f}, {e}")
                # 如果目录为空，删除目录
                try:
                    if not any(path.iterdir()):
                        path.rmdir()
                        logger.info(f"[_delete_local_file] 已删除空目录: {path}")
                except Exception:
                    pass
        except Exception as e:
            logger.warning(f"[_delete_local_file] 删除失败: {download_path}, {e}")

    def delete_videos(self, video_ids: list[str]) -> dict:
        """批量删除视频

        同时清理：
        1. 本地磁盘文件
        2. author_videos 数据库记录
        3. download_tasks 数据库记录
        4. 后端下载任务

        Args:
            video_ids: 视频ID列表

        Returns:
            {"deleted": int, "not_found": int, "failed": int}
        """
        result = {"deleted": 0, "not_found": 0, "failed": 0}

        for video_id in video_ids:
            video = db.get_author_video(video_id)
            if not video:
                result["not_found"] += 1
                continue

            # 1. 删除本地磁盘文件
            download_path = video.download_path
            if download_path:
                self._delete_local_file(download_path)

            # 2. 删除 author_videos 数据库记录
            if not db.delete_author_video(video_id):
                logger.error(f"[delete_videos] 删除数据库记录失败: {video_id}")
                result["failed"] += 1
                continue

            # 3. 清理 download_tasks 数据库记录
            task = db.get_download_task_by_video_id(video_id)
            if task:
                db.delete_download_task(task.task_id)

            # 4. 取消后端下载任务
            self._cancel_backend_task(video_id)

            result["deleted"] += 1

        logger.info(f"[delete_videos] 完成: {result}")
        return result

    # ============================================================
    # 私有方法
    # ============================================================

    def _fetch_author_videos_from_backend(self, source_author_id: str, since_date: str = None) -> list[dict]:
        """从后端获取作者视频列表

        Args:
            source_author_id: 作者的 source_author_id (username)
            since_date: ISO格式日期字符串，只获取此日期之后的视频，遇到更早的视频停止翻页

        Returns:
            视频字典列表
        """
        if not source_author_id:
            return []

        since_dt = None
        if since_date:
            try:
                since_dt = datetime.fromisoformat(since_date)
            except (ValueError, TypeError):
                logger.warning(f"[_fetch_author_videos_from_backend] since_date 格式无效: {since_date}")

        videos = []
        next_marker = None

        while True:
            try:
                params = {"username": source_author_id, "page_size": 20}
                if next_marker:
                    params["next_marker"] = next_marker

                resp = requests.get(
                    f"{self.api_base_url}/api/channels/contact/feed/list",
                    params=params,
                    timeout=30
                )
                data = resp.json()

                if data.get("code") != 0:
                    logger.warning(f"[_fetch_author_videos_from_backend] API 返回错误: {data.get('msg')}")
                    break

                inner_data = data.get("data", {}).get("data", {})
                object_list = inner_data.get("object", [])

                stop_paging = False
                page_has_new = False  # 当前页是否仍有新视频（处理页内乱序）
                for obj in object_list:
                    video_dict = self._parse_video_object(obj)
                    if video_dict:
                        # 日期基准过滤：跳过早于 since_date 的视频
                        if since_dt and video_dict.get("create_time"):
                            try:
                                video_dt = datetime.fromisoformat(video_dict["create_time"])
                                if video_dt <= since_dt:
                                    # 小于等于基准日期 → 已知视频，停止翻页
                                    stop_paging = True
                                    continue
                                # video_dt > since_dt → 新视频，正常收集
                            except (ValueError, TypeError):
                                pass
                        videos.append(video_dict)
                        page_has_new = True

                # 当前页遍历完毕后再判断是否停止翻页
                # 如果本页仍有新视频，说明时间线还没完全进入旧区间，继续翻页
                if stop_paging and not page_has_new:
                    logger.info(f"[_fetch_author_videos_from_backend] 整页均为旧视频，停止翻页（基准: {since_date}）")
                    break

                # 分页
                next_marker = inner_data.get("lastBuff")
                if not next_marker:
                    break

            except Exception as e:
                logger.error(f"[_fetch_author_videos_from_backend] 请求失败: {e}")
                break

        logger.info(f"[_fetch_author_videos_from_backend] 获取 {len(videos)} 个短视频" + (f"（基准日期: {since_date}）" if since_date else ""))
        return videos

    def _fetch_author_replays_from_backend(self, source_author_id: str, since_date: str = None) -> list[dict]:
        """从后端获取作者直播回放列表

        Args:
            source_author_id: 作者的 source_author_id (username)
            since_date: ISO格式日期字符串，只获取此日期之后的回放，遇到更早的停止翻页
        """
        if not source_author_id:
            return []

        since_dt = None
        if since_date:
            try:
                since_dt = datetime.fromisoformat(since_date)
            except (ValueError, TypeError):
                logger.warning(f"[_fetch_author_replays] since_date 格式无效: {since_date}")

        replays = []
        next_marker = None

        while True:
            try:
                params = {"username": source_author_id, "page_size": 20}
                if next_marker:
                    params["next_marker"] = next_marker

                resp = requests.get(
                    f"{self.api_base_url}/api/channels/live/replay/list",
                    params=params,
                    timeout=30
                )
                data = resp.json()

                if data.get("code") != 0:
                    logger.warning(f"[_fetch_author_replays] API 返回错误: {data.get('msg')}")
                    break

                inner_data = data.get("data", {}).get("data", {})
                object_list = inner_data.get("object", [])

                stop_paging = False
                page_has_new = False
                for obj in object_list:
                    video_dict = self._parse_video_object(obj)
                    if video_dict:
                        video_dict["video_type"] = "live_replay"
                        # 日期基准过滤
                        if since_dt and video_dict.get("create_time"):
                            try:
                                video_dt = datetime.fromisoformat(video_dict["create_time"])
                                if video_dt <= since_dt:
                                    stop_paging = True
                                    continue
                            except (ValueError, TypeError):
                                pass
                        replays.append(video_dict)
                        page_has_new = True

                # 整页均为旧回放时停止翻页
                if stop_paging and not page_has_new:
                    logger.info(f"[_fetch_author_replays] 整页均为旧回放，停止翻页（基准: {since_date}）")
                    break

                next_marker = inner_data.get("lastBuff")
                if not next_marker:
                    break

            except Exception as e:
                logger.error(f"[_fetch_author_replays] 请求失败: {e}")
                break

        logger.info(f"[_fetch_author_replays] 获取 {len(replays)} 个直播回放" + (f"（基准日期: {since_date}）" if since_date else ""))
        return replays

    def _parse_video_object(self, obj: dict) -> Optional[dict]:
        """解析后端返回的视频对象

        Args:
            obj: 后端返回的视频对象

        Returns:
            标准化的视频字典或 None（非视频类型返回 None）
        """
        video_id = obj.get("id", "")
        if not video_id:
            return None

        obj_desc = obj.get("objectDesc", {})
        title = obj_desc.get("description", "")
        object_nonce_id = obj.get("objectNonceId", "")
        createtime = obj.get("createtime", 0)

        media_list = obj_desc.get("media", [])
        if not media_list:
            return None

        media = media_list[0]
        # mediaType=4 是视频，mediaType=9 是图片，跳过非视频类型
        media_type = media.get("mediaType", 0)
        if media_type != 4:
            logger.info(f"[_parse_video_object] 跳过非视频类型 mediaType={media_type}, video_id={video_id}")
            return None

        url = media.get("url", "") + media.get("urlToken", "")
        original_file_size = media.get("fileSize", 0)
        cover_url = media.get("coverUrl", "")
        decode_key_str = media.get("decodeKey", "0")
        decode_key = int(decode_key_str) if decode_key_str else 0
        # 获取时长：优先 spec[0].durationMs（毫秒），fallback videoPlayLen（秒）
        duration_ms = 0
        spec_list = media.get("spec", [])
        if spec_list:
            duration_ms = spec_list[0].get("durationMs", 0)
        if not duration_ms:
            # videoPlayLen 单位是秒，需乘1000转为毫秒
            duration_ms = media.get("videoPlayLen", 0) * 1000

        # 原视频分辨率
        original_width = media.get("width", 0)
        original_height = media.get("height", 0)

        # 规格选择：优先压缩规格（xWT111等），迫不得已才用 original
        best_spec = "original"
        best_width = original_width
        best_height = original_height
        if spec_list:
            # 先找非 original 的压缩规格
            for s in spec_list:
                spec_format = s.get("fileFormat", "")
                if spec_format and spec_format != "original":
                    best_spec = spec_format
                    best_width = s.get("width", 0)
                    best_height = s.get("height", 0)
                    break
            # 如果没找到压缩规格，才用 original（但 original 不需要显式指定）
            if best_spec == "original":
                best_width = original_width
                best_height = original_height

        # 添加规格参数到 URL
        url = url + "&X-snsvideoflag=" + best_spec

        # 估算文件大小：按分辨率比例计算
        file_size = original_file_size
        if best_spec != "original" and original_width > 0 and original_height > 0 and best_width > 0 and best_height > 0:
            file_size = int(original_file_size * (best_width * best_height) / (original_width * original_height))

        contact = obj.get("contact", {})
        author_name = contact.get("nickname", "")
        author_avatar = contact.get("headUrl", "")
        author_bio = contact.get("signature", "")
        author_cover_img = contact.get("coverImgUrl", "")

        # 转换时间
        create_time = ""
        if createtime:
            try:
                create_time = datetime.fromtimestamp(createtime).isoformat()
            except:
                pass

        return {
            "video_id": video_id,
            "title": title,
            "object_nonce_id": object_nonce_id,
            "url": url,
            "spec": best_spec,
            "file_size": file_size,
            "cover_url": cover_url,
            "decode_key": decode_key,
            "author_name": author_name,
            "author_avatar": author_avatar,
            "author_bio": author_bio,
            "author_cover_img": author_cover_img,
            "duration": duration_ms // 1000 if duration_ms else 0,
            "create_time": create_time,
        }

    def _cancel_backend_task(self, video_id: str):
        """取消后端下载任务

        Args:
            video_id: 视频ID
        """
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
                opts = task.get("opts", {})
                # 检查 opts.video_id
                if opts.get("video_id") == video_id:
                    if task_id:
                        requests.post(
                            f"{self.api_base_url}/api/task/delete",
                            json={"id": task_id},
                            timeout=10
                        )
                        logger.info(f"[_cancel_backend_task] 已取消任务(匹配opts): {task_id}")
                    break
                # 检查任务 id
                if task_id == video_id:
                    requests.post(
                        f"{self.api_base_url}/api/task/delete",
                        json={"id": task_id},
                        timeout=10
                    )
                    logger.info(f"[_cancel_backend_task] 已取消任务(匹配id): {task_id}")
                    break

        except Exception as e:
            logger.warning(f"[_cancel_backend_task] 取消任务失败: {e}")
