#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_all.py —— 号匣本地 CI 门禁（ADR-021 本地化，YZPQ-326 任务一）。
串联以下检查，任一红即 exit 1（供 pre-commit 与发版前 Step1 调用）：
  L0 语法   : compileall 全部运行时 .py（config/core/*.py + gui/build/main）
  L1 前端安全: scripts_check_frontend.py（node --check + XSS 回归扫描）
  契约     : pytest tests/test_go_contract.py（Tikhub/Go 契约快照）
  依赖扫描 : scripts_scan_deps.py（仅打印实际第三方依赖，信息项不阻断）
  单测     : pytest tests/ -q
用法: python scripts/check_all.py
退出码: 0=全绿；1=任一红。
"""
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VENV_PY = os.path.join(ROOT, ".venv", "Scripts", "python.exe")
PY = VENV_PY if os.path.exists(VENV_PY) else sys.executable


def run(label, cmd, blocking=True):
    print("\n==== [%s] $ %s ====" % (label, " ".join(cmd)), flush=True)
    p = subprocess.run(cmd, cwd=ROOT)
    ok = (p.returncode == 0)
    if not ok and not blocking:
        print("[%s] 信息项未绿（不阻断）rc=%s" % (label, p.returncode))
        return True
    if not ok:
        print("[%s] *** 红 rc=%s ***" % (label, p.returncode))
    return ok


def main():
    results = []

    # L0 语法：compileall 运行时 py
    runtime_dirs = [os.path.join(ROOT, d) for d in ("config", "core")
                    if os.path.isdir(os.path.join(ROOT, d))]
    runtime_files = [os.path.join(ROOT, f) for f in ("gui.py", "build.py", "main.py", "runtime_hook.py")
                     if os.path.isfile(os.path.join(ROOT, f))]
    import py_compile
    l0_bad = 0
    for f in runtime_files:
        try:
            py_compile.compile(f, doraise=True)
        except py_compile.PyCompileError as e:
            l0_bad += 1
            print("L0 语法错:", e)
    for d in runtime_dirs:
        for dirpath, _, names in os.walk(d):
            if ".venv" in dirpath:
                continue
            for n in names:
                if n.endswith(".py"):
                    fp = os.path.join(dirpath, n)
                    try:
                        py_compile.compile(fp, doraise=True)
                    except py_compile.PyCompileError as e:
                        l0_bad += 1
                        print("L0 语法错:", e)
    results.append(("L0 语法", l0_bad == 0))

    # L1 前端安全（内部已含 node --check + XSS 扫描，退出码即判据）
    results.append(("L1 前端安全",
                    run("L1 前端安全", [PY, os.path.join(ROOT, "scripts_check_frontend.py")])))

    # 契约
    results.append(("契约 go_contract",
                    run("契约", [PY, "-m", "pytest", os.path.join("tests", "test_go_contract.py"), "-q"])))

    # 依赖扫描（信息项，不阻断）
    run("依赖扫描", [PY, os.path.join(ROOT, "scripts_scan_deps.py")], blocking=False)

    # 全量单测
    results.append(("pytest",
                    run("pytest", [PY, "-m", "pytest", "tests", "-q"])))

    print("\n========== check_all 汇总 ==========")
    all_ok = True
    for name, ok in results:
        print(("  [绿] " if ok else "  [红] ") + name)
        all_ok = all_ok and ok
    print("====================================")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
