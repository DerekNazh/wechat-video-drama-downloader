"""微信视频号后端服务启动器

提供 wx_video_download.exe 的启动、检测功能
"""
import logging
import socket
import subprocess
import threading
import time
import os
import sys
from pathlib import Path

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

    def is_upstream_ready(self) -> bool:
        """检测上游 MITM 代理端口（res_download 转发目标 2023）是否在监听

        res_download 的 UpstreamProxy 指向 127.0.0.1:2023，微信流量经此拦截。
        该端口由 wx_video_download.exe 内部代理监听，2022 HTTP 就绪不代表 2023 已监听。
        """
        try:
            with socket.create_connection(("127.0.0.1", settings.res_upstream_port), timeout=1.0):
                return True
        except (ConnectionRefusedError, OSError):
            return False

    def _inject_download_dir(self) -> bool:
        """将 Python 侧下载目录注入 Go 的 config.yaml download.dir

        断点背景：config.yaml 是打包时静态复制的文件（download.dir: ../下载/作者资源），
        若用户在设置里改了下载目录，只更新 Python 侧 settings/.env，Go 仍按旧路径落盘，
        导致"文件下了但用户去新目录找不到"。因此每次启动 Go 前必须注入单一事实源：
        settings.wx_download_dir（相对 app_root 则绝对化）。
        """
        try:
            cfg_path = Path(self.exe_path).parent / "config.yaml"
            if not cfg_path.exists():
                logger.warning("[注入] config.yaml 不存在: %s", cfg_path)
                return False

            target = str(settings.wx_download_dir).replace(os.sep, "/")

            import yaml
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            current = (data.get("download") or {}).get("dir")
            if current == target:
                return True
            data.setdefault("download", {})["dir"] = target
            with open(cfg_path, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)
            logger.info("[注入] config.yaml download.dir → %s", target)
            return True
        except Exception as e:
            logger.error("[注入] 写入 config.yaml 失败: %s", e)
            return False

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

        # 启动前注入下载目录（单一事实源），否则 Go 按静态 config.yaml 旧路径落盘
        self._inject_download_dir()

        try:
            logger.info("[启动] 启动服务: %s", self.exe_path)
            self.process = subprocess.Popen(
                [self.exe_path],
                cwd=os.path.dirname(self.exe_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                creationflags=CREATE_NO_WINDOW,
            )
            self._start_time = time.time()
            self._pid = self.process.pid
            logger.info("[启动] Go 后端已派发 PID=%d", self._pid)

            # 把 Go exe 的 stdout 实时转发到 logger，便于诊断 cert 安装等关键输出
            threading.Thread(
                target=self._drain_go_stdout,
                args=(self.process.stdout,),
                daemon=True,
                name="goexe-stdout-drain",
            ).start()
            # 心跳: 5s/15s/30s 检查进程是否还活着
            threading.Thread(
                target=self._watch_go_process,
                daemon=True,
                name="goexe-watchdog",
            ).start()

            for i in range(wait_seconds):
                time.sleep(1)
                if self.is_running():
                    logger.info("[OK] 服务启动成功 (耗时 %d 秒)", i + 1)
                    break
            else:
                logger.error("[ERROR] 服务启动超时（%d 秒）", wait_seconds)
                return False

            # HTTP 2022 就绪后，进一步验证上游 MITM 代理 2023 已监听
            # （2022 就绪不代表 2023 已监听，res_download 转发链路可能仍断）
            if not self.is_upstream_ready():
                logger.warning("[WARN] HTTP API 已就绪，但上游代理端口 %d 未监听，微信拦截链路可能不可用",
                               settings.res_upstream_port)
            else:
                logger.info("[OK] 上游代理端口 %d 已监听，微信拦截链路就绪", settings.res_upstream_port)

            return True

        except Exception as e:
            logger.error("[ERROR] 启动失败: %s", e)
            return False

    def _drain_go_stdout(self, stream):
        """把 Go exe 的 stdout 实时逐行写到 logger。解码失败时回退 repr。"""
        try:
            for raw in iter(stream.readline, b""):
                try:
                    line = raw.decode("utf-8", errors="replace").rstrip()
                except Exception:
                    line = repr(raw)
                if line:
                    logger.info("[goexe] %s", line)
            stream.close()
        except Exception as e:
            logger.warning("[goexe] stdout drain 异常: %s: %s", type(e).__name__, e)

    def _watch_go_process(self):
        """心跳监控：5s/15s/30s 时检查 Go 后端进程是否还活着，秒退则报错。"""
        checkpoints = [5, 15, 30]
        start = self._start_time
        for cp in checkpoints:
            sleep_for = cp - (time.time() - start)
            if sleep_for > 0:
                time.sleep(sleep_for)
            if self.process is None:
                return
            ret = self.process.poll()
            if ret is not None:
                logger.error(
                    "[goexe-watchdog] Go 后端在启动后 %ds 内已退出 exit_code=%s —— "
                    "常见原因：MITM 根证书安装失败触发崩溃、未捕获异常",
                    int(time.time() - start), ret,
                )
                return
            logger.info("[goexe-watchdog] %ds 检查: Go 后端 PID=%d 仍在运行",
                        cp, self._pid)

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
                if self.process and self.process.poll() is not None:
                    logger.info("[停止] Go 后端已退出 exit_code=%s (等待 %d 秒)",
                                self.process.poll(), i + 1)
                    break
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