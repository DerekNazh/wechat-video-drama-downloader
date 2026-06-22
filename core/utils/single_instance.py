"""单实例检测模块

在所有服务启动之前执行，确保同一时间只有一个应用实例运行。
检测到重复实例时：激活已有窗口 → 弹窗提示 → 退出新实例。

Mutex 名称包含应用唯一标识，避免与同系列其他应用（如智能剪辑v4）冲突。
窗口激活基于标题正则匹配，只激活标题符合本应用格式的窗口。
"""

import ctypes
import logging
import re
import sys

logger = logging.getLogger("single_instance")

MUTEX_NAME = "VideoMonitor_Downloader_SingleInstance_Mutex"
# 匹配 "视频号监控控制台 v1.1.1" 或 "视频号监控控制台 v1.1.1 - 加入交流群..."
# 不匹配 "新智能剪辑 v1.0.1"
WINDOW_TITLE_PATTERN = re.compile(r"^视频号监控控制台\s+v[\d.]+")
ERROR_ALREADY_EXISTS = 183


class Win32API:
    """Windows API 薄层封装，便于 mock 测试"""

    @staticmethod
    def create_mutex(name):
        """创建命名 Mutex，返回 (handle, last_error)"""
        kernel32 = ctypes.windll.kernel32
        handle = kernel32.CreateMutexW(None, False, name)
        last_error = kernel32.GetLastError()
        return handle, last_error

    @staticmethod
    def find_window_by_title(pattern):
        """按标题正则查找窗口，返回 hwnd 或 0

        Args:
            pattern: 编译后的正则表达式，窗口标题需完全匹配
        """
        user32 = ctypes.windll.user32
        hwnd_found = ctypes.c_long(0)

        @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_long, ctypes.c_long)
        def enum_callback(hwnd, _lparam):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                if pattern.match(buf.value):
                    hwnd_found.value = hwnd
                    return False
            return True

        user32.EnumWindows(enum_callback, 0)
        return hwnd_found.value

    @staticmethod
    def activate_window(hwnd):
        """激活窗口到前台，绕过 Windows 前台锁限制"""
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        user32.ShowWindow(hwnd, 9)  # SW_RESTORE

        current_thread = kernel32.GetCurrentThreadId()
        foreground_hwnd = user32.GetForegroundWindow()
        pid = ctypes.c_ulong(0)
        foreground_thread = user32.GetWindowThreadProcessId(foreground_hwnd, ctypes.byref(pid))

        attached = False
        if foreground_thread and foreground_thread != current_thread:
            user32.AttachThreadInput(current_thread, foreground_thread, True)
            attached = True

        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)

        if attached:
            user32.AttachThreadInput(current_thread, foreground_thread, False)

    @staticmethod
    def show_message_box(text, title, icon=0x40):
        """显示 Windows 消息框"""
        ctypes.windll.user32.MessageBoxW(0, text, title, icon)


def ensure_single_instance(api=None):
    """确保只有一个应用实例运行。

    如果已有实例运行：
    1. 尝试激活已有窗口到前台
    2. 弹窗提示用户
    3. 退出当前实例

    Args:
        api: Win32API 实例（依赖注入，便于测试时 mock）

    Returns:
        True 如果当前是唯一实例（可以继续启动）
    """
    if sys.platform != "win32":
        return True

    if api is None:
        api = Win32API()

    _handle, last_error = api.create_mutex(MUTEX_NAME)

    if last_error == ERROR_ALREADY_EXISTS:
        logger.info("[single_instance] 检测到已有实例运行，尝试激活窗口")
        _activate_existing(api)
        api.show_message_box(
            "应用已在运行！\n已将运行中的窗口激活到前台。",
            "视频号监控控制台",
        )
        sys.exit(0)

    return True


def _activate_existing(api):
    """查找并激活已有实例的窗口"""
    hwnd = api.find_window_by_title(WINDOW_TITLE_PATTERN)
    if hwnd:
        try:
            api.activate_window(hwnd)
            logger.info("[single_instance] 已激活已有窗口")
        except Exception:
            logger.warning("[single_instance] 激活窗口失败，仅弹窗提示")
    else:
        logger.info("[single_instance] 未找到已有窗口，可能窗口标题已变化")
