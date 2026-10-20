"""L2 严格下载链路测试（direct-download 主核心，字节级校验）

覆盖的真实场景（每条都严格校验，不放水）：
1. 正常下载 → 文件大小/md5 与源精确一致 + 命名规则正确
2. 重复下载 → 命中已存在文件，服务器请求计数零增长（真的没重新下）
3. 序号 = 有效文件数 + 1（不因残留/重复膨胀）
4. 0 字节损坏残留 → 删除重下（杜绝永久假成功）
5. 404 失效链接 → 502 + 无残留
6. 空内容（0 字节响应）→ 502 + 无残留
7. 网络超时（慢速上游）→ 502 + 无残留
8. CDN 签名防盗链拒绝 → 502 + 无残留
9. 非法请求 → 400
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from tests import core_checks
from tests.core_checks import (
    check_download_ok,
    check_failure_clean,
    check_no_duplicate_request,
    list_downloaded,
)

BASE = "http://127.0.0.1:19099"
APP_ID = "127"  # 127.0.0.1 的第一段


def _dl_url(video_id: str) -> str:
    return f"{BASE}/drama1/{video_id}/video.mp4"


def _post(client, url: str, body: dict):
    return client.post("/api/direct-download", json=body)


class TestDownloadChain:
    def test_success_bytes_exact(self, test_app, source_mp4, counter):
        client, dl_dir = test_app
        resp = _post(client, _dl_url("video1"), {"url": _dl_url("video1")})
        check_download_ok(resp, dl_dir, source_mp4, f"{APP_ID}_1_video1.mp4",
                          counter_before=0)
        assert counter("video1") == 1

    def test_duplicate_hits_existing_no_new_request(self, test_app, source_mp4, counter):
        client, dl_dir = test_app
        url = _dl_url("video1")
        before = counter("video1")  # 用例开始时计数（服务器为 session 级共享）
        r1 = _post(client, url, {"url": url})
        p1 = check_download_ok(r1, dl_dir, source_mp4, f"{APP_ID}_1_video1.mp4",
                               counter_before=before)
        after_first = counter("video1")
        # 第二次：应命中已存在，且服务器请求计数不增长
        r2 = _post(client, url, {"url": url})
        p2 = check_download_ok(r2, dl_dir, source_mp4, f"{APP_ID}_1_video1.mp4",
                               counter_before=after_first)
        assert str(p1) == str(p2), "重复下载应返回同一文件路径"
        check_no_duplicate_request(counter("video1"), after_first, "video1")

    def test_seq_is_valid_count_plus_one(self, test_app, source_mp4, counter):
        client, dl_dir = test_app
        # 预置 2 个有效文件（模拟目录里已有其他短剧视频）
        app_dir = dl_dir / APP_ID
        app_dir.mkdir(parents=True)
        (app_dir / f"{APP_ID}_1_other.mp4").write_bytes(b"a" * 100)
        (app_dir / f"{APP_ID}_2_other.mp4").write_bytes(b"b" * 100)
        url = _dl_url("video1")
        resp = _post(client, url, {"url": url})
        check_download_ok(resp, dl_dir, source_mp4, f"{APP_ID}_3_video1.mp4",
                          counter_before=0)
        # 目录共 3 个有效文件，无残留
        assert len(list_downloaded(dl_dir)) == 3

    def test_zero_byte_residue_replaced(self, test_app, source_mp4, counter):
        client, dl_dir = test_app
        app_dir = dl_dir / APP_ID
        app_dir.mkdir(parents=True)
        residue = app_dir / f"{APP_ID}_1_video1.mp4"
        residue.write_bytes(b"")  # 0 字节损坏残留
        before = counter("video1")  # session 级共享计数，取用例起始值
        url = _dl_url("video1")
        resp = _post(client, url, {"url": url})
        check_download_ok(resp, dl_dir, source_mp4, f"{APP_ID}_1_video1.mp4",
                          counter_before=0)
        # 残留被删除并以有效文件替换（目录中仅 1 个文件、字节级一致）
        assert len(list_downloaded(dl_dir)) == 1, f"残留未清理: {list_downloaded(dl_dir)}"
        assert counter("video1") == before + 1, "0字节场景必须重新请求下载"

    def test_404_returns_502_no_residue(self, test_app, tmp_path, counter):
        client, dl_dir = test_app
        resp = _post(client, _dl_url("video2"), {"url": _dl_url("video2")})
        check_failure_clean(resp, dl_dir, "video2")

    def test_empty_content_returns_502(self, test_app, counter):
        client, dl_dir = test_app
        resp = _post(client, _dl_url("video3"), {"url": _dl_url("video3")})
        check_failure_clean(resp, dl_dir, "video3")

    def test_timeout_returns_502(self, test_app, counter):
        client, dl_dir = test_app
        resp = _post(client, _dl_url("video4"), {"url": _dl_url("video4")})
        check_failure_clean(resp, dl_dir, "video4")

    def test_cdn_hotlink_403_returns_502(self, test_app, counter):
        client, dl_dir = test_app
        # video5 模拟真实 CDN 签名防盗链：Referer 必须是 CDN 站点，
        # 下载器带的是自身 origin → 403 → 必须 502 且无残留
        resp = _post(client, _dl_url("video5"), {"url": _dl_url("video5")})
        check_failure_clean(resp, dl_dir, "video5")

    def test_hotlink_302_to_html_rejected(self, test_app, counter):
        """防盗链 302 → 提示页：下载器跟随重定向拿到 HTML，
        Content-Type 闸门必须拒绝（不能保存 HTML 为 .mp4 假成功）"""
        client, dl_dir = test_app
        resp = _post(client, _dl_url("video9"), {"url": _dl_url("video9")})
        check_failure_clean(resp, dl_dir, "video9")
        assert counter("video9") >= 1

    def test_truncated_download_fails_and_cleans(self, test_app, counter):
        """声明 Content-Length=100000 只发 500 字节（badhttp 风格）：
        流式下载必须失败（不能留下半截文件）"""
        client, dl_dir = test_app
        resp = _post(client, _dl_url("video10"), {"url": _dl_url("video10")})
        check_failure_clean(resp, dl_dir, "video10")


class TestBadRequest:
    def test_missing_url_returns_400(self, test_app):
        client, _ = test_app
        resp = _post(client, _dl_url("video1"), {})
        assert resp.status_code == 400

    def test_invalid_json_returns_400(self, test_app):
        client, _ = test_app
        resp = client.post("/api/direct-download", content="not-json",
                           headers={"Content-Type": "application/json"})
        assert resp.status_code == 400

    def test_empty_url_returns_400(self, test_app):
        client, _ = test_app
        resp = _post(client, _dl_url("video1"), {"url": ""})
        assert resp.status_code == 400
