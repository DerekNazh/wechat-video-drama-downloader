#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
前端门禁（本地化，ADR-021）：static/js 改动后必跑。
  L0 语法：全部 .js 跑 node --check（拦语法错/白屏）
  L1 安全：静态扫描禁止 XSS 模式回归
    R1 内联 onclick 内嵌模板插值或引号拼接（新注入点）
    R2 innerHTML 直插外部数据字段（未走 escapeHtml/escHtml）
    R3 运行时 setAttribute('onclick') 与手写转义复活（escapeAttr/escAttr）
用法：python scripts_check_frontend.py [--quiet]
退出码：0=通过；1=有违例（列出文件+行+规则+代码）
"""
import argparse
import glob
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
JS_DIR = os.path.join(ROOT, "static", "js")

# 外部数据字段名（出现即视为不可信数据，直插 innerHTML 必须转义）
EXTERNAL_FIELDS = r"(title|nickname|name|username|author|signature|head_url|bio|message|video_id|video\.id|task\.id|taskId|task_id|data\.|item\.|l\.|r\.|d\.)"

# ---- L1 规则（正则） ----
# R1a: 模板字符串内 onclick 含外部数据字段 ${ 插值（数字/内部常量插值不算注入面）
R1_TEMPLATE = re.compile(r'onclick="[^"]*\$\{%s\}' % EXTERNAL_FIELDS)
# R1b: 字符串拼接内 onclick 含引号拼接（\'...\' 形式；onclick="addX(this)" 无拼接不算）
R1_CONCAT = re.compile(r'onclick="[^"]*(\'|\+\\")')
# R1c: onclick 内出现 \\' + （转义引号拼接）
R1_ESCAPED = re.compile(r"onclick=[^>]*\\'\+")
# R3a: 运行时动态 onclick
R3_ONCLICK_ATTR = re.compile(r"setAttribute\(\s*['\"]onclick['\"]")
# R3b: 手写转义工具复活（统一走 utils/html.js 的 escapeHtml）
R3_ESCATTR = re.compile(r"\bescapeAttr\(|\bescAttr\(")


def l0_syntax(files):
    """node --check 全部 JS，返回 (违规列表, 检查数)。"""
    violations = []
    for f in files:
        r = subprocess.run(["node", "--check", f], capture_output=True, text=True)
        if r.returncode != 0:
            violations.append((f, 0, "L0 语法", (r.stderr or r.stdout).strip()[:200]))
    return violations


def l1_scan(files):
    """静态扫描 XSS 模式，返回违规列表。"""
    violations = []
    for f in files:
        with open(f, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.read().split("\n")

        for i, line in enumerate(lines):
            lineno = i + 1
            # R1a / R1b / R1c
            if R1_TEMPLATE.search(line):
                violations.append((f, lineno, "R1 内联 onclick 含模板插值", line.strip()[:120]))
            elif R1_CONCAT.search(line) and "\\'" in line:
                violations.append((f, lineno, "R1 内联 onclick 含引号拼接", line.strip()[:120]))
            # R3
            if R3_ONCLICK_ATTR.search(line):
                violations.append((f, lineno, "R3 运行时 setAttribute(onclick)", line.strip()[:120]))
            if R3_ESCATTR.search(line):
                violations.append((f, lineno, "R3 手写转义复活(escapeAttr/escAttr)", line.strip()[:120]))

            # R2: innerHTML 直插外部数据（行 + 后 10 行窗口）
            if ".innerHTML" in line and re.search(r"innerHTML\s*=", line):
                window = "\n".join(lines[i:i + 11])
                if re.search(r"\$\{%s\}" % EXTERNAL_FIELDS, window) and not re.search(
                        r"escapeHtml|escHtml", window):
                    violations.append((f, lineno, "R2 innerHTML 直插外部数据(未转义)", line.strip()[:120]))
    return violations


def main():
    ap = argparse.ArgumentParser(description="号匣前端门禁 L0+L1")
    ap.add_argument("--quiet", action="store_true", help="只输出结果摘要")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(JS_DIR, "**", "*.js"), recursive=True))
    if not files:
        print("[GATE] 未找到 JS 文件: %s" % JS_DIR)
        return 1

    syn = l0_syntax(files)
    sec = l1_scan(files)

    all_v = syn + sec
    if args.quiet:
        print("[GATE] JS=%d 文件, L0语法=%s, L1安全=%s → %s" % (
            len(files), "PASS" if not syn else "FAIL(%d)" % len(syn),
            "PASS" if not sec else "FAIL(%d)" % len(sec),
            "通过" if not all_v else "有违例"))
    else:
        for f, ln, rule, snippet in all_v:
            print("[FAIL] %s:%d  %s\n       %s" % (os.path.relpath(f, ROOT), ln, rule, snippet))
        print("")
        print("[GATE] 扫描 %d 个 JS 文件 → L0语法 %s / L1安全 %s / 总计 %s" % (
            len(files),
            "PASS" if not syn else "FAIL(%d)" % len(syn),
            "PASS" if not sec else "FAIL(%d)" % len(sec),
            "PASS ✅" if not all_v else "FAIL ❌"))

    return 1 if all_v else 0


if __name__ == "__main__":
    sys.exit(main())
