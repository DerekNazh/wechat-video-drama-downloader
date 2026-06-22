"""播放器 API 路由"""
import logging
from fastapi import APIRouter
from pydantic import BaseModel
from core.service.player import PlayerService
from core.utils.database import db

logger = logging.getLogger("api_player")

router = APIRouter(prefix="/api/player", tags=["player"])


class PlayVideoRequest(BaseModel):
    video_id: str = None
    file_path: str = None


@router.post("/play")
def play_video(request: PlayVideoRequest):
    """播放视频

    根据视频ID或文件路径播放视频
    """
    try:
        service = PlayerService()

        # 优先使用 video_id
        if request.video_id:
            video = db.get_author_video(request.video_id)
            if not video:
                return {"code": -1, "msg": "视频不存在"}
            if not video.is_downloaded or not video.download_path:
                return {"code": -1, "msg": "视频未下载"}
            result = service.play_video(video.download_path)
            return result

        # 使用 file_path
        if request.file_path:
            result = service.play_video(request.file_path)
            return result

        return {"code": -1, "msg": "请提供 video_id 或 file_path"}

    except Exception as e:
        logger.error(f"[play_video] 播放失败: {e}")
        return {"code": -1, "msg": str(e)}