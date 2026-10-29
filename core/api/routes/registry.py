"""API 薄路由注册表（YZPQ-310）：5 分组映射前端 38 接口。

薄路由：这里只声明「路径 + 方法 + 处理器名 + 是否需要门禁」，真正的 HTTP
绑定由 app.py 用此表生成。后端独有旧路由在此登记下线/替换。
"""
from __future__ import annotations

# 5 分组，共 38 个前端接口：(method, path, handler, gated)
ROUTES: list[tuple[str, str, str, bool]] = [
    # 任务组 (tasks)
    ("GET", "/api/tasks", "list_tasks", False),
    ("GET", "/api/tasks/{task_id}", "get_task", False),
    ("POST", "/api/tasks", "create_task", False),
    ("POST", "/api/tasks/{task_id}/pause", "pause_task", False),
    ("POST", "/api/tasks/{task_id}/resume", "resume_task", False),
    ("POST", "/api/tasks/{task_id}/cancel", "cancel_task", False),
    ("DELETE", "/api/tasks/{task_id}", "delete_task", False),
    ("GET", "/api/tasks/logs", "task_logs", False),
    # 搜索组 (search)
    ("GET", "/api/search", "search", False),
    ("GET", "/api/search/hot", "hot_search", False),
    ("GET", "/api/suggest", "suggest", False),
    ("GET", "/api/channels/resolve", "resolve_link", False),
    # 下载组 (download)
    ("POST", "/api/download/video/{video_id}", "download_video", False),
    ("POST", "/api/download/author/{author_id}", "download_author", True),
    ("POST", "/api/download/collection/{topic_id}", "download_collection", True),
    ("GET", "/api/download/status/{task_id}", "download_status", False),
    # 作者组 (author)
    ("GET", "/api/authors", "list_authors", False),
    ("GET", "/api/authors/{author_id}", "get_author", False),
    ("DELETE", "/api/authors/{author_id}", "delete_author", False),
    ("POST", "/api/authors/{author_id}/star", "toggle_star", False),
    ("GET", "/api/authors/{author_id}/videos", "author_videos", False),
    ("GET", "/api/authors/{author_id}/collections", "author_collections", False),
    ("GET", "/api/authors/{author_id}/comments", "author_comments", False),
    ("GET", "/api/authors/{author_id}/list-snapshot", "author_snapshot", False),
    # 设置组 (settings)
    ("GET", "/api/settings", "get_settings", False),
    ("PUT", "/api/settings", "update_settings", False),
    ("GET", "/api/settings/token", "get_token", False),
    ("POST", "/api/settings/test-key", "test_key", False),
    ("GET", "/api/storage/usage", "storage_usage", False),
    ("GET", "/api/update/check", "check_update", False),
    ("POST", "/api/update/download", "download_update", False),
    ("GET", "/api/system/status", "system_status", False),
    ("GET", "/api/collections/{topic_id}", "get_collection", False),
    ("GET", "/api/videos/{video_id}", "get_video", False),
    ("GET", "/api/videos/{video_id}/comments", "video_comments", False),
    ("POST", "/api/videos/{video_id}/redownload", "redownload", False),
    ("GET", "/api/progress/author/{author_id}", "author_progress", False),
    ("POST", "/api/alias/refresh", "refresh_alias", False),
]

# 旧路由下线/替换登记
RETIRED_ROUTES = {
    "/api/wechat-status": "移除（不再探微信登录态）",
    "/api/service/*": "下线（服务端侧迁 TikHub）",
}
REPLACED_ROUTES = {
    "/api/link-status": "/api/channels/resolve (语义改 TikHub)",
    "/api/download-all": "/api/download/author/{author_id} (门禁替换)",
}

# require_wechat 门禁 → 新门禁替换（gated 字段在 ROUTES 中标 True）
WECHAT_GATE_REPLACED = 16
