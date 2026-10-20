"""短剧嗅探后端服务启动器

提供 res_download.exe 的启动、检测、配置注入、代理管理功能
"""
import json
import logging
import socket
import subprocess
import time
import os
import sys

import requests

from config.settings import settings

logger = logging.getLogger("res_download_service")

if sys.platform == "win32":
    CREATE_NO_WINDOW = subprocess.CREATE_NO_WINDOW
else:
    CREATE_NO_WINDOW = 0


class ResDownloadService:
    """短剧嗅探后端服务管理器（res_download.exe）

    职责：
    1. 进程管理：启动/停止 res_download.exe
    2. 状态检测：HTTP 探测 /api/app-info
    3. 配置注入：设置 UpstreamProxy、SaveDirectory、OpenProxy
    4. 代理管理：开启/关闭系统代理
    5. 端口清理：启动前杀掉占用 8899 的残留进程
    """

    PROCESS_NAME = "res_download.exe"

    def __init__(self):
        self.process = None
        self.exe_path = str(settings.res_exe_path)
        self.work_dir = str(settings.res_work_dir)
        self.service_url = settings.res_api_url
        self.port = settings.res_port
        self.upstream_port = settings.res_upstream_port

    def is_running(self) -> bool:
        """检测服务是否已启动（HTTP 探测 /api/app-info）"""
        try:
            resp = requests.get(f"{self.service_url}/api/app-info", timeout=2)
            return resp.status_code == 200
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
            return self.PROCESS_NAME in result.stdout
        except Exception:
            return False

    def is_port_free(self) -> bool:
        """检测端口是否未被占用"""
        try:
            with socket.create_connection(("127.0.0.1", self.port), timeout=0.5):
                return False
        except (ConnectionRefusedError, OSError):
            return True

    def _port_listening(self, port: int) -> bool:
        """端口是否在监听（True=有服务存活，False=死端口）"""
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.5):
                return True
        except (ConnectionRefusedError, OSError):
            return False

    def kill_port(self) -> bool:
        """强制杀掉占用指定端口的进程（Windows netstat + taskkill）

        逻辑来自 pac 版本 prepar.go 的 killPort()
        """
        try:
            cmd = subprocess.run(
                ["cmd", "/c", f"netstat -ano | findstr :{self.port} | findstr LISTENING"],
                capture_output=True,
                text=True,
                creationflags=CREATE_NO_WINDOW,
            )
            output = cmd.stdout.strip()
            if not output:
                logger.info("[端口] %d 未被占用", self.port)
                return True

            for line in output.splitlines():
                fields = line.strip().split()
                if len(fields) < 5:
                    continue
                pid = int(fields[-1])
                if pid <= 4:
                    continue
                logger.info("[端口] 端口 %d 被进程 %d 占用，强制终止", self.port, pid)
                subprocess.run(
                    ["taskkill", "/T", "/F", "/PID", str(pid)],
                    capture_output=True,
                    creationflags=CREATE_NO_WINDOW,
                )

            # 等待端口释放
            for i in range(10):
                time.sleep(0.5)
                if self.is_port_free():
                    logger.info("[端口] 端口 %d 已释放 (等待 %d 秒)", self.port, (i + 1) * 0.5)
                    return True

            logger.warning("[端口] 端口 %d 未在5秒内释放", self.port)
            return False

        except Exception as e:
            logger.error("[端口] 端口清理失败: %s", e)
            return False

    def start(self, wait_seconds: int = 30) -> bool:
        """启动服务（含端口清理、健康等待、配置注入）

        启动序列：
        1. 端口清理
        2. 启动进程
        3. 等待 HTTP 就绪
        4. 注入配置（UpstreamProxy、SaveDirectory）
        """
        if self.is_running():
            logger.info("[OK] res_download 服务已在运行")
            return True

        # 端口被占用但 HTTP 不响应 = 旧进程残留
        if not self.is_port_free():
            logger.info("[启动] 端口 %d 被占用，清理残留进程...", self.port)
            self.kill_port()

        if not os.path.exists(self.exe_path):
            logger.error("[ERROR] exe 文件不存在: %s", self.exe_path)
            return False

        try:
            logger.info("[启动] 启动 res_download: %s", self.exe_path)
            self.process = subprocess.Popen(
                [self.exe_path],
                cwd=self.work_dir,
                creationflags=CREATE_NO_WINDOW,
            )

            # 等待 HTTP 就绪
            ready = False
            for i in range(wait_seconds):
                time.sleep(1)
                if self.is_running():
                    logger.info("[OK] res_download 启动成功 (耗时 %d 秒)", i + 1)
                    ready = True
                    break

            if not ready:
                logger.error("[ERROR] res_download 启动超时（%d 秒），短剧嗅探不可用", wait_seconds)
                return False

            # 配置注入（内部自带重试+回读校验），失败则明确返回失败
            if not self._inject_config():
                logger.error("[ERROR] res_download 配置注入失败，短剧嗅探链路不可用")
                return False

            return True

        except Exception as e:
            logger.error("[ERROR] 启动失败: %s", e)
            return False

    def ensure_configured(self) -> bool:
        """确保配置已正确注入（含重试 + 回读校验）

        供外部在开启系统代理前调用：注入未就绪时不应开启代理，
        否则流量进入 8899 但转发链路（UpstreamProxy→2023）是断的。
        """
        return self._inject_config()

    def _inject_config(self, max_retries: int = 3) -> bool:
        """注入配置：UpstreamProxy、SaveDirectory（带重试 + 回读校验）

        逻辑来自 pac 版本 prepar.go 的 ensureUpstreamProxy()
        重试策略：注入失败或回读校验不一致时重试，最多 max_retries 次。
        """
        upstream = f"http://127.0.0.1:{self.upstream_port}"
        save_dir = str(settings.short_drama_download_dir)

        for attempt in range(1, max_retries + 1):
            try:
                # GET 当前配置
                resp = requests.get(f"{self.service_url}/api/get-config", timeout=5)
                if resp.status_code != 200:
                    logger.warning("[配置] 第 %d 次获取 res_download 配置失败: HTTP %d", attempt, resp.status_code)
                    time.sleep(2)
                    continue

                result = resp.json()
                data = result.get("data", {})
                if not isinstance(data, dict):
                    logger.warning("[配置] 第 %d 次 res_download 配置 data 字段格式异常", attempt)
                    time.sleep(2)
                    continue

                # 嗅探类型每次都要设置（Type 走独立接口 /api/set-type，不在 get-config 里）
                self._set_type_video()

                # 检查是否已配置
                if (data.get("UpstreamProxy") == upstream
                        and data.get("SaveDirectory") == save_dir):
                    logger.info("[配置] res_download 配置已正确，无需修改")
                    return True

                # 设置目标字段
                data["UpstreamProxy"] = upstream
                data["OpenProxy"] = True
                data["AutoProxy"] = False
                data["SaveDirectory"] = save_dir

                # POST 回写
                set_resp = requests.post(
                    f"{self.service_url}/api/set-config",
                    json=data,
                    timeout=5,
                )
                if set_resp.status_code != 200:
                    logger.warning("[配置] 第 %d 次设置 res_download 配置失败: HTTP %d", attempt, set_resp.status_code)
                    time.sleep(2)
                    continue

                # 回读校验：确认 UpstreamProxy / SaveDirectory / OpenProxy 真正生效
                verify_resp = requests.get(f"{self.service_url}/api/get-config", timeout=5)
                if verify_resp.status_code != 200:
                    logger.warning("[配置] 第 %d 次回读校验失败: HTTP %d", attempt, verify_resp.status_code)
                    time.sleep(2)
                    continue

                verified = verify_resp.json().get("data", {})
                if (isinstance(verified, dict)
                        and verified.get("UpstreamProxy") == upstream
                        and verified.get("SaveDirectory") == save_dir
                        and verified.get("OpenProxy") is True):
                    logger.info("[配置] res_download 配置注入完成并已回读确认: UpstreamProxy=%s, SaveDirectory=%s", upstream, save_dir)
                    return True

                logger.warning("[配置] 第 %d 次注入后回读校验不一致（期望 UpstreamProxy=%s），重试", attempt, upstream)
                time.sleep(2)

            except Exception as e:
                logger.warning("[配置] 第 %d 次注入配置失败: %s", attempt, e)
                time.sleep(2)

        logger.error("[配置] 注入失败（已重试 %d 次），短剧嗅探链路不可用", max_retries)
        return False

    def _set_type_video(self) -> None:
        """设置嗅探类型为仅视频（调 /api/set-type）"""
        try:
            resp = requests.post(
                f"{self.service_url}/api/set-type",
                json={"type": "video"},
                timeout=5,
            )
            if resp.status_code == 200:
                logger.info("[配置] 嗅探类型已设为仅视频")
            else:
                logger.warning("[配置] 设置嗅探类型失败: HTTP %d", resp.status_code)
        except Exception as e:
            logger.warning("[配置] 设置嗅探类型失败: %s", e)

    def open_proxy(self) -> bool:
        """开启系统代理（调 res_download /api/proxy-open，失败回退注册表）

        HTTP 非 200 也视为失败（黑盒异常时不应假成功，否则系统代理没开
        却对外报告已开）。
        """
        try:
            resp = requests.get(f"{self.service_url}/api/proxy-open", timeout=5)
            resp.close()
            if resp.status_code == 200:
                logger.info("[代理] 系统代理已开启")
                return True
            logger.warning("[代理] 开启系统代理返回 HTTP %d，回退注册表", resp.status_code)
            return self._set_proxy_registry()
        except Exception as e:
            logger.warning("[代理] API 开启系统代理失败: %s，回退注册表", e)
            return self._set_proxy_registry()

    def _set_proxy_registry(self) -> bool:
        """直接修改注册表开启系统代理（指向本机 res_download 端口）"""
        try:
            import winreg
            proxy_server = f"127.0.0.1:{self.port}"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Internet Settings", 0, winreg.KEY_WRITE) as key:
                winreg.SetValueEx(key, "ProxyServer", 0, winreg.REG_SZ, proxy_server)
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 1)
            logger.info("[代理] 已通过注册表开启系统代理: %s", proxy_server)
            return True
        except Exception as e:
            logger.error("[代理] 注册表开启系统代理失败: %s", e)
            return False

    def recover_stale_proxy(self) -> dict:
        """自愈：检测系统代理残留（指向本应用端口但服务已死），自动清理

        场景：应用被强杀/崩溃时优雅退出未执行，注册表 ProxyEnable=1 且
        ProxyServer 指向 res_download 端口，但进程已不在 → 全网流量走死代理。
        此时读取注册表修复，避免用户"什么都加载不了"。

        Returns:
            {"changed": bool, "reason": str}
        """
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Internet Settings", 0, winreg.KEY_READ) as key:
                proxy_enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
                proxy_server, _ = winreg.QueryValueEx(key, "ProxyServer")
        except FileNotFoundError:
            return {"changed": False, "reason": "系统代理未启用（ProxyEnable 键不存在）"}
        except Exception as e:
            logger.warning("[代理] 读取系统代理注册表失败: %s", e)
            return {"changed": False, "reason": f"读取注册表失败: {e}"}

        if not proxy_enable:
            return {"changed": False, "reason": "系统代理未启用"}

        # 只处理本产品端口：res_download(8899) / Go MITM 上游(2023)
        # （Go 黑盒可能自写 2023 到系统代理——它被杀死后也是残留，必须能清）
        own_ports = {self.port, self.upstream_port}
        try:
            port = int(proxy_server.rsplit(":", 1)[-1])
        except (ValueError, IndexError):
            return {"changed": False, "reason": f"系统代理指向无法解析 {proxy_server}，跳过"}
        if port not in own_ports:
            return {"changed": False, "reason": f"系统代理指向其他代理 {proxy_server}，跳过"}

        # 端口未监听 = 对应服务已死 = 残留（比 is_running 更普适，2023 无 HTTP API 可探测）
        if self._port_listening(port):
            return {"changed": False, "reason": f"系统代理指向本产品端口 {port} 且服务存活，正常"}

        logger.warning("[代理] 检测到残留系统代理（指向 %s 但端口 %d 未监听），自动清理", proxy_server, port)
        success = self._unset_proxy_registry()
        return {"changed": success, "reason": "残留系统代理已清理" if success else "残留代理清理失败"}

    def unset_proxy(self) -> bool:
        """关闭系统代理：调 API + 注册表复核兜底

        API 分支仅作"通知黑盒"：黑盒 /api/proxy-unset 返回 200 但实际没改
        注册表的"假成功"会让用户残留系统代理、打不开网站（2026-10-21 修复）。
        因此无论 API 结果如何，注册表层必须确认关闭（_unset_proxy_registry 幂等）。
        """
        if self.is_process_running():
            try:
                resp = requests.get(f"{self.service_url}/api/proxy-unset", timeout=5)
                resp.close()
                logger.info("[代理] 已请求 API 关闭系统代理（HTTP %s），注册表复核兜底", resp.status_code)
            except Exception as e:
                logger.warning("[代理] API 关闭失败，回退注册表: %s", e)

        # 进程不在 / API 成功与否，一律注册表兜底
        return self._unset_proxy_registry()

    def _unset_proxy_registry(self) -> bool:
        """直接修改注册表关闭系统代理（res_download 进程不在时的回退方案）"""
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Internet Settings", 0, winreg.KEY_WRITE) as key:
                current, _ = winreg.QueryValueEx(key, "ProxyEnable")
                if current == 0:
                    logger.info("[代理] ProxyEnable 已为 0，无需修改")
                    return True
                winreg.SetValueEx(key, "ProxyEnable", 0, winreg.REG_DWORD, 0)
                logger.info("[代理] 已通过注册表关闭系统代理")
            return True
        except Exception as e:
            logger.error("[代理] 注册表清理失败: %s", e)
            return False

    def stop(self, wait_timeout: int = 10) -> bool:
        """停止服务，等待进程真正退出和端口释放"""
        if not self.is_process_running():
            logger.info("[OK] res_download 未在运行")
            return True

        try:
            subprocess.run(
                ["taskkill", "/T", "/F", "/IM", self.PROCESS_NAME],
                capture_output=True,
                creationflags=CREATE_NO_WINDOW,
            )
            logger.info("[停止] 已发送 taskkill，等待进程退出...")

            # 等待进程退出
            for i in range(wait_timeout):
                time.sleep(1)
                if not self.is_process_running():
                    logger.info("[OK] 进程已退出 (等待 %d 秒)", i + 1)
                    break
                if i == wait_timeout - 1:
                    logger.warning("[停止] 进程 %d 秒后仍未退出", wait_timeout)

            # 等待端口释放
            for i in range(5):
                time.sleep(1)
                if self.is_port_free():
                    logger.info("[OK] 端口 %d 已释放", self.port)
                    return True

            logger.warning("[停止] 端口 %d 未释放，可能残留连接", self.port)
            return True

        except Exception as e:
            logger.error("[ERROR] 停止失败: %s", e)
            return False

    def restart(self) -> bool:
        """重启服务（确保旧进程完全退出后再启动）"""
        self.stop()
        return self.start()
