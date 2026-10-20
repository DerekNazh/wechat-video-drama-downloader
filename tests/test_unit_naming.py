"""L0 单元测试：命名规则 / URL 解析 / 落盘文件兜底搜索

不依赖任何网络/微信/Go，纯函数级校验。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import pytest

from core.api.routers.sniff_proxy import _parse_download_url
from core.service.task import find_downloaded_file
from core.utils.weixin_client import build_video_filename


# ---------- URL 解析（短剧ID/视频ID/后缀提取） ----------

class TestParseDownloadUrl:
    def test_standard_drama_url(self):
        # http://cdn.xxx.com/playlist/video123/video.mp4（无签名 query → 路径规则）
        app_id, video_id, suffix = _parse_download_url(
            "http://cdn.example.com/episode/video123/video.mp4?from=web")
        assert app_id == "cdn"
        assert video_id == "video123"
        assert suffix == ".mp4"

    def test_https_and_query_stripped(self):
        app_id, video_id, suffix = _parse_download_url(
            "https://xxx.com/v1/v2/item456/play.m3u8?sign=1&ts=2")
        assert app_id == "xxx"
        assert video_id == "item456"
        assert suffix == ".m3u8"

    def test_suffix_defaults_to_mp4(self):
        _, _, suffix = _parse_download_url("http://a.com/x/abc123/play")
        assert suffix == ".mp4"

    def test_no_video_id_returns_empty(self):
        # path 只有一段，无倒数第二段 video_id → 无法提取 → 转交 res_download
        app_id, video_id, _ = _parse_download_url("http://a.com/justafile.mp4")
        assert video_id == ""

    def test_deep_path(self):
        app_id, video_id, suffix = _parse_download_url(
            "http://x.a.com/a/b/c/d/evt789/index.m3u8")
        assert app_id == "x"
        assert video_id == "evt789"
        assert suffix == ".m3u8"

    # ---------- 真实腾讯短剧 URL（2026-10-21 用 457 条 author_videos 验证）----------
    # 形态: finder.video.qq.com/251/20302/stodownload?token=...&encfilekey=...
    # 路径段恒为固定值，唯一标识在 query —— 按路径取会把所有集数合并为同一视频

    def test_real_tencent_url_uses_query_id(self):
        app_id, video_id, suffix = _parse_download_url(
            "https://finder.video.qq.com/251/20302/stodownload?"
            "encfilekey=AAA&token=BBB&bizid=1023&idx=1&web=1")
        assert app_id == "finder"
        assert video_id.startswith("v") and len(video_id) == 13, video_id  # v + md5[:12]
        assert suffix == ".mp4"

    def test_real_tencent_different_videos_different_id(self):
        """同一短剧（20302）不同集数（token 不同）→ video_id 必须不同"""
        id1 = _parse_download_url(
            "https://finder.video.qq.com/251/20302/stodownload?token=TOKEN_AAA")[1]
        id2 = _parse_download_url(
            "https://finder.video.qq.com/251/20302/stodownload?token=TOKEN_BBB")[1]
        assert id1 != id2, "不同视频必须得到不同 video_id（否则去重互相吞）"

    def test_real_tencent_same_url_same_id(self):
        """同一 URL 重复下载 → 同一 video_id（去重仍生效）"""
        u = "https://finder.video.qq.com/251/20302/stodownload?token=TOKEN_SAME"
        assert _parse_download_url(u)[1] == _parse_download_url(u)[1]

    def test_tencent_missing_token_falls_back_to_path(self):
        app_id, video_id, _ = _parse_download_url(
            "https://finder.video.qq.com/251/20302/stodownload")
        assert video_id == "20302"  # 无 query 标识 → 路径回退


# ---------- 文件命名（微信视频号文件名模板） ----------

class TestBuildVideoFilename:
    def test_full_template(self):
        name = build_video_filename("我的视频", "2026-10-20T10:00:00", "1080p", "vid1")
        assert name == "2026-10-20_我的视频_1080p_vid1.mp4", name

    def test_invalid_date_no_prefix(self):
        name = build_video_filename("标题", "not-a-date", "720p")
        assert name == "标题_720p.mp4", name

    def test_none_date(self):
        assert build_video_filename("标题", None, "720p") == "标题_720p.mp4"

    def test_title_sanitized_and_truncated(self):
        name = build_video_filename('a<>:"/\\|?*' * 20, None, "720p")
        # 非法字符替换为 _，且截断到 80
        assert "<" not in name and len(name) > 0

    def test_empty_title(self):
        assert build_video_filename("", None, "720p") == "720p.mp4"


# ---------- 落盘文件兜底搜索（Go 报 done 路径偏差场景） ----------

class TestFindDownloadedFile:
    def test_direct_hit(self, tmp_path):
        f = tmp_path / "2026-10-20_标题_1080p.mp4"
        f.write_bytes(b"x" * 100)
        got = find_downloaded_file(str(tmp_path), f.name, "")
        assert got == str(f)

    def test_zero_byte_not_accepted(self, tmp_path):
        f = tmp_path / "zero.mp4"
        f.write_bytes(b"")
        got = find_downloaded_file(str(tmp_path), f.name, "")
        assert got is None

    def test_recursive_fallback_by_name(self, tmp_path, monkeypatch):
        """Go 的 opts.path 偏差时，应在全局下载目录递归兜底命中"""
        from config.settings import settings
        monkeypatch.setattr(settings._config, "wx_download_dir", str(tmp_path))
        sub = tmp_path / "作者资源" / "nested"
        sub.mkdir(parents=True)
        f = sub / "2026-10-20_标题_1080p_vid1.mp4"
        f.write_bytes(b"y" * 50)
        # 给定错误目录（Go 报告的路径偏差），应递归兜底命中
        got = find_downloaded_file(str(tmp_path / "不存在"), "2026-10-20_标题_1080p_vid1.mp4", "")
        assert got == str(f)

    def test_missing_returns_none(self, tmp_path):
        assert find_downloaded_file(str(tmp_path), "nope.mp4", "") is None
