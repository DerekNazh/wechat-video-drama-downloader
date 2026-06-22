"""微信视频号后端服务启动器

提供 wx_video_download.exe 的启动、检测功能
"""
import logging
import socket
import subprocess
import time
import os
import sys

from config.settings import settings

logger = logging.getLogger("base_service")

if sys.platform == "win32":
    CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW
else:
    CREATE_NO_WINDOW = 0

GO_PORT = 2022


class WechatVideoService:
    """微信视频号后端服务管理器"""

    def __init__(self):
        self.process = None
        self.exe_path = str(settings.wx_exe_path)
        self.service_url = "http://127.0.0.1:2022"

    def is_running(self) -> bool:
        """检测服务是否已启动（HTTP 探测）"""
        try:
            import requests
            resp = requests.get(f"{self.service_url}/api/status", timeout=2)
            return resp.json().get("code") == 0
        except Exception:
            return False

    def is_process_running(self) -> bool:
        """检测 Go 进程是否存在"""
        try:
            result = subprocess.run(
                ["tasklist"],
                capture_output=True,
                text=True,
                creationflags=CREATE_NO_WINDOW,
            )
            return "wx_video_download.exe" in result.stdout
        except Exception:
            return False

    def is_port_free(self) -> bool:
        """检测端口 2022 是否未被占用"""
        try:
            with socket.create_connection(("127.0.0.1", GO_PORT), timeout=0.5):
                return False
        except (ConnectionRefusedError, OSError):
            return True

    def start(self, wait_seconds: int = 5) -> bool:
        """启动服务"""
        if self.is_running():
            logger.info("[OK] 服务已在运行")
            return True

        # 端口被占用但 HTTP 不响应 = 旧进程正在关闭，等待端口释放
        if not self.is_port_free():
            logger.info("[启动] 端口 2022 被占用，等待释放...")
            for i in range(10):
                time.sleep(1)
                if self.is_port_free():
                    logger.info("[启动] 端口 2022 已释放 (等待 %d 秒)", i + 1)
                    break
                if i == 9:
                    logger.warning("[启动] 端口 2022 仍未释放，强制终止残留进程")
                    self.stop()

        if not os.path.exists(self.exe_path):
            logger.error("[ERROR] exe 文件不存在: %s", self.exe_path)
            return False

        try:
            logger.info("[启动] 启动服务: %s", self.exe_path)
            self.process = subprocess.Popen(
                [self.exe_path],
                cwd=os.path.dirname(self.exe_path),
                creationflags=CREATE_NO_WINDOW,
            )

            for i in range(wait_seconds):
                time.sleep(1)
                if self.is_running():
                    logger.info("[OK] 服务启动成功 (耗时 %d 秒)", i + 1)
                    return True

            logger.warning("[WARN] 服务启动超时，但进程可能已启动")
            return True

        except Exception as e:
            logger.error("[ERROR] 启动失败: %s", e)
            return False

    def stop(self, wait_timeout: int = 10) -> bool:
        """停止服务，等待进程真正退出和端口释放"""
        if not self.is_process_running():
            logger.info("[OK] 服务未在运行")
            return True

        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", "wx_video_download.exe"],
                capture_output=True,
                creationflags=CREATE_NO_WINDOW,
            )
            logger.info("[停止] 已发送 taskkill，等待进程退出...")

            # 等待进程真正退出
            for i in range(wait_timeout):
                time.sleep(1)
                if not self.is_process_running():
                    logger.info("[OK] 进程已退出 (等待 %d 秒)", i + 1)
                    break
                if i == wait_timeout - 1:
                    logger.warning("[停止] 进程 %d 秒后仍未退出", wait_timeout)

            # 等待端口释放（进程退出后端口仍有短暂占用）
            for i in range(5):
                time.sleep(1)
                if self.is_port_free():
                    logger.info("[OK] 端口 2022 已释放")
                    return True

            logger.warning("[停止] 端口 2022 未释放，可能残留连接")
            return True

        except Exception as e:
            logger.error("[ERROR] 停止失败: %s", e)
            return False

    def restart(self) -> bool:
        """重启服务（确保旧进程完全退出后再启动）"""
        self.stop()
        return self.start()