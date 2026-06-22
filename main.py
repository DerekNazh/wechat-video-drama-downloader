#!/usr/bin/env python3
"""视频号自动监控 - 主入口"""

# 初始化系统（日志、配置、检测等）
import sys
if sys.platform == "win32":
    from core.utils.single_instance import ensure_single_instance
    ensure_single_instance()

import config.settings
import config.initaizler

from gui import run_gui

if __name__ == "__main__":
    run_gui()
