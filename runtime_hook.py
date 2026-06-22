"""
PyInstaller runtime hook - 视频号自动监控

在打包后的 exe 启动时执行，用于：
1. 设置正确的工作目录
2. 添加嵌入式资源路径
"""
import sys
import os
from pathlib import Path

# 获取 exe 所在目录（打包后）或脚本目录（开发时）
if getattr(sys, 'frozen', False):
    # 打包后：exe 所在目录
    APP_ROOT = Path(sys.executable).parent
else:
    # 开发时：项目根目录
    APP_ROOT = Path(__file__).parent

# 设置工作目录为 exe 所在目录
os.chdir(str(APP_ROOT))

# 添加静态资源路径到 sys.path
static_path = APP_ROOT / "static"
if static_path.exists():
    sys.path.insert(0, str(static_path))

# 添加 lib 目录（存放 gopeed.exe 等）
lib_path = APP_ROOT / "lib"
if lib_path.exists():
    sys.path.insert(0, str(lib_path))
