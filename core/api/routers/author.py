"""作者 API 路由"""
import logging

from fastapi import APIRouter

from core.utils.database import db

logger = logging.getLogger("api_author")

router = APIRouter(prefix="/api/author", tags=["author"])


@router.get("/list")
def list_authors():
    """获取所有作者列表，包含按类型统计的视频数"""
    try:
        authors = db.list_authors()

        data = []
        for author in authors:
            type_stats = db.get_author_video_type_stats(author.id)

            data.append({
                "id": author.id,
                "source_author_id": author.source_author_id,
                "name": author.name,
                "tag": author.tag,
                "bio": author.bio,
                "avatar_url": author.avatar_url,
                "cover_img_url": author.cover_img_url,
                "created_at": author.created_at,
                "updated_at": author.updated_at,
                "latest_publish_date": author.latest_publish_date,
                "short_video_count": type_stats["short_video_count"],
                "replay_count": type_stats["replay_count"],
                "short_video_downloaded": type_stats["short_video_downloaded"],
                "replay_downloaded": type_stats["replay_downloaded"],
            })

        return {"code": 0, "data": data, "msg": ""}
    except Exception as e:
        logger.error(f"[list_authors] 获取失败: {e}")
        return {"code": -1, "msg": str(e)}
