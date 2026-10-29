"""更新落地（YZPQ-316）：下载包暂存 + 重启时替换脚本生成。

真正的 exe 替换在重启时由外部批处理执行（GUI/进程职责），这里只做可单测的
纯逻辑：暂存新版、生成替换脚本、失败回退标记。装用户目录保写权限。
"""
from __future__ import annotations

import os


def stage_package(data: bytes, staged_path: str) -> str:
    os.makedirs(os.path.dirname(staged_path), exist_ok=True)
    with open(staged_path, "wb") as f:
        f.write(data)
    return staged_path


def build_replace_script(current_exe: str, staged_exe: str,
                         backup_exe: str, log_path: str) -> str:
    """生成 Windows 批处理：等进程退出 -> 备份旧版 -> 替换 -> 重启新版。

    失败时不删旧备份，旧版仍可手动拉起。
    """
    return (
        "@echo off\r\n"
        "timeout /t 2 /nobreak >nul\r\n"
        f'copy /Y "{current_exe}" "{backup_exe}" >> "{log_path}" 2>&1\r\n'
        f'if errorlevel 1 exit /b 1\r\n'
        f'copy /Y "{staged_exe}" "{current_exe}" >> "{log_path}" 2>&1\r\n'
        f'if errorlevel 1 exit /b 1\r\n'
        f'start "" "{current_exe}"\r\n'
    )


def fallback_available(backup_exe: str) -> bool:
    return os.path.exists(backup_exe)
