"""视频号自动监控 - GUI 启动模块"""

import os
import sys
import socket
import time
import subprocess
import threading
import logging
import winreg
from pathlib import Path

from config.settings import settings
from core.api import create_app, shutdown_monitor

logger = logging.getLogger(__name__)


# ==================== WebView2 检测与引导安装 ====================

def _is_webview2_available() -> bool:
    """检测系统是否安装了 WebView2 Runtime"""
    try:
        import winreg
        keys = [
            (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'),
            (winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'),
            (winreg.HKEY_CURRENT_USER, r'SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'),
        ]
        for hive, path in keys:
            try:
                with winreg.OpenKey(hive, path) as key:
                    build, _ = winreg.QueryValueEx(key, 'pv')
                    if build and str(build) != '0':
                        return True
            except OSError:
                continue
    except Exception:
        pass
    return False


def _find_bootstrapper() -> Path | None:
    """查找本地 WebView2 Bootstrapper"""
    if getattr(sys, 'frozen', False):
        app_root = Path(sys.executable).parent
    else:
        app_root = Path(__file__).parent

    candidates = [
        app_root / "lib" / "MicrosoftEdgeWebview2Setup.exe",
        app_root / "MicrosoftEdgeWebview2Setup.exe",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None


def _ensure_webview2():
    """检测 WebView2 Runtime，未安装时自动运行 Bootstrapper

    Returns:
        True 表示可用（已安装或安装成功），False 表示不可用
    """
    if _is_webview2_available():
        logger.info("[WebView2] 系统已安装 WebView2 Runtime")
        return True

    logger.warning("[WebView2] 系统未安装 WebView2 Runtime，尝试引导安装")

    bootstrapper = _find_bootstrapper()
    if not bootstrapper:
        logger.error("[WebView2] 未找到 MicrosoftEdgeWebview2Setup.exe，"
                     "请从 https://developer.microsoft.com/microsoft-edge/webview2/ 下载安装")
        return False

    logger.info(f"[WebView2] 运行 Bootstrapper: {bootstrapper}")
    try:
        result = subprocess.run(
            [str(bootstrapper), "/silent", "/install"],
            timeout=120,
        )
        if result.returncode == 0:
            logger.info("[WebView2] WebView2 Runtime 安装成功")
            return True
        else:
            logger.warning(f"[WebView2] Bootstrapper 返回码: {result.returncode}")
            return _is_webview2_available()
    except subprocess.TimeoutExpired:
        logger.warning("[WebView2] Bootstrapper 安装超时")
        return _is_webview2_available()
    except Exception as e:
        logger.error(f"[WebView2] Bootstrapper 运行失败: {e}")
        return False


# ==================== pywebview 暴露给前端 API ====================


class ExposedAPI:
    """暴露给前端 JavaScript 的 API，供 pywebview 保存对话框下载使用

    注意：create_file_dialog() 必须在主线程调用，不能在后台线程里调。
    因此 HTTP 请求和文件写入放到后台线程，create_file_dialog 在主线程执行。
    """

    def __init__(self, base_url: str, window_ref: dict):
        self.base_url = base_url
        self._window_ref = window_ref

    @property
    def _window(self):
        return self._window_ref.get("window")

    def _do_download(self, api_path: str, default_filename: str) -> dict:
        """下载文件：HTTP 请求放后台线程，API 函数立即返回不阻塞。

        后端数据就绪后，从后台线程通过 evaluate_js 回调通知前端，
        前端再弹保存对话框（通过 fetch + blob URL 方式无需阻塞）。
        """
        import json
        import re
        import urllib.request
        from threading import Thread
        import webview

        result_holder = [None]  # {"success": bool, "message": str}

        def background_download():
            content = None
            filename = default_filename
            try:
                api_url = f"{self.base_url}{api_path}"
                req = urllib.request.Request(api_url)
                with urllib.request.urlopen(req, timeout=10) as resp:
                    content = resp.read()
                    cd = resp.headers.get("Content-Disposition", "")
                    if "filename=" in cd:
                        m = re.search(r'filename="?([^";\n]+)"?', cd)
                        if m:
                            filename = m.group(1)
            except Exception as e:
                result_holder[0] = {"success": False, "message": f"请求文件失败: {e}"}
                self._window.evaluate_js(
                    f"window._downloadCallback({json.dumps(result_holder[0], ensure_ascii=False)})"
                )
                return

            if content is None:
                result_holder[0] = {"success": False, "message": "服务器未返回内容"}
                self._window.evaluate_js(
                    f"window._downloadCallback({json.dumps(result_holder[0], ensure_ascii=False)})"
                )
                return

            # 弹保存对话框（后台线程调用 create_file_dialog 不阻塞 GUI）
            try:
                file_path = self._window.create_file_dialog(
                    dialog_type=webview.FileDialog.SAVE,
                    save_filename=filename,
                    file_types=["CSV 文件 (*.csv)", "所有文件 (*.*)"],
                )
            except Exception as e:
                result_holder[0] = {"success": False, "message": f"对话框异常: {e}"}
                self._window.evaluate_js(
                    f"window._downloadCallback({json.dumps(result_holder[0], ensure_ascii=False)})"
                )
                return

            if file_path is None:
                result_holder[0] = {"success": False, "message": "已取消保存"}
                self._window.evaluate_js(
                    f"window._downloadCallback({json.dumps(result_holder[0], ensure_ascii=False)})"
                )
                return

            # winforms create_file_dialog 返回元组，取第一个元素
            if isinstance(file_path, tuple):
                file_path = file_path[0]

            # 写文件
            try:
                Path(file_path).write_bytes(content)
                result_holder[0] = {"success": True, "message": f"已保存到: {file_path}"}
            except Exception as e:
                result_holder[0] = {"success": False, "message": f"写入文件失败: {e}"}

            self._window.evaluate_js(
                f"window._downloadCallback({json.dumps(result_holder[0], ensure_ascii=False)})"
            )

        # API 函数本身立即返回，不阻塞
        Thread(target=background_download, daemon=True).start()
        return None

    def download_template(self) -> dict:
        """下载作者导入模板 CSV"""
        return self._do_download("api/inputer/csv/template", "author_import_template.csv")

    def download_excel_template(self) -> dict:
        """下载 Excel 导入模板"""
        return self._do_download("api/inputer/excel/template", "excel_import_template.xlsx")

    def download_failed_csv(self, token: str) -> dict:
        """下载失败 CSV"""
        if not token or not token.strip():
            return {"success": False, "message": "没有可下载的失败 CSV"}
        return self._do_download(f"api/authors/import-failed/{token}", "author_import_failed.csv")

    def select_folder(self) -> dict:
        """选择文件夹对话框，返回选中路径或取消信息"""
        import webview
        logger = logging.getLogger(__name__)

        logger.debug("[select_folder] 开始调用 create_file_dialog")
        try:
            folder_path = self._window.create_file_dialog(
                dialog_type=webview.FileDialog.FOLDER,
            )
            logger.debug(f"[select_folder] create_file_dialog 返回: {folder_path}")
        except Exception as e:
            logger.error(f"[select_folder] 对话框异常: {e}")
            return {"success": False, "message": f"对话框异常: {e}"}

        if folder_path is None:
            logger.debug("[select_folder] 用户取消选择")
            return {"success": False, "message": "已取消选择"}

        if isinstance(folder_path, tuple):
            folder_path = folder_path[0]

        logger.debug(f"[select_folder] 返回路径: {folder_path}")
        return {"success": True, "path": folder_path}

    def destroy(self):
        """关闭应用窗口"""
        import webview
        if self._window:
            self._window.destroy()


# ==================== 辅助函数 ====================

def get_available_port() -> int:
    """获取可用端口"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        s.listen(1)
        return s.getsockname()[1]


def run_fastapi_in_thread(host: str, port: int, ready_event: threading.Event) -> threading.Thread:
    """在子线程中启动 FastAPI"""
    import uvicorn

    def _serve():
        try:
            logger.debug("[服务器] 开始创建应用...")
            app = create_app()
            logger.debug("[服务器] 应用创建成功")

            config = uvicorn.Config(
                app,
                host=host,
                port=port,
                log_level="warning",
                log_config=None,
                timeout_graceful_shutdown=3,
            )
            server = uvicorn.Server(config)
            logger.debug(f"[服务器] 服务器配置完成，即将设置事件")

            if ready_event:
                ready_event.set()
                logger.debug("[服务器] 已设置 ready_event")

            logger.debug("[服务器] 开始运行服务器...")
            server.run()
        except Exception as e:
            logger.error(f"[服务器] 启动失败: {e}")
            import traceback
            traceback.print_exc()
            if ready_event:
                ready_event.set()

    t = threading.Thread(target=_serve, daemon=True)
    t.start()
    return t


# ==================== 主入口 ====================

def run_gui():
    """桌面 GUI 模式 - 启动 FastAPI 和 webview 窗口"""
    host = "127.0.0.1"
    port = get_available_port()
    base_url = f"http://{host}:{port}/"

    logger.info(f"使用端口: {port}")
    logger.info(f"后台服务: {base_url}")

    ready_event = threading.Event()
    server_thread = run_fastapi_in_thread(host, port, ready_event)
    logger.info("等待后台服务启动...")

    ready_event.wait(timeout=30)
    logger.debug(f"[主线程] ready_event.wait() 返回，事件已设置")

    time.sleep(1)

    logger.info("后台服务已启动")

    try:
        import webview

        # 检测 WebView2，未安装时尝试引导安装
        webview2_ok = _ensure_webview2()
        if not webview2_ok:
            logger.warning("[WebView2] WebView2 Runtime 不可用，pywebview 将降级到 MSHTML（IE 内核）")
            logger.warning("[WebView2] 前端可能无法正常加载，建议安装 WebView2 Runtime")

        logger.info("[webview] 开始创建窗口...")

        # 用容器解决 window 循环引用：先建容器，window 创建后再填入
        _window_ref: dict = {}

        def _make_api():
            return ExposedAPI(base_url, _window_ref)

        ads_suffix = " - 加入交流群：https://docs.qq.com/doc/DRVByZHBGREtJT1pG" if settings.ads_enabled else ""
        window = webview.create_window(
            title=f"视频号监控控制台 v{settings.project_version}{ads_suffix}",
            url=base_url,
            width=950,
            height=750,
            min_size=(800, 650),
            confirm_close=False,
            background_color="#0D1117",
            js_api=_make_api(),
        )
        _window_ref["window"] = window
        logger.info(f"[webview] 窗口创建成功，URL: {base_url}")

        _shutdown_done = threading.Event()

        def on_closing():
            """窗口关闭：立即隐藏窗口，后台执行优雅退出"""
            if _shutdown_done.is_set():
                return False

            logger.info("[webview] 窗口关闭请求，隐藏窗口并后台执行优雅退出...")
            window.hide()

            def _graceful_shutdown():
                try:
                    # 0. 保存活跃任务为 pending（断点续传：下次启动时自动恢复）
                    from core.utils.database import db
                    for status in ("running", "wait"):
                        tasks = db.list_download_tasks(status=status, limit=1000)
                        for task in tasks:
                            db.update_download_task_status(task.task_id, "pending")
                        if tasks:
                            logger.info("[webview] 已保存 %d 个 %s 任务为 pending", len(tasks), status)
                except Exception as e:
                    logger.error(f"[webview] 保存下载任务异常: {e}")

                try:
                    # 1. 先停止监控器
                    shutdown_monitor()
                    logger.info("[webview] 监控器已关闭（含下载任务清理）")
                except Exception as e:
                    logger.error(f"[webview] 监控器关闭异常: {e}")

                try:
                    # 2. 停止 Go 后端服务
                    from core.utils.base_servier import WechatVideoService
                    svc = WechatVideoService()
                    if svc.is_process_running():
                        logger.info("[webview] 正在停止微信视频号后端服务...")
                        svc.stop()
                        logger.info("[webview] 微信视频号后端服务已停止")
                    else:
                        logger.info("[webview] 微信视频号后端服务未运行，无需停止")
                except Exception as e:
                    logger.error(f"[webview] Go 后端服务停止异常: {e}")

                try:
                    # 3. 清除系统代理（应用退出后不应残留代理设置）
                    proxy_key = winreg.HKEY_CURRENT_USER
                    proxy_path = r'Software\Microsoft\Windows\CurrentVersion\Internet Settings'
                    with winreg.OpenKey(proxy_key, proxy_path, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as key:
                        try:
                            enabled, _ = winreg.QueryValueEx(key, 'ProxyEnable')
                            logger.info("[webview] 当前 ProxyEnable=%s", enabled)
                            if enabled != 0:
                                winreg.SetValueEx(key, 'ProxyEnable', 0, winreg.REG_DWORD, 0)
                                logger.info("[webview] 已将系统代理 ProxyEnable 置为 0")
                            else:
                                logger.info("[webview] ProxyEnable 已为 0，无需修改")
                        except OSError as e:
                            logger.warning("[webview] 读取/写入 ProxyEnable 失败: %s", e)
                        try:
                            winreg.DeleteValue(key, 'ProxyServer')
                            logger.info("[webview] 已清除系统代理 ProxyServer")
                        except OSError:
                            pass
                except Exception as e:
                    logger.error(f"[webview] 清除系统代理异常: {e}")

                _shutdown_done.set()
                logger.info("[webview] 清理完成，退出进程")
                os._exit(0)

            threading.Thread(target=_graceful_shutdown, daemon=True).start()
            return False  # 取消窗口关闭，由后台线程退出

        def on_closed():
            pass

        window.events.closing += on_closing
        window.events.closed += on_closed
        logger.info("[webview] 开始启动 GUI...")
        if webview2_ok:    #mshtml     edgechromium
            webview.start(debug=settings.pywebview_debug, gui='edgechromium')
        else:
            logger.warning("[webview] 使用默认渲染引擎（非 edgechromium）")
            webview.start(debug=settings.pywebview_debug)

    except ImportError:
        logger.error("pywebview 未安装，请运行: pip install pywebview")
        sys.exit(1)
    except Exception as e:
        logger.error(f"[webview] 启动失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


def main():
    run_gui()


if __name__ == "__main__":
    main()
