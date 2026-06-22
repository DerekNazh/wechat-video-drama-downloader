"""播放器服务层

提供视频播放功能
"""

import logging
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger("player_service")


class PlayerService:
    """播放器服务

    提供视频播放功能
    """

    def play_video(self, file_path: str) -> dict:
        """播放视频

        Args:
            file_path: 视频文件路径（必须是绝对路径且为 .mp4 文件）

        Returns:
            {"code": 0, "msg": ""} 或 {"code": -1, "msg": "错误信息"}
        """
        # 校验1: 必须是绝对路径
        path = Path(file_path)
        if not path.is_absolute():
            logger.warning(f"[play_video] 必须使用绝对路径: {file_path}")
            return {"code": -1, "msg": "必须使用绝对路径"}

        # 校验2: 必须是 .mp4 文件
        if path.suffix.lower() != ".mp4":
            logger.warning(f"[play_video] 只支持 .mp4 文件: {file_path}")
            return {"code": -1, "msg": "只支持 .mp4 文件"}

        # 校验3: 文件必须存在
        if not path.exists():
            logger.warning(f"[play_video] 文件不存在: {file_path}")
            return {"code": -1, "msg": "文件不存在"}

        # 调用系统默认播放器播放
        try:
            if sys.platform == 'win32':
                subprocess.run(['start', '', str(path)], shell=True)
            elif sys.platform == 'darwin':
                subprocess.run(['open', str(path)])
            else:
                subprocess.run(['xdg-open', str(path)])

            logger.info(f"[play_video] 已发送播放命令: {path}")
            return {"code": 0, "msg": "已打开播放器"}

        except Exception as e:
            logger.error(f"[play_video] 播放失败: {e}")
            return {"code": -1, "msg": f"播放失败: {e}"}
