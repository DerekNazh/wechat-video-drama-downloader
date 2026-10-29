#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts_probe_wechat_proxy.py — v2：Chromium proxy.server 格式实测（可重复）
v1 失败原因：headless Edge 访问外网 neverssl 无回显，四轮全 0 无法区分"网络不通"与"代理未生效"。
v2 改进：① 本地起 HTTP 服务器(8999) + Edge --dump-dom 带回显校验（"PROBE_OK" 出现在输出=请求确实发出）；
       ② 目标 URL 用机器名（非 loopback，避开 Chromium 默认 localhost 代理 bypass）；
       ③ 每轮先验证直连可达，再判代理命中；输出四轮对照表。
仍不碰微信真实配置（微信=Chromium radium 内核，读同结构 Preferences，等效成立）。
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
if not os.path.exists(EDGE):
    EDGE = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
PROXY_HOST, PROXY_PORT = "127.0.0.1", 2023
WEB_HOST, WEB_PORT = "127.0.0.1", 8999
HOSTNAME = socket.gethostname()
TEST_URL = "http://%s:%d/" % (HOSTNAME, WEB_PORT)   # 机器名→内网IP，非 loopback，不触发默认 bypass
LOG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_proxy_probe.log")

hit_lock = threading.Lock()
hits = []          # 假代理入站类型
web_hits = 0       # 本地服务器直连次数（代理生效时≈0）
proxy_srv = None
WAIT_HEADED = 12   # 有头启动+加载等待（秒）


def http_server():
    """本地 HTTP 服务器（监听所有接口，机器名可达）：返回 PROBE_OK，统计直连次数。"""
    global web_hits
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind(("0.0.0.0", WEB_PORT))
    s.listen(16)
    while True:
        try:
            conn, _ = s.accept()
        except OSError:
            return
        try:
            conn.settimeout(3)
            conn.recv(1024)
            with hit_lock:
                web_hits += 1
            body = b"PROBE_OK"
            resp = (b"HTTP/1.1 200 OK\r\nContent-Length: %d\r\nContent-Type: text/plain\r\n\r\n" % len(body)) + body
            conn.sendall(resp)
            conn.close()
        except OSError:
            pass


def probe_server():
    """假代理 2023：记录入站类型。"""
    while True:
        try:
            conn, _ = proxy_srv.accept()
        except OSError:
            return
        try:
            conn.settimeout(3)
            data = conn.recv(256)
            if not data:
                conn.close()
                continue
            if data[0] == 0x05:
                kind = "socks5"
                conn.sendall(b"\x05\x00")
            elif data.startswith(b"CONNECT "):
                kind = "http_connect"
                conn.sendall(b"HTTP/1.1 200 Connection established\r\n\r\n")
            elif data.startswith((b"GET ", b"POST ")):
                kind = "http_get"
                conn.sendall(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 0\r\n\r\n")
            else:
                kind = "unknown"
            with hit_lock:
                hits.append(kind)
            conn.close()
        except OSError:
            pass


def write_profile(profile_dir, server_value):
    # v5 修正：现代 Chromium Preferences 位于 <user-data-dir>/Default/Preferences（根目录只有 Local State）
    # 微信等价路径 profiles/<hash>/Preferences —— 同一层结构（profile 目录内）
    default_dir = os.path.join(profile_dir, "Default")
    os.makedirs(default_dir, exist_ok=True)
    prefs = {"profile": {"content_settings": {}}}
    prefs["proxy"] = {"mode": "fixed_servers", "server": server_value} if server_value else {"mode": "direct"}
    with open(os.path.join(default_dir, "Preferences"), "w", encoding="utf-8") as f:
        json.dump(prefs, f)


def run_edge(profile_dir, timeout_s=25):
    """Edge headless --dump-dom 加载测试页。返回 (dom_ok, 代理入站列表)。"""
    with hit_lock:
        hits.clear()
        global web_hits
        web_hits = 0
    # v5：有头模式（微信=有头 Chromium，headless 不读 Preferences proxy，故弃 headless）
    # 窗口移到屏幕外 (-32000,-32000)，不打扰用户桌面；独立 user-data-dir 不与现有 Edge 实例合并
    cmd = [EDGE, "--disable-gpu", "--no-first-run",
           "--no-default-browser-check", "--disable-extensions",
           "--user-data-dir=%s" % profile_dir,
           "--window-position=-32000,-32000", "--window-size=800,600",
           "--disable-background-networking", TEST_URL]
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(WAIT_HEADED)   # 有头启动 + 页面加载 + 网络请求发出
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
    # 有头 Edge 会 fork 子进程，主进程被杀后子进程可能残留——按 user-data-dir 特征清理
    _kill_edge_by_profile(profile_dir)
    time.sleep(0.3)
    # 读回校验：确认启动后 Preferences 的 proxy 键未被 Chromium 重置/覆盖
    kept = False
    pref_path = os.path.join(profile_dir, "Default", "Preferences")
    try:
        with open(pref_path, "r", encoding="utf-8") as f:
            kept = json.load(f).get("proxy", {}).get("mode") is not None
    except Exception:
        kept = False
    with hit_lock:
        got = list(hits)
        wh = web_hits
    return wh, got, kept


def _kill_edge_by_profile(profile_dir):
    """按 --user-data-dir 命令行特征结束残留 Edge 进程（避免孤儿进程占用 2023/8999 观察口径）。"""
    import subprocess as sp
    try:
        out = sp.run(["wmic", "process", "where",
                      "name='msedge.exe'",
                      "get", "ProcessId,CommandLine"],
                     capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return
    for line in out.splitlines():
        if profile_dir.replace("\\", "/") in line.replace("\\", "/"):
            parts = line.strip().split()
            if parts and parts[0].isdigit():
                try:
                    sp.run(["taskkill", "/PID", parts[0], "/T", "/F"],
                           capture_output=True, timeout=8)
                except Exception:
                    pass


def log(s):
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write("%s | %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), s))
    print(s)


def main():
    if not os.path.exists(EDGE):
        log("FAIL: Edge 不存在 %s" % EDGE)
        return 1
    global proxy_srv
    proxy_srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    proxy_srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    proxy_srv.bind((PROXY_HOST, PROXY_PORT))
    proxy_srv.listen(16)
    threading.Thread(target=probe_server, daemon=True).start()
    threading.Thread(target=http_server, daemon=True).start()
    time.sleep(0.3)

    try:
        host_ip = socket.gethostbyname(HOSTNAME)
    except Exception as e:
        host_ip = "解析失败:%s" % e
    log("=== v4 2026-10-29 proxy.server 格式实测（有头Edge/窗口屏外/独立profile；假代理2023+本地页%d；目标URL=%s [%s]；不碰微信）===" % (WEB_PORT, TEST_URL, host_ip))
    cases = [
        ("socks5://127.0.0.1:2023", "A: socks5:// 显式前缀"),
        ("http://127.0.0.1:2023", "B: http:// 显式前缀"),
        ("127.0.0.1:2023", "C: 无 scheme（微信 GUI 原生存储形态）"),
        (None, "D: 对照 direct（应无代理流量）"),
    ]
    res = {}
    for server_value, label in cases:
        d = tempfile.mkdtemp(prefix="wxprobe_")
        try:
            write_profile(d, server_value)
            wh, got, kept = run_edge(d)
            res[label] = (wh, got)
            log("%-34s server=%-22s → 服务器直连:%d 代理入站:%d [%s] proxy键保留:%s" % (
                label, str(server_value), wh, len(got), ",".join(got) or "-", "是" if kept else "否"))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    log("--- 判定（判据：代理生效=假代理有入站 且 本地服务器直连≈0；未生效=反之） ---")
    d = res.get("D: 对照 direct（应无代理流量）", (0, []))
    if d[0] == 0 and d[1]:
        log("  警示: 对照 D 服务器无直连但代理有入站 → 意外代理，本轮整体不可信")
    if d[0] == 0 and not d[1]:
        log("  警示: 对照 D 两侧均无流量 → 页面未加载，本轮整体不可信")
    for label, (wh, got) in res.items():
        if label.startswith("D"):
            continue
        if wh == 0 and got:
            log("  ✓ %s → 走代理生效（入站 %d）" % (label, len(got)))
        else:
            log("  ✗ %s → 未走代理（服务器直连 %d / 代理入站 %d）" % (label, wh, len(got)))
    c = res.get("C: 无 scheme（微信 GUI 原生存储形态）", (0, []))
    if d[0] > 0 and not d[1] and c[0] == 0 and c[1]:
        log("  结论: 无scheme(127.0.0.1:2023) 被 Chromium 按 HTTP 代理读取生效 → 注入值锁定「127.0.0.1:2023」")
    elif any(not got for _, (wh, got) in res.items() if wh == 0 and got):
        pass
    else:
        log("  结论: 有头模式三种格式均未见代理入站 → 需人工复查（先看 D 是否可信）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
