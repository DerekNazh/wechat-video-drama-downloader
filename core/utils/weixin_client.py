"""微信视频号后端服务 Client"""
import json
import logging
import re
import threading
import websocket
import requests
from datetime import datetime
from typing import Optional, Callable

from core.utils.socket_client import DownloadProgressListener

logger = logging.getLogger("weixin_monitor")

# 连通性探测的上一次结果。require_wechat 依赖会在每个受保护请求上执行探测，
# 仅在状态发生变化时写日志，避免正常运行时刷屏。
_last_service_state = {"code": None, "available": None}
_last_wechat_state = {"code": None}


def build_video_filename(title: str, create_time: Optional[str], spec: str, video_id: str = "") -> str:
    """构造视频文件名

    Args:
        title: 视频标题
        create_time: 视频发布时间（ISO 格式），None 或无效时不加日期前缀
        spec: 视频规格
        video_id: 视频 ID（用于同日期同标题视频消歧）

    Returns:
        文件名，格式：日期_标题_规格[_video_id].mp4
    """
    safe_title = re.sub(r'[<>:"/\\|?*\n\r\t]', '_', title)[:80] if title else ""

    date_str = ""
    if create_time:
        try:
            dt = datetime.fromisoformat(create_time)
            date_str = dt.strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            pass

    if date_str and safe_title:
        safe_title = re.sub(r'^20\d{2}[\s　\-_.]*', '', safe_title)
        safe_title = safe_title.lstrip('-_')

    parts = []
    if date_str:
        parts.append(date_str)
    if safe_title:
        parts.append(safe_title)
    if spec:
        parts.append(spec)
    if video_id:
        parts.append(video_id)
    file_part = "_".join(parts) if parts else "unknown"

    return f"{file_part}.mp4"


class WechatVideoAPIClient:
    """微信视频号后端服务 Client"""

    def __init__(self, base_url: str = "http://127.0.0.1:2022", timeout: int = 30):
        self.base_url = base_url
        self.timeout = timeout

    def check_service(self) -> bool:
        """检测后端服务是否启动

        Returns:
            是否启动
        """
        try:
            resp = requests.get(
                f"{self.base_url}/api/status",
                timeout=self.timeout
            )
            data = resp.json()
        except (requests.RequestException, ValueError) as e:
            logger.warning(
                "[check_service] %s 不可达: %s: %s",
                self.base_url, type(e).__name__, e
            )
            return False

        code = data.get("code")
        available = data.get("data", {}).get("channels", {}).get("available")

        # 该依赖在每个受保护请求上都会执行，仅在状态变化时记录以免刷屏。
        # channels.available 反映根证书安装状态：为 false 时视频号解密链路不可用，
        # 但它不参与在线判定，若不显式记录，证书故障在日志中完全不可见。
        if (code, available) != (_last_service_state["code"], _last_service_state["available"]):
            _last_service_state["code"] = code
            _last_service_state["available"] = available
            logger.info(
                "[check_service] code=%s channels.available=%s version=%s",
                code, available, data.get("data", {}).get("version")
            )
            if available is False:
                # 接口文档标注 /api/status「go源码有bug 暂不可用」；实测在三张根证书
                # 齐全、contact/search 能返回真实数据的机器上该字段依然为 false，
                # 说明它不反映真实证书状态，不能作为故障判据，仅留档参考。
                # 真实判据见 env_probe 启动时的根证书检查。
                logger.warning(
                    "[check_service] channels.available=false（该字段已知不可靠，"
                    "请以启动日志 [环境] 段的根证书检查结果为准）"
                )

        return code == 0

    def clear_all_tasks(self) -> bool:
        """清空所有任务记录（取消所有任务，包括正在下载的）

        Returns:
            是否成功
        """
        try:
            resp = requests.post(
                f"{self.base_url}/api/task/clear",
                timeout=self.timeout
            )
            data = resp.json()
            return data.get("code") == 0
        except Exception as e:
            logger.error(f"[clear_all_tasks] 异常: {e}")
            return False

    def cancel_task(self, task_id: str) -> bool:
        """取消单个任务

        Args:
            task_id: 任务 ID

        Returns:
            是否成功
        """
        try:
            resp = requests.post(
                f"{self.base_url}/api/task/delete",
                json={"id": task_id},
                timeout=self.timeout
            )
            data = resp.json()
            return data.get("code") == 0
        except Exception as e:
            logger.error(f"[cancel_task] 异常: {e}")
            return False

    def download_video(self, video_id: str, url: str, title: str,
                       spec: str, key: int, author_name: str = "",
                       create_time: str = "", video_type: str = "short_video") -> dict:
        """下载视频（创建任务）

        Args:
            video_id: 视频 ID
            url: 视频直链
            title: 标题
            spec: 视频规格
            key: 解密密钥
            author_name: 作者名称（用于创建子目录）
            create_time: 视频发布时间（ISO 格式，用于文件名日期）
            video_type: 视频类型 "short_video" 或 "live_replay"（用于按类型建子目录）

        Returns:
            {"code": 0, "data": {"id": "task_id"}, "msg": ""}
        """
        filename = build_video_filename(title, create_time, spec, video_id=video_id)
        safe_author = re.sub(r'[<>:"/\\|?*\n\r\t]', '_', author_name)[:50] if author_name else ""

        type_folder_map = {"short_video": "短视频", "live_replay": "直播回放"}
        type_folder = type_folder_map.get(video_type, "短视频")

        dir_parts = []
        if safe_author:
            dir_parts.append(safe_author)
        dir_parts.append(type_folder)
        dir_path = "/".join(dir_parts)

        logger.info(f"[download_video] video_id={video_id}, video_type={video_type}, "
                    f"type_folder={type_folder}, author={safe_author}, "
                    f"dir={dir_path}, filename={filename}")

        try:
            resp = requests.post(
                f"{self.base_url}/api/task/create2",
                json={
                    "url": url,
                    "filename": filename,
                    "dir": dir_path,
                    "extra": {
                        "id": video_id,
                        "title": title,
                        "key": str(key),
                        "spec": spec,
                        "suffix": ".mp4",
                    },
                },
                timeout=self.timeout
            )
            return resp.json()
        except Exception as e:
            logger.error(f"[download_video] 异常: {e}")
            return {"code": -1, "msg": str(e)}

    def list_download_tasks(self) -> list:
        """获取所有下载任务列表

        Returns:
            任务列表，每个任务包含 id, status, progress 等
        """
        try:
            resp = requests.get(
                f"{self.base_url}/api/task/list",
                timeout=self.timeout
            )
            data = resp.json()
            if data.get("code") == 0:
                return data.get("data", {}).get("list", [])
            return []
        except Exception as e:
            logger.error(f"[list_download_tasks] 异常: {e}")
            return []

    def get_download_task(self, task_id: str) -> Optional[dict]:
        """获取任务状态

        Args:
            task_id: 任务 ID

        Returns:
            任务信息，包含 status, progress, save_path 等
        """
        try:
            # 使用 list_download_tasks 获取任务列表，再通过 task_id 查找
            tasks = self.list_download_tasks()
            for task in tasks:
                if task.get("id") == task_id:
                    return task
            return None
        except Exception as e:
            logger.error(f"[get_download_task] 异常: {e}")
            return None

    def search_authors(self, keyword: str, next_marker: str = None) -> dict:
        """搜索作者

        Args:
            keyword: 搜索关键词
            next_marker: 分页游标（对应返回的 lastBuff）

        Returns:
            {"authors": [...], "next_marker": str or None}
        """
        try:
            params = {"keyword": keyword}
            if next_marker:
                params["next_marker"] = next_marker
            resp = requests.get(
                f"{self.base_url}/api/channels/contact/search",
                params=params,
                timeout=self.timeout
            )
            data = resp.json()
            if data.get("code") == 0:
                # 实际返回：data.data.infoList, data.data.lastBuff（嵌套结构）
                inner_data = data.get("data", {}).get("data", {})
                return {
                    "authors": inner_data.get("infoList", []),
                    "next_marker": inner_data.get("lastBuff"),
                }
            logger.warning(f"[search_authors] 失败: {data.get('msg')}")
            return {"authors": [], "next_marker": None}
        except Exception as e:
            logger.error(f"[search_authors] 异常: {e}")
            return {"authors": [], "next_marker": None}

    def listen_download_progress(self, on_progress: Callable[[dict], None]) -> DownloadProgressListener:
        """监听下载进度（实时推送）

        Args:
            on_progress: 回调函数，接收任务进度 dict

        Returns:
            监听器实例，调用 stop() 停止
        """
        listener = DownloadProgressListener()
        listener.start(on_progress)
        return listener

    def check_wechat_connected(self) -> bool:
        """检测微信视频号客户端是否连接

        通过搜索关键词来判断是否已连接（code==0 表示已连接）

        Returns:
            是否已连接
        """
        try:
            resp = requests.get(
                f"{self.base_url}/api/channels/contact/search",
                params={"keyword": "测"},
                timeout=self.timeout
            )
            data = resp.json()
        except (requests.RequestException, ValueError) as e:
            logger.warning(
                "[check_wechat_connected] 探测请求失败: %s: %s",
                type(e).__name__, e
            )
            return False

        code = data.get("code")
        if code != _last_wechat_state["code"]:
            _last_wechat_state["code"] = code
            if code == 0:
                logger.info("[check_wechat_connected] 微信已连接")
            else:
                # 实测：根证书齐全的机器上，若尚未在微信中打开过视频号页面，
                # 此处同样返回 code=400「请先初始化客户端 socket 连接」。
                # 故不能由本项失败反推证书故障，两种成因需结合 [环境] 段判断。
                logger.error(
                    "[check_wechat_connected] 微信未连接 code=%s msg=%s —— "
                    "成因一：尚未在微信中打开过视频号页面，注入脚本未回连后端；"
                    "成因二：根证书未生效导致视频号页面白屏，注入无法完成。"
                    "区分方法见启动日志 [环境] 段的根证书检查",
                    code, data.get("msg")
                )

        return code == 0

    def search_authors_by_keyword(self, keyword: str, next_marker: str = None) -> dict:
        """搜索作者（返回标准结构）

        Args:
            keyword: 搜索关键词
            next_marker: 分页游标

        Returns:
            {"code": 0, "data": {"authors": [...], "next_marker": "..."}, "msg": ""}
        """
        try:
            params = {"keyword": keyword}
            if next_marker:
                params["next_marker"] = next_marker
            resp = requests.get(
                f"{self.base_url}/api/channels/contact/search",
                params=params,
                timeout=self.timeout
            )
            data = resp.json()
            if data.get("code") == 0:
                inner_data = data.get("data", {}).get("data", {})
                return {
                    "code": 0,
                    "data": {
                        "authors": inner_data.get("infoList", []),
                        "next_marker": inner_data.get("lastBuff"),
                    },
                    "msg": ""
                }
            return {"code": -1, "data": {"authors": [], "next_marker": None}, "msg": data.get("msg", "")}
        except Exception as e:
            logger.error(f"[search_authors_by_keyword] 异常: {e}")
            return {"code": -1, "data": {"authors": [], "next_marker": None}, "msg": str(e)}

    def get_author_videos(self, username: str, page_size: int = 20, last_buff: str = None) -> dict:
        """获取作者普通视频列表

        Args:
            username: 作者 username
            page_size: 每页数量
            last_buff: 分页游标

        Returns:
            {"code": 0, "data": [...], "last_buff": "...", "msg": ""}
        """
        try:
            params = {"username": username, "page_size": page_size}
            if last_buff:
                params["next_marker"] = last_buff
            resp = requests.get(
                f"{self.base_url}/api/channels/contact/feed/list",
                params=params,
                timeout=self.timeout
            )
            data = resp.json()
            if data.get("code") == 0:
                inner_data = data.get("data", {}).get("data", {})
                videos = inner_data.get("object", [])
                return {
                    "code": 0,
                    "data": videos,
                    "next_marker": inner_data.get("lastBuffer"),
                    "msg": ""
                }
            return {"code": -1, "data": [], "next_marker": None, "msg": data.get("msg", "")}
        except Exception as e:
            logger.error(f"[get_author_videos] 异常: {e}")
            return {"code": -1, "data": [], "next_marker": None, "msg": str(e)}

    def get_author_replays(self, username: str, page_size: int = 20, last_buff: str = None) -> dict:
        """获取作者直播回放列表

        Args:
            username: 作者 username
            page_size: 每页数量
            last_buff: 分页游标

        Returns:
            {"code": 0, "data": [...], "msg": ""}
        """
        try:
            params = {"username": username, "page_size": page_size}
            if last_buff:
                params["next_marker"] = last_buff
            resp = requests.get(
                f"{self.base_url}/api/channels/live/replay/list",
                params=params,
                timeout=self.timeout
            )
            data = resp.json()
            if data.get("code") == 0:
                inner_data = data.get("data", {}).get("data", {})
                replays = inner_data.get("object", [])
                return {
                    "code": 0,
                    "data": replays,
                    "next_marker": inner_data.get("lastBuffer"),
                    "msg": ""
                }
            return {"code": -1, "data": [], "next_marker": None, "msg": data.get("msg", "")}
        except Exception as e:
            logger.error(f"[get_author_replays] 异常: {e}")
            return {"code": -1, "data": [], "next_marker": None, "msg": str(e)}