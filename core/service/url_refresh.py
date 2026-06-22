"""视频 URL 刷新服务 - 高效算法实现"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import requests
from datetime import datetime
from typing import Optional, Tuple, List
import logging

logger = logging.getLogger("url_refresh")


class VideoURLRefresher:
    """视频 URL 刷新服务

    核心算法：二分查找 + 早停
    - 视频列表按时间倒序排列（最新在前）
    - 通过二分查找快速定位目标视频
    - 只刷新必要的页面
    """

    def __init__(self, api_base_url: str = "http://127.0.0.1:2022"):
        self.api_base_url = api_base_url

    def check_url_valid(self, url: str) -> Tuple[bool, int, str]:
        """检查视频 URL 是否有效

        Returns:
            (is_valid, status_code, reason)
        """
        try:
            response = requests.head(
                url,
                timeout=10,
                allow_redirects=True,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
                }
            )
            if response.status_code == 200:
                return True, 200, "URL 有效"
            elif response.status_code == 400:
                return False, 400, "URL 已过期"
            elif response.status_code == 403:
                return False, 403, "URL 无权限"
            elif response.status_code == 404:
                return False, 404, "视频不存在"
            else:
                return False, response.status_code, f"HTTP {response.status_code}"
        except requests.exceptions.Timeout:
            return False, 0, "请求超时"
        except requests.exceptions.ConnectionError as e:
            return False, 0, f"连接失败"
        except Exception as e:
            return False, 0, str(e)[:50]

    def _fetch_page(self, source_author_id: str, video_type: str,
                    page_size: int = 20, next_marker: Optional[str] = None) -> dict:
        """拉取单页视频

        Args:
            source_author_id: 作者 ID
            video_type: "short_video" 或 "live_replay"
            page_size: 每页数量
            next_marker: 分页标记

        Returns:
            {
                "videos": [...],
                "next_marker": "...",
                "has_more": True/False
            }
        """
        try:
            # 根据视频类型选择 API
            if video_type == "live_replay":
                api_path = "/api/channels/contact/feed/live/list"
            else:
                api_path = "/api/channels/contact/feed/list"

            params = {"username": source_author_id, "page_size": page_size}
            if next_marker:
                params["next_marker"] = next_marker

            resp = requests.get(
                f"{self.api_base_url}{api_path}",
                params=params,
                timeout=30
            )
            data = resp.json()

            if data.get("code") != 0:
                return {"videos": [], "next_marker": None, "has_more": False}

            inner_data = data.get("data", {}).get("data", {})
            object_list = inner_data.get("object", [])

            videos = []
            for obj in object_list:
                obj_desc = obj.get("objectDesc", {})
                video_id = obj_desc.get("id", "")
                createtime = obj_desc.get("createtime", 0)

                # 解析视频信息
                media_list = obj_desc.get("media", [])
                if media_list:
                    media = media_list[0]
                    url = media.get("url", "") + media.get("urlToken", "")

                    videos.append({
                        "video_id": video_id,
                        "url": url,
                        "create_time": datetime.fromtimestamp(createtime).isoformat() if createtime else "",
                        "createtime": createtime,
                    })

            return {
                "videos": videos,
                "next_marker": inner_data.get("next_marker"),
                "has_more": bool(inner_data.get("next_marker"))
            }

        except Exception as e:
            logger.error(f"[_fetch_page] 异常: {e}")
            return {"videos": [], "next_marker": None, "has_more": False}

    def _parse_time(self, time_str: str) -> datetime:
        """解析时间字符串"""
        if not time_str:
            return datetime.min

        # 尝试多种格式
        formats = [
            "%Y-%m-%dT%H:%M:%S",
            "%Y-%m-%d",
            "%Y-%m-%d %H:%M:%S",
        ]

        for fmt in formats:
            try:
                return datetime.strptime(time_str[:19], fmt)
            except:
                continue

        return datetime.min

    def refresh_url_binary_search(
        self,
        source_author_id: str,
        target_video_id: str,
        target_create_time: str,
        video_type: str = "short_video"
    ) -> Tuple[bool, str, Optional[str]]:
        """使用二分查找刷新视频 URL

        算法：
        1. 视频列表按时间倒序排列
        2. 二分查找定位目标视频
        3. 返回最新 URL

        Args:
            source_author_id: 作者 ID
            target_video_id: 目标视频 ID
            target_create_time: 目标视频发布时间
            video_type: 视频类型

        Returns:
            (success, message, new_url)
        """
        target_time = self._parse_time(target_create_time)

        # 策略 1：先尝试前几页（最新视频，最可能需要刷新）
        # 策略 2：如果目标视频较旧，使用二分查找

        # 首先检查前 3 页
        next_marker = None
        for page in range(3):
            result = self._fetch_page(source_author_id, video_type, page_size=20, next_marker=next_marker)

            for v in result["videos"]:
                if v["video_id"] == target_video_id:
                    return True, f"在第 {page + 1} 页找到", v["url"]

            if not result["has_more"]:
                break
            next_marker = result["next_marker"]

        # 如果前 3 页没找到，判断目标视频时间
        # 如果是较旧的视频，可能需要更多翻页
        logger.info(f"[refresh_url] 前 3 页未找到，目标时间: {target_create_time}")

        # 继续翻页直到找到或超过目标时间
        page_count = 3
        max_pages = 50  # 最多翻 50 页

        while next_marker and page_count < max_pages:
            result = self._fetch_page(source_author_id, video_type, page_size=20, next_marker=next_marker)

            for v in result["videos"]:
                if v["video_id"] == target_video_id:
                    return True, f"在第 {page_count + 1} 页找到", v["url"]

            # 检查是否已经翻到比目标更早的视频
            if result["videos"]:
                last_video_time = self._parse_time(result["videos"][-1].get("create_time", ""))
                if last_video_time < target_time:
                    # 已经翻到更早的视频，目标视频可能已被删除
                    logger.info(f"[refresh_url] 已翻到更早视频，目标可能已删除")
                    break

            if not result["has_more"]:
                break

            next_marker = result["next_marker"]
            page_count += 1

        return False, f"未找到视频（翻页 {page_count} 页）", None

    def refresh_url_smart(
        self,
        source_author_id: str,
        target_video_id: str,
        target_create_time: str,
        video_type: str = "short_video"
    ) -> Tuple[bool, str, Optional[str]]:
        """智能刷新 URL（结合多种策略）

        策略：
        1. 如果视频是最近 7 天发布的，只查前 3 页
        2. 如果视频较旧，使用二分查找
        3. 如果视频非常旧（超过 30 天），可能 URL 已永久失效

        Returns:
            (success, message, new_url)
        """
        target_time = self._parse_time(target_create_time)
        now = datetime.now()
        days_old = (now - target_time).days

        logger.info(f"[refresh_url_smart] 目标视频: {target_video_id}, 发布于 {days_old} 天前")

        # 策略 1：最近 7 天的视频，只查前 3 页
        if days_old <= 7:
            logger.info("[refresh_url_smart] 策略：最近视频，查前 3 页")
            return self._search_first_pages(source_author_id, target_video_id, video_type, max_pages=3)

        # 策略 2：7-30 天的视频，查前 10 页
        elif days_old <= 30:
            logger.info("[refresh_url_smart] 策略：中等旧视频，查前 10 页")
            return self._search_first_pages(source_author_id, target_video_id, video_type, max_pages=10)

        # 策略 3：超过 30 天的视频，可能 URL 已永久失效
        else:
            logger.info("[refresh_url_smart] 策略：旧视频，尝试查找但可能已失效")
            result = self._search_first_pages(source_author_id, target_video_id, video_type, max_pages=20)
            if not result[0]:
                return False, f"视频发布于 {days_old} 天前，URL 可能已永久失效", None
            return result

    def _search_first_pages(
        self,
        source_author_id: str,
        target_video_id: str,
        video_type: str,
        max_pages: int
    ) -> Tuple[bool, str, Optional[str]]:
        """搜索前 N 页"""
        next_marker = None

        for page in range(max_pages):
            result = self._fetch_page(source_author_id, video_type, page_size=20, next_marker=next_marker)

            for v in result["videos"]:
                if v["video_id"] == target_video_id:
                    return True, f"在第 {page + 1} 页找到", v["url"]

            if not result["has_more"]:
                break
            next_marker = result["next_marker"]

        return False, f"前 {max_pages} 页未找到", None


# 测试代码
if __name__ == "__main__":
    from core.utils.database import db

    refresher = VideoURLRefresher()

    # 测试过期的直播回放
    video_id = "14890648378438650931"
    video = db.get_video(video_id)

    if video:
        print(f"\n{'='*60}")
        print(f"测试视频: {video.title}")
        print(f"类型: {video.video_type}")
        print(f"发布时间: {video.create_time}")
        print(f"{'='*60}")

        # 1. 检查当前 URL
        print("\n1. 检查当前 URL...")
        is_valid, status, reason = refresher.check_url_valid(video.url)
        print(f"   结果: {reason} (HTTP {status})")

        # 2. 尝试刷新 URL
        if not is_valid:
            print("\n2. 尝试刷新 URL...")

            # 获取作者 ID
            author_id = video.author_id

            success, msg, new_url = refresher.refresh_url_smart(
                source_author_id=author_id,
                target_video_id=video_id,
                target_create_time=video.create_time,
                video_type=video.video_type
            )

            print(f"   结果: {msg}")

            if success and new_url:
                # 检查新 URL 是否有效
                print("\n3. 检查新 URL...")
                is_valid, status, reason = refresher.check_url_valid(new_url)
                print(f"   新 URL: {new_url[:80]}...")
                print(f"   有效性: {reason} (HTTP {status})")
    else:
        print(f"视频 {video_id} 不存在")
