"""测试 resume_download_task 中 URL 过期刷新逻辑"""
import pytest
from unittest.mock import patch, MagicMock

from core.utils.database import Author, AuthorVideo, DownloadTask, Database


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def db():
    """内存数据库实例"""
    database = Database(":memory:")
    yield database


@pytest.fixture
def sample_author():
    """作者测试数据"""
    return Author(
        id="author_001",
        source_author_id="test_username_001",
        name="测试作者",
        tag="测试标签",
        bio="这是测试简介",
        avatar_url="https://example.com/avatar.jpg",
        cover_img_url="https://example.com/cover.jpg",
        created_at="2026-04-23T10:00:00",
        updated_at="2026-04-23T10:00:00",
    )


@pytest.fixture
def sample_video():
    """视频测试数据"""
    return AuthorVideo(
        video_id="video_001",
        author_id="author_001",
        title="测试视频标题",
        object_nonce_id="nonce_001",
        url="https://example.com/video.mp4?token=old_token",
        spec="1080p",
        file_size=1024000,
        cover_url="https://example.com/cover.jpg",
        decode_key=12345,
        author_avatar="https://example.com/avatar.jpg",
        duration=180,
        create_time="2026-04-23T10:00:00",
        is_downloaded=0,
        download_path="",
        downloaded_at=None,
    )


@pytest.fixture
def sample_task():
    """任务测试数据"""
    return DownloadTask(
        task_id="task_001",
        video_id="video_001",
        url="https://example.com/video.mp4?token=old_token",
        title="测试任务",
        filename="test_video",
        spec="1080p",
        suffix=".mp4",
        key=12345,
        status="pending",
        progress=0,
        downloaded=0,
        total_size=1024000,
        speed=0,
        error_msg="",
        created_at="2026-04-23T10:00:00",
        updated_at="2026-04-23T10:00:00",
        completed_at=None,
        video_type="short_video",
        create_time="2026-04-23T10:00:00",
    )


# ============================================================
# Tests
# ============================================================

class TestResumeUrlRefresh:
    """resume_download_task 中 URL 过期刷新测试"""

    def test_resume_calls_ensure_valid_url(self, db, sample_author, sample_video, sample_task):
        """resume_download_task 应调用 ensure_valid_url 检查 URL 有效性"""
        # Setup: 写入作者、视频、任务到数据库
        db.create_author(sample_author)
        db.create_author_video(sample_video)
        db.create_download_task(sample_task)

        with patch("core.service.task.db", db), \
             patch("core.service.task.WechatVideoAPIClient") as mock_client_cls, \
             patch("core.service.task.SearchService") as mock_search_cls:
            # Mock WechatVideoAPIClient.download_video 返回成功
            mock_client = MagicMock()
            mock_client.download_video.return_value = {
                "code": 0,
                "data": {"id": "task_001"},
            }
            mock_client_cls.return_value = mock_client

            # Mock SearchService.ensure_valid_url 返回 URL 有效
            mock_search = MagicMock()
            mock_search.ensure_valid_url.return_value = {
                "code": 0,
                "data": {"url": sample_task.url, "refreshed": False},
                "msg": "URL 有效",
            }
            mock_search_cls.return_value = mock_search

            # 调用
            from core.service.task import resume_download_task
            result = resume_download_task("task_001")

            # 断言: ensure_valid_url 被调用
            assert result is True
            mock_search.ensure_valid_url.assert_called_once()
            call_kwargs = mock_search.ensure_valid_url.call_args
            assert call_kwargs.kwargs["url"] == sample_task.url
            assert call_kwargs.kwargs["source_author_id"] == sample_author.source_author_id
            assert call_kwargs.kwargs["video_id"] == sample_task.video_id
            assert call_kwargs.kwargs["video_type"] == "short_video"

    def test_resume_url_refresh_failed_returns_false(self, db, sample_author, sample_video, sample_task):
        """当 URL 刷新失败时，resume_download_task 应返回 False"""
        # Setup
        db.create_author(sample_author)
        db.create_author_video(sample_video)
        db.create_download_task(sample_task)

        with patch("core.service.task.db", db), \
             patch("core.service.task.WechatVideoAPIClient") as mock_client_cls, \
             patch("core.service.task.SearchService") as mock_search_cls:
            mock_client = MagicMock()
            mock_client_cls.return_value = mock_client

            # Mock ensure_valid_url 返回刷新失败
            mock_search = MagicMock()
            mock_search.ensure_valid_url.return_value = {
                "code": -1,
                "msg": "URL 过期且刷新失败: HTTP 403",
            }
            mock_search_cls.return_value = mock_search

            # 调用
            from core.service.task import resume_download_task
            result = resume_download_task("task_001")

            # 断言: 返回 False，且 download_video 不应被调用
            assert result is False
            mock_client.download_video.assert_not_called()

    def test_resume_uses_refreshed_url(self, db, sample_author, sample_video, sample_task):
        """URL 刷新后，应使用新 URL 调用 download_video"""
        # Setup
        db.create_author(sample_author)
        db.create_author_video(sample_video)
        db.create_download_task(sample_task)

        refreshed_url = "https://example.com/video.mp4?token=new_token"

        with patch("core.service.task.db", db), \
             patch("core.service.task.WechatVideoAPIClient") as mock_client_cls, \
             patch("core.service.task.SearchService") as mock_search_cls:
            # Mock WechatVideoAPIClient.download_video 返回成功
            mock_client = MagicMock()
            mock_client.download_video.return_value = {
                "code": 0,
                "data": {"id": "task_001"},
            }
            mock_client_cls.return_value = mock_client

            # Mock ensure_valid_url 返回 URL 已刷新
            mock_search = MagicMock()
            mock_search.ensure_valid_url.return_value = {
                "code": 0,
                "data": {"url": refreshed_url, "refreshed": True},
                "msg": "URL 已刷新",
            }
            mock_search_cls.return_value = mock_search

            # 调用
            from core.service.task import resume_download_task
            result = resume_download_task("task_001")

            # 断言: download_video 使用刷新后的 URL
            assert result is True
            mock_client.download_video.assert_called_once()
            call_kwargs = mock_client.download_video.call_args
            assert call_kwargs.kwargs["url"] == refreshed_url
            # 确保不是旧 URL
            assert call_kwargs.kwargs["url"] != sample_task.url