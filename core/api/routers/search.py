"""搜索 API 路由"""
import logging

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from core.service.search import SearchService
from core.utils.database import db
from core.utils.event_bus import emit
from core.api.deps import require_wechat

logger = logging.getLogger("api_search")

router = APIRouter(
    prefix="/api/search",
    tags=["search"],
    dependencies=[Depends(require_wechat)],
)


@router.get("/authors")
def search_authors(q: str = "", exact: bool = False):
    """搜索作者（代理 Go 后端）

    Args:
        q: 搜索关键词
        exact: True=严格匹配(单个结果)，False=模糊模式(列表)
    """
    if not q:
        return {"code": 0, "data": [], "msg": ""}
    try:
        service = SearchService()
        result = service.search_author(q, exact_match=exact)
        return result
    except Exception as e:
        logger.error(f"[search_authors] {e}")
        return {"code": -1, "data": [], "msg": str(e)}


class AddAuthorRequest(BaseModel):
    keyword: str
    pages: int = 1
    before_date: str = ""  # 截止日期 YYYY-MM-DD，同步该日期到今天之间的视频


class BatchAddRequest(BaseModel):
    keywords: list[str]
    pages: int = 1


@router.post("/author/add")
def add_author_with_videos(request: AddAuthorRequest):
    """作者名称强匹配并入库作者信息与视频"""
    try:
        service = SearchService()

        # 1. 搜索作者（强匹配）
        search_result = service.search_author(request.keyword)
        if search_result.get("code") != 0:
            return {"code": -1, "msg": search_result.get("msg", "搜索失败")}

        author_data = search_result.get("data")
        if not author_data:
            return {"code": -1, "msg": f"未找到精确匹配的作者: {request.keyword}"}

        # 2. 先入库作者（幂等：已存在则更新），再获取视频
        #    原因：get_author_videos 内部会调 _update_author_latest_publish_date
        #    需要作者已存在才能更新 latest_publish_date
        from core.utils.store import Author
        from datetime import datetime

        existing_author = db.get_author_by_source_id(author_data.get("source_author_id"))
        if existing_author:
            existing_author.name = author_data.get("name")
            existing_author.bio = author_data.get("bio", "")
            existing_author.avatar_url = author_data.get("avatar_url", "")
            existing_author.cover_img_url = author_data.get("cover_img_url", "")
            existing_author.updated_at = datetime.now().isoformat()
            db.update_author(existing_author)
            author_id = existing_author.id
        else:
            author_id = f"doc_author_{int(datetime.now().timestamp() * 1000)}"
            author = Author(
                id=author_id,
                source_author_id=author_data.get("source_author_id"),
                name=author_data.get("name"),
                tag=None,
                bio=author_data.get("bio", ""),
                avatar_url=author_data.get("avatar_url", ""),
                cover_img_url=author_data.get("cover_img_url", ""),
                created_at=datetime.now().isoformat(),
                updated_at=datetime.now().isoformat(),
            )
            if not db.create_author(author):
                return {"code": -1, "msg": "作者入库失败"}

        # 3. 获取视频（支持日期过滤）
        author_name = author_data.get("name", "")

        # 进度回调：将 Service 层的逐页进度转发为 SSE 事件
        def _on_fetch_progress(phase, current, total, message, **kwargs):
            event_data = {
                "phase": phase,
                "current": current,
                "total": total,
                "name": message,
                "author_name": author_name,
            }
            if "video_type" in kwargs:
                event_data["video_type"] = kwargs["video_type"]
            if "short_video_count" in kwargs:
                event_data["short_video_count"] = kwargs["short_video_count"]
            if "replay_count" in kwargs:
                event_data["replay_count"] = kwargs["replay_count"]
            logger.debug(f"[SSE进度] phase={phase}, video_type={kwargs.get('video_type','')}, sv={kwargs.get('short_video_count')}, rp={kwargs.get('replay_count')}, msg={message}")
            emit("video_fetch_progress", event_data)

        emit("video_fetch_progress", {
            "phase": "start",
            "current": 0,
            "total": 0,
            "name": "",
            "author_name": author_name,
        })

        if request.before_date:
            # 按日期范围获取：before_date 到今天
            videos_result = service.get_author_videos_before_date(
                author_data.get("source_author_id"),
                request.before_date,
                on_progress=_on_fetch_progress
            )
        else:
            # 按页数获取
            videos_result = service.get_author_videos(
                author_data.get("source_author_id"),
                pages=request.pages,
                on_progress=_on_fetch_progress
            )

        if videos_result.get("code") != 0:
            return {"code": -1, "msg": "获取视频失败"}

        videos = videos_result.get("data", [])

        # 4. 入库视频
        from core.utils.store import AuthorVideo

        added_count = 0
        added_sv_count = 0
        added_rp_count = 0
        for i, video in enumerate(videos):
            author_video = AuthorVideo(
                video_id=video.get('video_id', ''),
                author_id=author_id,
                title=video.get("title", ""),
                object_nonce_id=video.get("object_nonce_id", ""),
                url=video.get("url", ""),
                spec=video.get("spec", ""),
                file_size=video.get("file_size", 0),
                cover_url=video.get("cover_url", ""),
                decode_key=video.get("decode_key", 0),
                author_avatar=video.get("author_avatar", ""),
                duration=video.get("duration", 0),
                create_time=video.get("create_time", ""),
                is_downloaded=0,
                download_path="",
                downloaded_at=None,
                video_type=video.get("video_type", "short_video"),
            )
            is_new = db.create_author_video(author_video)
            if is_new:
                added_count += 1
                if video.get("video_type") == "live_replay":
                    added_rp_count += 1
                else:
                    added_sv_count += 1
            # 每个视频都发射进度（用迭代序号 i+1，确保连续递增）
            emit("video_fetch_progress", {
                "phase": "saving",
                "current": i + 1,
                "total": len(videos),
                "name": video.get("title", "")[:20],
                "author_name": author_name,
                "added": added_count,
                "short_video_count": added_sv_count,
                "replay_count": added_rp_count,
            })

        emit("video_fetch_progress", {
            "phase": "done",
            "current": added_count,
            "total": len(videos),
            "name": "",
            "author_name": author_name,
            "short_video_count": added_sv_count,
            "replay_count": added_rp_count,
        })

        # 添加 author_id 到每个视频
        videos_with_author = []
        for video in videos:
            video["author_id"] = author_id
            videos_with_author.append(video)

        return {
            "code": 0,
            "data": {
                "author": {
                    "id": author_id,
                    "name": author_data.get("name"),
                    "source_author_id": author_data.get("source_author_id"),
                },
                "videos": videos_with_author,
                "added": added_count,
            },
            "msg": ""
        }
    except Exception as e:
        return {"code": -1, "msg": str(e)}


@router.post("/author/batch-add")
def batch_add_authors_with_videos(request: BatchAddRequest):
    """批量作者名称强匹配并入库"""
    try:
        service = SearchService()

        success_count = 0
        fail_count = 0
        results = []

        for keyword in request.keywords:
            # 搜索作者
            search_result = service.search_author(keyword)
            if search_result.get("code") != 0 or not search_result.get("data"):
                fail_count += 1
                results.append({"keyword": keyword, "success": False})
                continue

            author_data = search_result.get("data")

            # 先入库作者，再获取视频（同 add_author_with_videos 的顺序修复）
            from core.utils.store import Author
            from datetime import datetime

            existing_author = db.get_author_by_source_id(author_data.get("source_author_id"))
            if existing_author:
                existing_author.name = author_data.get("name")
                existing_author.bio = author_data.get("bio", "")
                existing_author.avatar_url = author_data.get("avatar_url", "")
                existing_author.cover_img_url = author_data.get("cover_img_url", "")
                existing_author.updated_at = datetime.now().isoformat()
                db.update_author(existing_author)
                author_id = existing_author.id
            else:
                author_id = f"doc_author_{int(datetime.now().timestamp() * 1000)}"
                author = Author(
                    id=author_id,
                    source_author_id=author_data.get("source_author_id"),
                    name=author_data.get("name"),
                    tag=None,
                    bio=author_data.get("bio", ""),
                    avatar_url=author_data.get("avatar_url", ""),
                    cover_img_url=author_data.get("cover_img_url", ""),
                    created_at=datetime.now().isoformat(),
                    updated_at=datetime.now().isoformat(),
                )
                if not db.create_author(author):
                    fail_count += 1
                    results.append({"keyword": keyword, "success": False})
                    continue

            # 获取视频
            videos_result = service.get_author_videos(
                author_data.get("source_author_id"),
                pages=request.pages
            )

            if videos_result.get("code") != 0:
                fail_count += 1
                results.append({"keyword": keyword, "success": False})
                continue

            videos = videos_result.get("data", [])

            # 入库视频
            from core.utils.store import AuthorVideo

            for video in videos:
                author_video = AuthorVideo(
                    video_id=video.get('video_id', ''),
                    author_id=author_id,
                    title=video.get("title", ""),
                    object_nonce_id=video.get("object_nonce_id", ""),
                    url=video.get("url", ""),
                    spec=video.get("spec", ""),
                    file_size=video.get("file_size", 0),
                    cover_url=video.get("cover_url", ""),
                    decode_key=video.get("decode_key", 0),
                    author_avatar=video.get("author_avatar", ""),
                    duration=video.get("duration", 0),
                    create_time=video.get("create_time", ""),
                    is_downloaded=0,
                    download_path="",
                    downloaded_at=None,
                    video_type=video.get("video_type", "short_video"),
                )
                db.create_author_video(author_video)

            success_count += 1
            results.append({"keyword": keyword, "success": True, "videos": len(videos)})

        return {
            "code": 0,
            "data": {
                "success_count": success_count,
                "fail_count": fail_count,
                "results": results,
            },
            "msg": ""
        }
    except Exception as e:
        return {"code": -1, "msg": str(e)}