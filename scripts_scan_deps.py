#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts_scan_deps.py —— 环境固化辅助：AST 扫描项目真实第三方依赖（不扫 vendored 目录）。
用法: uv run python scripts_scan_deps.py
输出: 非 stdlib 顶层模块名（去重排序）。config/core 等项目内部包、_tikhub_pkg/_tikhub_sdk 本地 vendored 不扫。
"""
import ast
import pathlib
import sys

STDLIB = set(sys.stdlib_module_names)
ROOT = pathlib.Path(__file__).resolve().parent
# 扫描范围：运行时代码 + 开发工具脚本；排除 vendored / 构建产物 / 测试夹具
SCAN_DIRS = [ROOT / "config", ROOT / "core", ROOT / "static" if False else None]
EXCLUDE_DIRS = {"_tikhub_pkg", "_tikhub_sdk", "_redfox_probe", ".venv", "tools", "tests", "_e2e_verify", "docs_柠檬后台截图", "doc-fetch-resources"}


def targets():
    files = []
    # config/ + core/ + gui.py + build.py（运行时）
    for name in ("config", "core"):
        d = ROOT / name
        if d.is_dir():
            files.extend(p for p in d.rglob("*.py") if not any(part in EXCLUDE_DIRS for part in p.parts))
    for name in ("gui.py", "build.py", "weixin_exe/main.py"):
        p = ROOT / name
        if p.exists():
            files.append(p)
    # scripts_*.py（开发工具）
    files.extend(p for p in ROOT.glob("scripts_*.py"))
    return files


def main():
    runtime = set()
    tool = set()
    for f in targets():
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            continue
        is_tool = f.name.startswith("scripts_")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    (tool if is_tool else runtime).add(a.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                (tool if is_tool else runtime).add(node.module.split(".")[0])

    def clean(s):
        return sorted(d for d in s if d not in STDLIB and d != "__future__" and d not in ("config", "core", "tools", "tests", "tikhub"))

    print("=== 运行时依赖（config/ core/ gui.py build.py）===")
    print("\n".join(clean(runtime)) or "(无)")
    print("=== 工具脚本依赖（scripts_*.py，仅开发用）===")
    print("\n".join(clean(tool)) or "(无)")
    print("=== 工具脚本专属（不在运行时里）===")
    print("\n".join(clean(tool - runtime)) or "(无)")


if __name__ == "__main__":
    main()
