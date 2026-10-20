"""--selftest 入口：一条命令验证下载链路（无需打开微信）

用法（项目根目录）：
    python -m tests.selftest

输出：
    [节点探测] res_download(8899) / Go 上游(2023) / Go API(2022) 真实监听状态（只报告，不判过）
    [严格自检] L0 命名规则 + L2 真实下载链路（字节级校验，判定 PASS/FAIL）

设计：与 pytest 用例共用 tests/core_checks.py 的严格断言，
保证命令行自检与测试套件口径一致（不能太假、不能太宽松）。
"""
from __future__ import annotations

import socket
import sys
import tempfile
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient

from tests import core_checks, mock_video_server
from tests.core_checks import (
    CheckError,
    check_download_ok,
    check_failure_clean,
    check_no_duplicate_request,
    ensure_test_mp4,
)

BASE = "http://127.0.0.1:19099"
APP_ID = "127"

# 真实链路节点（只探测报告，判定交给严格自检）
NODES = [
    ("res_download 代理", 8899),
    ("Go 上游端口", 2023),
    ("Go API", 2022),
]

_results: list[tuple[str, bool, str]] = []


def _record(name: str, ok: bool, detail: str = ""):
    _results.append((name, ok, detail))
    mark = "✅" if ok else "❌"
    suffix = f"  ({detail})" if detail else ""
    print(f"  {mark} {name}{suffix}")


def _check_port(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1.0):
            return True
    except OSError:
        return False


def run_system_proxy_probe():
    """系统代理实况：读 Windows 注册表，检测"谁占用了系统代理"

    拓扑（2026-10-21 审查确认）：系统代理唯一写者 = res_download_service
    （只写 127.0.0.1:8899）；Go 黑盒 proxy.system=false 不自写；2022/2023
    不在系统代理层。冲突风险来自"用户其他代理工具"（如 Clash）与产品互抢
    注册表。本段如实报告，不判过不判挂。
    """
    import winreg
    try:
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
                0, winreg.KEY_READ) as key:
            proxy_enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
            proxy_server, _ = winreg.QueryValueEx(key, "ProxyServer")
    except FileNotFoundError:
        print("  ℹ️  系统代理: 注册表 ProxyEnable 键不存在（未启用）")
        return
    except OSError as e:
        print(f"  ℹ️  系统代理: 读取注册表失败: {e}")
        return

    if not proxy_enable:
        print("  ℹ️  系统代理: 未启用（ProxyEnable=0）")
        return
    if proxy_server == "127.0.0.1:8899":
        print("  ✅ 系统代理: 指向本产品 127.0.0.1:8899（唯一写者，无冲突）")
    else:
        print(f"  ⚠️  系统代理: 被其他代理占用 {proxy_server}（如 Clash/用户手动设置）"
              f"—— 产品 open_proxy 会覆盖它，recover_stale_proxy 会跳过它")


def run_proxy_chain_probe():
    """真实代理链实穿（诊断 + 判定分离）

    链路语义（2026-10-21 复核）：
    - 短剧下载（direct-download）由 Python 直连 CDN，不经过 8899→2023 代理链；
      本自检的 L2 段已覆盖该支线。
    - 视频号场景流量才走：系统代理 8899(res_download) → 2023(Go MITM) → 微信。
      MITM 代理预期只解密微信域流量，对普通 http 探测返回非 JSON 属预期内。

    判定规则：
    - 8899 在线 → 经它转发 probe 到 mock 服务器，通 = 系统代理链路入口健康（判定项）
    - 8899 未监听 → ⏭ 跳过（外部黑盒未启动，不判过不判挂）
    - 2023 → 诊断行（记录返回内容摘要，不判过不判挂）
    """
    import httpx
    marker = f"chain-{int(time.time())}"
    probe_url = f"{BASE}/probe?marker={marker}"

    # 8899 = 系统代理入口（视频号流量第一跳）：判定项
    if not _check_port(8899):
        print("  ⏭ 代理链实穿: res_download(8899) 未监听 → 跳过"
              "（程序未运行时外部代理不在线，不判过不判挂）")
    else:
        try:
            with httpx.Client(proxy="http://127.0.0.1:8899", timeout=6.0) as c:
                r = c.get(probe_url)
                data = r.json()
            if data.get("ok") is True and data.get("marker") == marker:
                _record("代理链实穿: 经 res_download(8899) 转发到 mock 服务器", True,
                        "marker 回显一致 → 系统代理转发通")
            else:
                _record("代理链实穿: 经 res_download(8899) 转发", False,
                        f"响应非预期 status={r.status_code} body={str(data)[:120]}")
        except Exception as e:
            _record("代理链实穿: 经 res_download(8899) 转发", False, str(e)[:120])

    # 2023 = Go MITM 上游：诊断行（不判过不判挂）
    if _check_port(2023):
        try:
            with httpx.Client(proxy="http://127.0.0.1:2023", timeout=6.0) as c:
                r = c.get(probe_url)
            print(f"  ℹ️  诊断: Go MITM(2023) 对非微信 http 探测返回 status={r.status_code} "
                  f"body前60={r.text[:60]!r}（MITM 预期只解密微信域流量，非微信请求非 JSON 属预期）")
        except Exception as e:
            print(f"  ℹ️  诊断: Go MITM(2023) 探测异常: {str(e)[:100]}（仅诊断，不判过）")


def run_unit_checks():
    from core.api.routers.sniff_proxy import _parse_download_url
    from core.service.task import find_downloaded_file
    from core.utils.weixin_client import build_video_filename

    app_id, video_id, suffix = _parse_download_url(
        "http://cdn.example.com/episode/video123/video.mp4?from=web")
    _record("URL 解析: 短剧ID/视频ID/后缀", app_id == "cdn" and video_id == "video123" and suffix == ".mp4",
            f"got=({app_id},{video_id},{suffix})")

    name = build_video_filename("我的视频", "2026-10-20T10:00:00", "1080p", "vid1")
    _record("命名规则: 日期_标题_规格_ID", name == "2026-10-20_我的视频_1080p_vid1.mp4", name)

    with tempfile.TemporaryDirectory() as td:
        from config.settings import settings
        old_wx = settings._config.wx_download_dir
        settings._config.wx_download_dir = str(td)  # 兜底搜索根指向临时目录
        try:
            sub = Path(td) / "作者资源" / "nested"
            sub.mkdir(parents=True)
            f = sub / "2026-10-20_标题_1080p_vid1.mp4"
            f.write_bytes(b"y" * 50)
            got = find_downloaded_file(str(Path(td) / "不存在"), f.name, "")
            _record("落盘兜底搜索: 递归命中", got == str(f))
        finally:
            settings._config.wx_download_dir = old_wx


def run_chain_checks(client, dl_dir: Path, source_mp4: Path, counter):
    def post(video_id: str):
        url = f"{BASE}/drama1/{video_id}/video.mp4"
        return client.post("/api/direct-download", json={"url": url})

    # 1. 正常下载（字节级校验）
    resp = post("video1")
    try:
        check_download_ok(resp, dl_dir, source_mp4, f"{APP_ID}_1_video1.mp4", 0)
        _record("正常下载: 大小+md5 精确一致", True, f"{source_mp4.stat().st_size}B")
    except CheckError as e:
        _record("正常下载: 大小+md5 精确一致", False, str(e))

    # 2. 重复下载 → 命中已存在，零新网络请求
    before = counter("video1")
    resp2 = post("video1")
    try:
        check_download_ok(resp2, dl_dir, source_mp4, f"{APP_ID}_1_video1.mp4", before)
        check_no_duplicate_request(counter("video1"), before, "video1")
        _record("重复下载: 命中已存在 + 零新请求", True, f"请求数保持 {before}")
    except CheckError as e:
        _record("重复下载: 命中已存在 + 零新请求", False, str(e))

    # 3. 序号 = 有效文件数 + 1（已有 video1 + 预置 2 个有效 → 新下载序号=4）
    try:
        app_dir = dl_dir / APP_ID
        app_dir.mkdir(parents=True, exist_ok=True)
        (app_dir / f"{APP_ID}_1_other.mp4").write_bytes(b"a" * 100)
        (app_dir / f"{APP_ID}_2_other.mp4").write_bytes(b"b" * 100)
        resp3 = post("video7")
        check_download_ok(resp3, dl_dir, source_mp4, f"{APP_ID}_4_video7.mp4", 0)
        _record("序号规则: 有效文件数+1", True, "已有3个有效(video1+2预置) → 新序号=4")
    except CheckError as e:
        _record("序号规则: 有效文件数+1", False, str(e))

    # 4. 0 字节损坏残留 → 删除重下（用独立 video8，避免与已下载的 video7 命中短路）
    try:
        app_dir = dl_dir / APP_ID
        residue = app_dir / f"{APP_ID}_1_video8.mp4"
        residue.write_bytes(b"")
        c_before = counter("video8")
        resp4 = post("video8")
        # 残留被删除、有效数=4(video1+2预置+video7) → 新文件 127_5_video8.mp4（字节级一致）
        check_download_ok(resp4, dl_dir, source_mp4, f"{APP_ID}_5_video8.mp4", c_before)
        assert counter("video8") == c_before + 1, "0字节场景必须重新请求下载"
        _record("0字节残留: 删除重下", True)
    except CheckError as e:
        _record("0字节残留: 删除重下", False, str(e))

    # 5. 故障路径：404 / 空内容 / 超时 / CDN 防盗链 / 302→HTML / 中途断开
    for vid, label in [("video2", "404 失效链接"), ("video3", "空内容 0 字节"),
                       ("video4", "网络超时"), ("video5", "CDN 防盗链拒绝"),
                       ("video9", "防盗链302→提示页(HTML闸门)"),
                       ("video10", "中途断开(Content-Length不符)")]:
        resp = post(vid)
        try:
            check_failure_clean(resp, dl_dir, vid)
            _record(f"故障路径: {label} → 502 无残留", True)
        except CheckError as e:
            _record(f"故障路径: {label} → 502 无残留", False, str(e))

    # 6. 非法请求
    try:
        r = client.post("/api/direct-download", json={})
        assert r.status_code == 400, f"期望400，实际{r.status_code}"
        _record("非法请求: 缺 url → 400", True)
    except (CheckError, AssertionError) as e:
        _record("非法请求: 缺 url → 400", False, str(e))


def main():
    print("=" * 60)
    print("  芯二合一下载器 · 链路自检（无需打开微信）")
    print("=" * 60)

    print("\n[1/4] 真实链路节点探测（仅报告，不判过）：")
    for label, port in NODES:
        ok = _check_port(port)
        print(f"  {'●' if ok else '○'} {label} (127.0.0.1:{port}): {'监听中' if ok else '未启动（自检不启动外部服务）'}")

    print("\n[1.5/4] 代理链实穿（经本机代理端口真实转发验证，未监听自动跳过）：")
    run_proxy_chain_probe()

    print("\n[1.6/4] 系统代理实况（读注册表，检测代理冲突）：")
    run_system_proxy_probe()

    print("\n[2/4] L0 单元规则：")
    run_unit_checks()

    print("\n[3/4] L2 严格下载链路（真实视频源 + 字节级校验）：")
    source_mp4 = ensure_test_mp4()
    mock_video_server.reset_counter()
    mock_video_server.start_server(source_mp4)
    tmp_dir = Path(tempfile.mkdtemp(prefix="selftest_"))
    from config.settings import settings
    restore = core_checks.override_settings(settings, tmp_dir, download_timeout=3.0)
    app = core_checks.build_test_app()
    try:
        with TestClient(app) as client:
            run_chain_checks(client, tmp_dir, source_mp4, mock_video_server.get_counter)
    finally:
        restore()
        mock_video_server.stop_server()

    print("\n[4/4] 汇总：")
    ok_count = sum(1 for _, ok, _ in _results if ok)
    fail_count = len(_results) - ok_count

    # —— 环境状态总结（与代码正确性分离，防"假绿"：测试绿≠环境健康）——
    env_lines = []
    if not _check_port(8899):
        env_lines.append("外部服务: res_download(8899) 未运行 → 代理链实穿段 SKIP（未验证）")
    if _check_port(2023):
        env_lines.append("Go MITM(2023) 在线（仅诊断）")
    if _check_port(2022):
        env_lines.append("Go API(2022) 在线")
    import winreg
    try:
        with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
                0, winreg.KEY_READ) as key:
            pe, _ = winreg.QueryValueEx(key, "ProxyEnable")
            ps, _ = winreg.QueryValueEx(key, "ProxyServer")
        if pe and ps != f"127.0.0.1:{8899}":
            env_lines.append(f"⚠️ 环境漂移: 系统代理={ps}（非本产品 8899）→ 短剧流量不进 8899，"
                             f"真实链路验证范围受限；需恢复后才能实穿")
        elif pe:
            env_lines.append("系统代理=8899（本产品，无冲突）")
        else:
            env_lines.append("系统代理未启用")
    except Exception as e:
        env_lines.append(f"系统代理读取失败: {e}")

    if fail_count == 0:
        print(f"  ✅ 全部通过：{ok_count}/{ok_count} 项（我方代码链路：下载→命名→防重→故障→编排契约）")
        print("  —— 环境状态（测试绿 ≠ 环境健康，真实链路范围如下）——")
        for line in env_lines:
            print(f"    {line}")
        print("\n  结论：我方代码链路健康；黑盒解密+真实签名URL成功路径需 L3 真机冒烟（发版门禁）。")
        return 0
    print(f"  ❌ 失败 {fail_count}/{len(_results)} 项，详情见上方 ❌ 行")
    return 1


if __name__ == "__main__":
    sys.exit(main())
