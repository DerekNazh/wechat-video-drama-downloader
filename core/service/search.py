"""搜索服务层

提供作者搜索和视频拉取功能
"""

import logging
import requests
from typing import Optional, Tuple
from datetime import datetime

from core.utils.weixin_client import WechatVideoAPIClient
from core.utils.database import db

logger = logging.getLogger("search_service")


class SearchService:
    """搜索服务

    提供作者搜索和视频拉取功能
    """

    def __init__(self, api_base_url: str = "http://127.0.0.1:2022", client=None):
        self.api_base_url = api_base_url
        self._client = client or WechatVideoAPIClient(base_url=api_base_url)

    def search_author(self, keyword: str, exact_match: bool = True) -> dict:
        """搜索作者

        Args:
            keyword: 搜索关键词
            exact_match: True=严格模式，只返回精确匹配的单个结果
                         False=模糊模式，返回所有搜索结果列表

        Returns:
            严格模式: {"code": 0, "data": {...} or None, "msg": ""}
            模糊模式: {"code": 0, "data": [{username, nickname, ...}], "msg": ""}
        """
        if not keyword:
            logger.warning("[search_author] 关键词为空")
            return {"code": -1, "msg": "关键词不能为空"}

        search_result = self._client.search_authors(keyword)
        authors = search_result.get("authors", [])

        if not authors:
            logger.info(f"[search_author] 搜索无结果: {keyword}")
            return {"code": 0, "data": None if exact_match else [], "msg": "无搜索结果"}

        if exact_match:
            for item in authors:
                contact = item.get("contact", {})
                nickname = contact.get("nickname", "")
                if nickname == keyword:
                    author_data = self._parse_author(item)
                    logger.info(f"[search_author] 强匹配成功: {nickname}")
                    return {"code": 0, "data": author_data, "msg": ""}

            logger.info(f"[search_author] 未找到精确匹配: {keyword}")
            return {"code": 0, "data": None, "msg": "未找到精确匹配的作者"}

        # 模糊模式：返回所有结果列表
        results = []
        for item in authors:
            contact = item.get("contact", {})
            results.append({
                "username": contact.get("username", ""),
                "nickname": contact.get("nickname", ""),
                "head_url": contact.get("headUrl", ""),
                "signature": contact.get("signature", ""),
                "cover_img_url": contact.get("coverImgUrl", ""),
                "friend_count": item.get("friendFollowCount", 0),
            })
        logger.info(f"[search_author] 模糊模式返回 {len(results)} 个结果")
        return {"code": 0, "data": results, "msg": ""}

    def get_author_videos_smart(
        self,
        source_author_id: str,
        target_date=None,
        video_type: str = "all"
    ) -> dict:
        """智能拉取作者视频（基于时间动态调整翻页深度）

        算法：
        1. 如果 target_date 是最近 7 天，只翻 3 页
        2. 如果 target_date 是 7-30 天，翻 10 页
        3. 如果 target_date 超过 30 天，翻 20 页
        4. 如果未指定 target_date，默认翻 5 页

        Args:
            source_author_id: 作者ID
            target_date: 目标日期（用于计算翻页深度）
            video_type: "short_video", "live_replay", "all"

        Returns:
            {"code": 0, "data": [...], "msg": ""}
        """
        if not source_author_id:
            return {"code": -1, "msg": "作者ID不能为空"}

        # 计算翻页深度
        max_pages = self._calculate_page_depth(target_date)
        logger.info(f"[get_author_videos_smart] 目标日期: {target_date}, 翻页深度: {max_pages}")

        all_videos = []

        # 短视频
        if video_type in ("short_video", "all"):
            videos = self._fetch_videos_with_limit(
                source_author_id, "short_video", max_pages
            )
            all_videos.extend(videos)

        # 直播回放
        if video_type in ("live_replay", "all"):
            replays = self._fetch_videos_with_limit(
                source_author_id, "live_replay", max_pages
            )
            all_videos.extend(replays)

        # 去重
        seen_ids = set()
        unique_videos = []
        for v in all_videos:
            if v["video_id"] not in seen_ids:
                seen_ids.add(v["video_id"])
                unique_videos.append(v)

        logger.info(f"[get_author_videos_smart] 共拉取 {len(unique_videos)} 个视频")

        # 更新作者最新发布时间
        self._update_author_latest_publish_date(source_author_id, unique_videos)

        return {"code": 0, "data": unique_videos, "msg": ""}

    def _calculate_page_depth(self, target_date) -> int:
        """根据目标日期计算翻页深度

        Args:
            target_date: 目标日期

        Returns:
            翻页深度（页数）
        """
        if not target_date:
            return 5  # 默认翻 5 页

        target_dt = self._parse_date(target_date)
        if not target_dt:
            return 5

        now = datetime.now()
        days_diff = (now - target_dt).days

        if days_diff <= 7:
            return 3   # 最近 7 天：3 页
        elif days_diff <= 30:
            return 10  # 7-30 天：10 页
        else:
            return 20  # 超过 30 天：20 页

    def _fetch_videos_with_limit(
        self,
        source_author_id: str,
        video_type: str,
        max_pages: int
    ) -> list:
        """带页数限制的视频拉取

        Args:
            source_author_id: 作者ID
            video_type: "short_video" 或 "live_replay"
            max_pages: 最大页数

        Returns:
            视频列表
        """
        videos = []
        next_marker = None

        for _ in range(max_pages):
            if video_type == "live_replay":
                result = self._client.get_author_replays(
                    source_author_id, page_size=20, last_buff=next_marker
                )
            else:
                result = self._client.get_author_videos(
                    source_author_id, page_size=20, last_buff=next_marker
                )

            if result.get("code") != 0:
                break

            data = result.get("data", [])
            if not data:
                break

            for obj in data:
                video = self._parse_video(obj)
                if video:
                    video.setdefault("video_type", video_type)
                    videos.append(video)

            next_marker = result.get("next_marker")
            if not next_marker:
                break

        return videos

    def refresh_video_url(
        self,
        source_author_id: str,
        target_video_id: str,
        target_create_time: str,
        video_type: str = "short_video"
    ) -> dict:
        """刷新视频 URL（智能查找）

        根据视频发布时间动态调整搜索范围：
        - 最近 7 天：查前 3 页
        - 7-30 天：查前 10 页
        - 超过 30 天：查前 20 页

        Args:
            source_author_id: 作者ID
            target_video_id: 目标视频ID
            target_create_time: 目标视频发布时间
            video_type: 视频类型

        Returns:
            {"code": 0, "data": {"url": "..."}, "msg": ""} 或
            {"code": -1, "msg": "未找到"}
        """
        if not source_author_id or not target_video_id:
            return {"code": -1, "msg": "参数不完整"}

        # 计算翻页深度
        max_pages = self._calculate_page_depth(target_create_time)
        logger.info(f"[refresh_video_url] 视频ID: {target_video_id}, 发布时间: {target_create_time}, 翻页深度: {max_pages}")

        # 搜索视频
        next_marker = None
        for page in range(max_pages):
            if video_type == "live_replay":
                result = self._client.get_author_replays(
                    source_author_id, page_size=20, last_buff=next_marker
                )
            else:
                result = self._client.get_author_videos(
                    source_author_id, page_size=20, last_buff=next_marker
                )

            if result.get("code") != 0:
                break

            data = result.get("data", [])
            if not data:
                break

            # 在当前页查找目标视频
            for obj in data:
                video_id = obj.get("id", "")
                if video_id == target_video_id:
                    # 找到了，解析并返回新 URL
                    video = self._parse_video(obj)
                    if video:
                        logger.info(f"[refresh_video_url] 在第 {page + 1} 页找到视频")
                        return {"code": 0, "data": {"url": video.get("url", "")}, "msg": f"在第 {page + 1} 页找到"}

            next_marker = result.get("next_marker")
            if not next_marker:
                break

        logger.warning(f"[refresh_video_url] 未找到视频，已搜索 {max_pages} 页")
        return {"code": -1, "msg": f"未找到视频（已搜索 {max_pages} 页）"}

    def check_url_valid(self, url: str) -> Tuple[bool, int, str]:
        """检查视频 URL 是否有效

        Args:
            url: 视频 URL

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
        except requests.exceptions.ConnectionError:
            return False, 0, "连接失败"
        except Exception as e:
            return False, 0, str(e)[:50]

    def ensure_valid_url(
        self,
        url: str,
        source_author_id: str,
        video_id: str,
        create_time: str,
        video_type: str = "short_video"
    ) -> dict:
        """确保 URL 有效，过期时自动刷新

        Args:
            url: 当前 URL
            source_author_id: 作者 ID
            video_id: 视频 ID
            create_time: 视频发布时间
            video_type: 视频类型

        Returns:
            {"code": 0, "data": {"url": "...", "refreshed": True/False}, "msg": ""}
            或 {"code": -1, "msg": "刷新失败"}
        """
        # 检查当前 URL 有效性
        is_valid, status, reason = self.check_url_valid(url)

        if is_valid:
            # URL 有效，直接返回
            return {"code": 0, "data": {"url": url, "refreshed": False}, "msg": "URL 有效"}

        logger.info(f"[ensure_valid_url] URL 过期: video_id={video_id}, status={status}, reason={reason}")

        # URL 过期，尝试刷新
        refresh_result = self.refresh_video_url(
            source_author_id=source_author_id,
            target_video_id=video_id,
            target_create_time=create_time,
            video_type=video_type
        )

        if refresh_result["code"] == 0:
            new_url = refresh_result["data"]["url"]
            logger.info(f"[ensure_valid_url] URL 刷新成功: video_id={video_id}")
            return {"code": 0, "data": {"url": new_url, "refreshed": True}, "msg": "URL 已刷新"}
        else:
            logger.warning(f"[ensure_valid_url] URL 刷新失败: video_id={video_id}, msg={refresh_result['msg']}")
            return {"code": -1, "msg": f"URL 过期且刷新失败: {refresh_result['msg']}"}

    def get_author_videos(self, source_author_id: str, pages: int = 1, on_progress=None) -> dict:
        """拉取作者视频（指定页数，短视频+直播回放）

        Args:
            source_author_id: 作者ID
            pages: 页数（默认1页，每页15条，短视频和直播回放各拉取该页数）
            on_progress: 进度回调 on_progress(phase, current, total, message)

        Returns:
            {"code": 0, "data": [...], "msg": ""} 或 {"code": -1, "msg": "错误信息"}
        """
        if not source_author_id:
            return {"code": -1, "msg": "作者ID不能为空"}

        if pages < 0:
            return {"code": -1, "msg": "页数不能为负数"}

        if pages == 0:
            return {"code": 0, "data": [], "msg": ""}

        all_videos = []
        sv_parsed_total = 0
        replay_parsed_total = 0

        # 短视频
        next_marker = None
        sv_raw_total = 0
        for page_idx in range(pages):
            result = self._client.get_author_videos(source_author_id, page_size=15, last_buff=next_marker)
            if result.get("code") != 0:
                logger.info(f"[get_author_videos] 短视频第{page_idx+1}页请求失败, code={result.get('code')}")
                break

            videos = result.get("data", [])
            if not videos:
                logger.info(f"[get_author_videos] 短视频第{page_idx+1}页无数据")
                break

            sv_raw_total += len(videos)
            logger.info(f"[get_author_videos] 短视频第{page_idx+1}页: 原始{len(videos)}条, next_marker={result.get('next_marker')}")

            for obj in videos:
                video = self._parse_video(obj)
                if video:
                    video.setdefault("video_type", "short_video")
                    all_videos.append(video)
                    sv_parsed_total += 1

            if on_progress:
                on_progress("fetching", len(all_videos), None, f"短视频第{page_idx+1}/{pages}页", video_type="short_video", short_video_count=sv_parsed_total, replay_count=replay_parsed_total)

            next_marker = result.get("next_marker")
            if not next_marker:
                logger.info(f"[get_author_videos] 短视频无更多页，在第{page_idx+1}页停止")
                break

        logger.info(f"[get_author_videos] 短视频汇总: 原始{sv_raw_total}条, 解析成功{sv_parsed_total}条")

        # 直播回放
        replay_marker = None
        replay_raw_total = 0
        replay_skipped_log = []
        for page_idx in range(pages):
            result = self._client.get_author_replays(source_author_id, page_size=15, last_buff=replay_marker)
            if result.get("code") != 0:
                logger.info(f"[get_author_videos] 直播回放第{page_idx+1}页请求失败, code={result.get('code')}")
                break

            replays = result.get("data", [])
            if not replays:
                logger.info(f"[get_author_videos] 直播回放第{page_idx+1}页无数据")
                break

            replay_raw_total += len(replays)
            next_marker_raw = result.get("next_marker")
            logger.info(f"[get_author_videos] 直播回放第{page_idx+1}页: 原始{len(replays)}条, next_marker={next_marker_raw}")

            for obj in replays:
                video = self._parse_video(obj)
                if video:
                    video["video_type"] = "live_replay"
                    all_videos.append(video)
                    replay_parsed_total += 1
                else:
                    vid = obj.get("id", "未知ID")
                    obj_desc = obj.get("objectDesc", {})
                    media_list = obj_desc.get("media", [])
                    media_type = media_list[0].get("mediaType", "无media") if media_list else "无media数组"
                    replay_skipped_log.append(f"id={vid}, mediaType={media_type}")

            if on_progress:
                on_progress("fetching", len(all_videos), None, f"回放第{page_idx+1}/{pages}页", video_type="live_replay", short_video_count=sv_parsed_total, replay_count=replay_parsed_total)

            replay_marker = result.get("next_marker")
            if not replay_marker:
                logger.info(f"[get_author_videos] 直播回放无更多页，在第{page_idx+1}页停止")
                break

        if replay_skipped_log:
            logger.warning(f"[get_author_videos] 直播回放跳过{len(replay_skipped_log)}条: {replay_skipped_log}")
        logger.info(f"[get_author_videos] 直播回放汇总: 原始{replay_raw_total}条, 解析成功{replay_parsed_total}条, 跳过{replay_raw_total - replay_parsed_total}条")

        # 去重
        seen_ids = set()
        unique_videos = []
        for v in all_videos:
            if v["video_id"] not in seen_ids:
                seen_ids.add(v["video_id"])
                unique_videos.append(v)

        logger.info(f"[get_author_videos] 拉取 {pages} 页，短视频+直播回放共 {len(unique_videos)} 个视频")

        # 更新作者最新发布时间
        self._update_author_latest_publish_date(source_author_id, unique_videos)

        return {"code": 0, "data": unique_videos, "msg": ""}

    def get_author_videos_by_date_range(
        self,
        source_author_id: str,
        start_date,
        end_date
    ) -> dict:
        """拉取指定日期范围内的视频

        Args:
            source_author_id: 作者ID
            start_date: 开始日期（时间戳或 YYYY-MM-DD）
            end_date: 结束日期（时间戳或 YYYY-MM-DD）

        Returns:
            {"code": 0, "data": [...], "msg": ""} 或 {"code": -1, "msg": "错误信息"}
        """
        if not source_author_id:
            return {"code": -1, "msg": "作者ID不能为空"}

        # 解析日期
        start_dt = self._parse_date(start_date)
        end_dt = self._parse_date(end_date)

        if not start_dt or not end_dt:
            return {"code": -1, "msg": "日期格式错误"}

        # 检查日期顺序
        if start_dt > end_dt:
            return {"code": -1, "msg": "开始日期不能晚于结束日期"}

        # 拉取所有视频并过滤
        all_videos_result = self._get_all_videos(source_author_id)
        if all_videos_result.get("code") != 0:
            return all_videos_result

        all_videos = all_videos_result.get("data", [])

        # 过滤日期范围
        filtered = []
        for v in all_videos:
            create_time = v.get("create_time", "")
            if create_time:
                video_dt = self._parse_date(create_time)
                if video_dt and start_dt <= video_dt <= end_dt:
                    filtered.append(v)

        logger.info(f"[get_author_videos_by_date_range] 日期范围 {start_date} ~ {end_date}，共 {len(filtered)} 个视频")
        return {"code": 0, "data": filtered, "msg": ""}

    def get_author_videos_before_date(self, source_author_id: str, before_date, on_progress=None) -> dict:
        """拉取指定日期到今天的视频

        逐页获取，按日期过滤。当某页中所有可解析日期的视频
        都早于 before_date 时停止翻页（后续页只会更旧）。

        Args:
            source_author_id: 作者ID
            before_date: 截止日期（时间戳或 YYYY-MM-DD）
            on_progress: 进度回调 on_progress(phase, current, total, message, **kwargs)

        Returns:
            {"code": 0, "data": [...], "msg": ""} 或 {"code": -1, "msg": "错误信息"}
        """
        logger.info(f"[get_author_videos_before_date] 入口: source_author_id={source_author_id[:30]}..., before_date={before_date}")

        if not source_author_id:
            return {"code": -1, "msg": "作者ID不能为空"}

        # 解析日期
        before_dt = self._parse_date(before_date)
        if not before_dt:
            logger.warning(f"[get_author_videos_before_date] 日期解析失败: {before_date}")
            return {"code": -1, "msg": "日期格式错误"}

        today = datetime.now()
        filtered = []
        short_video_count = 0
        replay_count = 0
        total_fetched = 0

        # 短视频：逐页获取，按日期过滤
        # API 返回的视频大致按时间倒序，当整页都早于临界值时停止
        next_marker = None
        while True:
            result = self._client.get_author_videos(source_author_id, page_size=20, last_buff=next_marker)
            if result.get("code") != 0:
                break

            videos = result.get("data", [])
            if not videos:
                break

            page_matched = 0
            page_all_before = True  # 假设整页都早于临界值，逐个否定

            for obj in videos:
                video = self._parse_video(obj)
                if not video:
                    continue
                video.setdefault("video_type", "short_video")
                total_fetched += 1

                create_time = video.get("create_time", "")
                if create_time:
                    video_dt = self._parse_date(create_time)
                    if video_dt:
                        if before_dt <= video_dt <= today:
                            filtered.append(video)
                            short_video_count += 1
                            page_matched += 1
                            page_all_before = False
                        elif video_dt < before_dt:
                            pass  # 早于临界值，不计数
                        else:
                            page_all_before = False  # 晚于 today，不算"都早于临界值"
                    else:
                        page_all_before = False  # 无法解析日期，保守不停
                else:
                    page_all_before = False  # 无日期字段，保守不停

            if on_progress:
                on_progress("fetching", total_fetched, None, f"短视频翻页中", video_type="short_video", short_video_count=short_video_count, replay_count=replay_count)

            # 整页无匹配且全部早于临界值 → 后续页只会更旧，停止
            if page_matched == 0 and page_all_before:
                logger.info(f"[get_author_videos_before_date] 短视频整页早于 {before_date}，停止翻页")
                break

            next_marker = result.get("next_marker")
            if not next_marker:
                break

        # 直播回放：逐页获取，按日期过滤（同理）
        replay_marker = None
        while True:
            result = self._client.get_author_replays(source_author_id, page_size=20, last_buff=replay_marker)
            if result.get("code") != 0:
                break

            replays = result.get("data", [])
            if not replays:
                break

            page_matched = 0
            page_all_before = True

            for obj in replays:
                video = self._parse_video(obj)
                if not video:
                    continue
                video["video_type"] = "live_replay"
                total_fetched += 1

                create_time = video.get("create_time", "")
                if create_time:
                    video_dt = self._parse_date(create_time)
                    if video_dt:
                        if before_dt <= video_dt <= today:
                            filtered.append(video)
                            replay_count += 1
                            page_matched += 1
                            page_all_before = False
                        elif video_dt < before_dt:
                            pass
                        else:
                            page_all_before = False
                    else:
                        page_all_before = False
                else:
                    page_all_before = False

            if on_progress:
                on_progress("fetching", total_fetched, None, f"回放翻页中", video_type="live_replay", short_video_count=short_video_count, replay_count=replay_count)

            # 整页无匹配且全部早于临界值 → 停止
            if page_matched == 0 and page_all_before:
                logger.info(f"[get_author_videos_before_date] 回放整页早于 {before_date}，停止翻页")
                break

            replay_marker = result.get("next_marker")
            if not replay_marker:
                break

        logger.info(f"[get_author_videos_before_date] 截止日期 {before_date}，拉取 {total_fetched} 个，符合条件 {len(filtered)} 个（短视频 {short_video_count}，回放 {replay_count}）")

        # 更新作者最新发布时间
        self._update_author_latest_publish_date(source_author_id, filtered)

        return {"code": 0, "data": filtered, "msg": ""}

    def get_author_videos_by_count(self, source_author_id: str, video_count: int) -> dict:
        """拉取指定数量的视频（从最新开始）

        Args:
            source_author_id: 作者ID
            video_count: 视频数量

        Returns:
            {"code": 0, "data": [...], "msg": ""} 或 {"code": -1, "msg": "错误信息"}
        """
        if not source_author_id:
            return {"code": -1, "msg": "作者ID不能为空"}

        if video_count < 0:
            return {"code": -1, "msg": "视频数量不能为负数"}

        if video_count == 0:
            return {"code": 0, "data": [], "msg": ""}

        # 拉取所有视频
        all_videos_result = self._get_all_videos(source_author_id)
        if all_videos_result.get("code") != 0:
            return all_videos_result

        all_videos = all_videos_result.get("data", [])

        # 按时间倒序排序
        all_videos.sort(key=lambda x: x.get("create_time", ""), reverse=True)

        # 取前 N 个
        result = all_videos[:video_count]

        logger.info(f"[get_author_videos_by_count] 请求 {video_count} 个，返回 {len(result)} 个视频")

        # 更新作者最新发布时间
        self._update_author_latest_publish_date(source_author_id, result)

        return {"code": 0, "data": result, "msg": ""}

    def add_author_only(
        self,
        keyword: str,
        source_author_id: str,
        avatar_url: str = ""
    ) -> dict:
        """只加入作者，不拉取视频

        记录当前时间戳作为基准，之后只拉取该时间戳之后的新视频

        Args:
            keyword: 作者名称
            source_author_id: 作者ID
            avatar_url: 头像URL

        Returns:
            {"code": 0, "data": {"author_id": "..."}, "msg": ""} 或 {"code": -1, "msg": "错误信息"}
        """
        from core.utils.database import Author

        if not keyword or not source_author_id:
            return {"code": -1, "msg": "作者信息不完整"}

        # 创建作者
        author_id = f"author_{int(datetime.now().timestamp() * 1000)}"
        now = datetime.now().isoformat()

        author = Author(
            id=author_id,
            source_author_id=source_author_id,
            name=keyword,
            tag=None,
            bio="",
            avatar_url=avatar_url,
            cover_img_url="",
            created_at=now,
            updated_at=now,
            latest_publish_date=now,  # 记录当前时间作为基准
        )

        if db.create_author(author):
            logger.info(f"[add_author_only] 创建作者成功: {keyword}, 基准时间: {now}")
            return {"code": 0, "data": {"author_id": author_id}, "msg": ""}
        else:
            logger.error(f"[add_author_only] 创建作者失败: {keyword}")
            return {"code": -1, "msg": "创建作者失败"}

    def _update_author_latest_publish_date(self, source_author_id: str, videos: list):
        """更新作者最新视频发布时间

        从视频列表中找到最大的 create_time，更新到作者的 latest_publish_date 字段

        Args:
            source_author_id: 作者ID
            videos: 视频列表
        """
        if not videos or not source_author_id:
            return

        # 找出最新视频的时间
        latest_time = ""
        for v in videos:
            create_time = v.get("create_time", "")
            if create_time and (not latest_time or create_time > latest_time):
                latest_time = create_time

        if not latest_time:
            return

        try:
            # 通过 source_author_id 查找作者
            author = db.get_author_by_source_id(source_author_id)
            if author:
                db.update_author_latest_publish_date(author.id, latest_time)
                logger.info(f"[_update_author_latest_publish_date] 更新作者 {author.name} 最新发布时间: {latest_time}")
            else:
                logger.debug(f"[_update_author_latest_publish_date] 作者尚未入库，跳过更新: {source_author_id[:30]}...")

        except Exception as e:
            logger.error(f"[_update_author_latest_publish_date] 更新失败: {e}")

    def _get_all_videos(self, source_author_id: str) -> dict:
        """拉取作者所有视频（短视频+直播回放）

        Args:
            source_author_id: 作者ID

        Returns:
            {"code": 0, "data": [...], "msg": ""}
        """
        all_videos = []
        next_marker = None

        # 短视频
        while True:
            result = self._client.get_author_videos(source_author_id, page_size=20, last_buff=next_marker)
            if result.get("code") != 0:
                break

            videos = result.get("data", [])
            if not videos:
                break

            for obj in videos:
                video = self._parse_video(obj)
                if video:
                    video.setdefault("video_type", "short_video")
                    all_videos.append(video)

            next_marker = result.get("next_marker")
            if not next_marker:
                break

        # 直播回放
        replay_marker = None
        while True:
            result = self._client.get_author_replays(source_author_id, page_size=20, last_buff=replay_marker)
            if result.get("code") != 0:
                break

            replays = result.get("data", [])
            if not replays:
                break

            for obj in replays:
                video = self._parse_video(obj)
                if video:
                    video["video_type"] = "live_replay"
                    all_videos.append(video)

            replay_marker = result.get("next_marker")
            if not replay_marker:
                break

        logger.info(f"[_get_all_videos] 短视频+直播回放共 {len(all_videos)} 个")
        return {"code": 0, "data": all_videos, "msg": ""}

    def _parse_date(self, date_value) -> Optional[datetime]:
        """解析日期

        Args:
            date_value: 时间戳(int) 或 日期字符串(str)

        Returns:
            datetime 对象或 None
        """
        if not date_value:
            return None

        if isinstance(date_value, (int, float)):
            return datetime.fromtimestamp(date_value)

        if isinstance(date_value, str):
            # 尝试 ISO 格式
            try:
                return datetime.fromisoformat(date_value.replace("Z", ""))
            except ValueError:
                pass

            # 尝试 YYYY-MM-DD 格式
            try:
                return datetime.strptime(date_value, "%Y-%m-%d")
            except ValueError:
                pass

        return None

    def _parse_author(self, item: dict) -> dict:
        """解析后端返回的作者信息

        Args:
            item: 后端返回的作者对象

        Returns:
            标准化的作者字典
        """
        contact = item.get("contact", {})
        return {
            "name": contact.get("nickname", ""),
            "source_author_id": contact.get("username", ""),
            "avatar_url": contact.get("headUrl", ""),
            "cover_img_url": contact.get("coverImgUrl", ""),
            "bio": contact.get("signature", ""),
        }

    def _parse_video(self, obj: dict) -> Optional[dict]:
        """解析后端返回的视频信息

        Args:
            obj: 后端返回的视频对象

        Returns:
            标准化的视频字典或 None（非视频类型返回 None）
        """
        video_id = obj.get("id", "")
        if not video_id:
            return None

        object_nonce_id = obj.get("objectNonceId", "")
        createtime = obj.get("createtime", 0)

        obj_desc = obj.get("objectDesc", {})
        title = obj_desc.get("description", "")

        media_list = obj_desc.get("media", [])
        if not media_list:
            return None

        media = media_list[0]
        # mediaType=9 是图片，不是视频，需要过滤
        # mediaType=4 是标准视频，mediaType=1 也可能是视频（直播回放中会出现）
        media_type = media.get("mediaType", 0)
        if media_type == 9:
            logger.info(f"[_parse_video] 跳过图片类型 mediaType=9, video_id={video_id}")
            return None
        url = media.get("url", "") + media.get("urlToken", "")
        original_file_size = media.get("fileSize", 0)
        cover_url = media.get("coverUrl", "")
        decode_key_str = media.get("decodeKey", "0")
        decode_key = int(decode_key_str) if decode_key_str else 0
        # 获取时长：优先选中规格的 durationMs，fallback spec[0]，再 fallback videoPlayLen
        duration_ms = 0
        spec_list = media.get("spec", [])
        if spec_list:
            duration_ms = spec_list[0].get("durationMs", 0)
        if not duration_ms:
            duration_ms = media.get("videoPlayLen", 0) * 1000

        # 原视频分辨率
        original_width = media.get("width", 0)
        original_height = media.get("height", 0)

        # 规格选择优先级：1080p → 720p → original → 720p以下压缩规格
        best_spec = "original"
        best_width = original_width
        best_height = original_height

        # 分辨率范围定义：1080档(1030-1130), 720档(680-770), 480档(450-510)
        RES_1080_RANGE = (1030, 1130)
        RES_720_RANGE = (680, 770)
        RES_480_RANGE = (450, 510)

        if spec_list:
            spec_1080 = None
            spec_720 = None
            spec_low = None

            for s in spec_list:
                spec_format = s.get("fileFormat", "")
                s_height = s.get("height", 0)

                if not spec_format or spec_format == "original":
                    continue

                if RES_1080_RANGE[0] <= s_height <= RES_1080_RANGE[1]:
                    if spec_1080 is None:
                        spec_1080 = s
                elif RES_720_RANGE[0] <= s_height <= RES_720_RANGE[1]:
                    if spec_720 is None:
                        spec_720 = s
                else:
                    if spec_low is None:
                        spec_low = s

            # 优先级：1080档 → 720档 → original(高于所有压缩规格) → 低档压缩
            selected = spec_1080 or spec_720
            if selected:
                best_spec = selected.get("fileFormat", "original")
                best_width = selected.get("width", original_width)
                best_height = selected.get("height", original_height)
            elif spec_low is None:
                # 没有任何压缩规格，用 original
                best_spec = "original"
                best_width = original_width
                best_height = original_height
            elif original_height > spec_low.get("height", 0):
                # original 分辨率比最高压缩规格还高，用 original
                best_spec = "original"
                best_width = original_width
                best_height = original_height
            else:
                # original 分辨率不比压缩规格高，选压缩规格
                best_spec = spec_low.get("fileFormat", "original")
                best_width = spec_low.get("width", original_width)
                best_height = spec_low.get("height", original_height)

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

        create_time = ""
        if createtime:
            create_time = datetime.fromtimestamp(createtime).isoformat()

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
