"""pytest fixtures：真实视频服务器 + 独立下载 app + 隔离下载目录"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# 保证能 import 项目模块
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from fastapi.testclient import TestClient  # noqa: E402

from config.settings import settings  # noqa: E402
from tests import core_checks  # noqa: E402
from tests import mock_video_server  # noqa: E402


@pytest.fixture(scope="session")
def source_mp4():
    """真实测试视频（ffmpeg 生成一次，session 内复用）"""
    return core_checks.ensure_test_mp4()


@pytest.fixture(scope="session")
def mock_server(source_mp4):
    """真实视频源服务器（session 级，端口 19099）"""
    mock_video_server.reset_counter()
    mock_video_server.start_server(source_mp4)
    yield mock_video_server
    mock_video_server.stop_server()


@pytest.fixture()
def test_app(mock_server, tmp_path):
    """隔离下载目录 + 短超时 + 独立 app（不触发启动序列）"""
    restore = core_checks.override_settings(settings, tmp_path, download_timeout=3.0)
    app = core_checks.build_test_app()
    try:
        with TestClient(app) as client:
            yield client, tmp_path
    finally:
        restore()


@pytest.fixture()
def counter(mock_server):
    def get(video_id: str) -> int:
        return mock_video_server.get_counter(video_id)
    return get
