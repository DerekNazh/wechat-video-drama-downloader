# AI-Callable CLI 命令系统实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 AI 可调用的 CLI 命令行系统，通过 `python -m core.cli <资源> <动作> [选项]` 完成视频下载器的所有操作

**Architecture:** Typer 框架 + 资源/动作二级命令结构，直接调用 Service 层，JSON 优先输出

**Tech Stack:** Python 3.13, Typer, Rich, 项目现有 Service 层 (AuthorService, VideoService, TaskService, SearchService, MonitorService, WechatVideoService)

---

## 文件结构

```
core/cli/
├── __init__.py          # Typer app 实例 + main 回调 + 子命令注册
├── __main__.py          # python -m core.cli 支持
├── author.py            # author 子命令组（6个命令）
├── video.py             # video 子命令组（6个命令）
├── task.py              # task 子命令组（4个命令）
├── service.py           # service 子命令组（9个命令，含 monitor 嵌套子组）
├── output.py            # 输出格式化工具（JSON/表格）
└── ctx.py               # 共享上下文（数据库初始化、Service 实例缓存）
```

---

### Task 1: 安装 Typer 依赖

**Files:**
- Modify: `requirements.txt`

- [ ] **Step 1: 安装 typer[all]**

Run:
```bash
cd "f:/setup_temp/剪辑合成拆散/监控/总下载器版本" && .venv/Scripts/pip install "typer[all]"
```

- [ ] **Step 2: 更新 requirements.txt**

在 `requirements.txt` 末尾添加:
```
typer[all]
```

- [ ] **Step 3: 验证安装**

Run:
```bash
cd "f:/setup_temp/剪辑合成拆散/监控/总下载器版本" && .venv/Scripts/python -c "import typer; print(typer.__version__)"
```
Expected: 输出版本号

---

### Task 2: 创建 ctx.py — 共享上下文和数据库初始化

**Files:**
- Create: `core/cli/ctx.py`

- [ ] **Step 1: 实现 ctx.py**

```python
"""CLI 共享上下文 — 数据库初始化、Service 实例缓存"""

import logging
from functools import lru_cache

logger = logging.getLogger("cli.ctx")

_initialized = False


def ensure_init():
    """确保数据库和配置已初始化（幂等）"""
    global _initialized
    if _initialized:
        return

    # 1. 初始化 settings（自动加载 .env、创建目录）
    from config.settings import settings

    # 2. 初始化数据库（触发 db 单例创建）
    from core.utils.database import db

    _initialized = True
    logger.debug("CLI 上下文初始化完成")


@lru_cache(maxsize=1)
def get_author_service():
    from core.service.author import AuthorService
    return AuthorService()


@lru_cache(maxsize=1)
def get_video_service():
    from core.service.video import VideoService
    return VideoService()


@lru_cache(maxsize=1)
def get_task_service():
    from core.service.task import TaskService
    return TaskService()


@lru_cache(maxsize=1)
def get_search_service():
    from core.service.search import SearchService
    return SearchService()


@lru_cache(maxsize=1)
def get_wechat_service():
    from core.utils.base_servier import WechatVideoService
    return WechatVideoService()


@lru_cache(maxsize=1)
def get_monitor_service():
    from core.monitor.monitor import MonitorService
    return MonitorService()
```

- [ ] **Step 2: 验证 ctx.py 可导入**

Run:
```bash
cd "f:/setup_temp/剪辑合成拆散/监控/总下载器版本" && .venv/Scripts/python -c "from core.cli.ctx import ensure_init, get_author_service; ensure_init(); print('OK')"
```
Expected: 输出 OK

- [ ] **Step 3: Commit**

```bash
git add core/cli/ctx.py
git commit -m "feat(cli): add shared context module for CLI service initialization"
```

---

### Task 3: 创建 output.py — 输出格式化工具

**Files:**
- Create: `core/cli/output.py`

- [ ] **Step 1: 实现 output.py**

```python
"""CLI 输出格式化 — JSON 默认，--pretty 切换表格"""

import json
import sys
from typing import Any

from rich.console import Console
from rich.table import Table

console = Console()


def format_output(data: Any, pretty: bool = False, table_config: dict = None):
    """统一输出格式

    Args:
        data: 要输出的数据（dict/list/其他）
        pretty: True 时输出 Rich 表格
        table_config: 表格配置 {"title": str, "columns": [{"name": str, "key": str}]}
    """
    if not pretty:
        _output_json(data)
    else:
        _output_table(data, table_config)


def _output_json(data: Any):
    """输出 JSON 到 stdout"""
    if isinstance(data, dict) and "code" not in data:
        data = {"code": 0, "message": "success", "data": data}
    try:
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
    except (TypeError, ValueError):
        print(json.dumps({"code": 0, "message": "success", "data": str(data)}, ensure_ascii=False))


def _output_table(data: Any, table_config: dict):
    """输出 Rich 表格"""
    if not table_config:
        console.print_json(json.dumps(data, ensure_ascii=False, default=str))
        return

    items = data
    if isinstance(data, dict) and "data" in data:
        items = data["data"]
    if isinstance(items, dict) and "items" in items:
        items = items["items"]

    if not isinstance(items, list):
        items = [items]

    table = Table(title=table_config.get("title", ""), show_lines=True)

    for col in table_config.get("columns", []):
        table.add_column(col["name"], style=col.get("style", ""))

    for row in items:
        if isinstance(row, dict):
            values = [str(row.get(col["key"], "")) for col in table_config["columns"]]
        else:
            values = [str(getattr(row, col["key"], "")) for col in table_config["columns"]]
        table.add_row(*values)

    console.print(table)


def error_output(message: str, code: int = 1):
    """输出错误信息"""
    result = {"code": code, "message": message, "data": None}
    print(json.dumps(result, ensure_ascii=False))
    sys.exit(code)
```

- [ ] **Step 2: 验证 output.py 可导入**

Run:
```bash
cd "f:/setup_temp/剪辑合成拆散/监控/总下载器版本" && .venv/Scripts/python -c "from core.cli.output import format_output, error_output; print('OK')"
```
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add core/cli/output.py
git commit -m "feat(cli): add output formatting module (JSON default, --pretty table)"
```

---

### Task 4: 创建 __init__.py 和 __main__.py — CLI 入口

**Files:**
- Create: `core/cli/__init__.py`
- Create: `core/cli/__main__.py`

- [ ] **Step 1: 实现 __init__.py**

```python
"""AI-Callable CLI 命令行系统

用法: python -m core.cli <资源> <动作> [选项]

资源:
  author   作者管理
  video    视频操作
  task     任务管理
  service  服务与监控
"""

import typer

from core.cli.ctx import ensure_init

app = typer.Typer(
    name="core.cli",
    help="视频下载器 CLI — AI 可调用的命令行接口",
    add_completion=False,
    no_args_is_help=True,
)


@app.callback()
def main():
    """CLI 入口回调 — 每条命令执行前初始化上下文"""
    ensure_init()


# 延迟注册子命令组（避免循环导入）
from core.cli import author, video, task, service  # noqa: E402

app.add_typer(author.app, name="author")
app.add_typer(video.app, name="video")
app.add_typer(task.app, name="task")
app.add_typer(service.app, name="service")
```

- [ ] **Step 2: 实现 __main__.py**

```python
"""支持 python -m core.cli 调用"""
from core.cli import app

if __name__ == "__main__":
    app()
```

- [ ] **Step 3: 验证 CLI 入口**

Run:
```bash
cd "f:/setup_temp/剪辑合成拆散/监控/总下载器版本" && .venv/Scripts/python -m core.cli --help
```
Expected: 输出帮助信息，包含 author/video/task/service 子命令

- [ ] **Step 4: Commit**

```bash
git add core/cli/__init__.py core/cli/__main__.py
git commit -m "feat(cli): add CLI entry point with Typer app and subcommand registration"
```

---

### Task 5: 创建 author.py — 作者管理子命令

**Files:**
- Create: `core/cli/author.py`

- [ ] **Step 1: 实现 author.py**

```python
"""author 子命令组 — 作者管理"""

from typing import Optional
import typer

from core.cli.ctx import get_author_service, get_search_service, get_video_service
from core.cli.output import format_output, error_output

app = typer.Typer(help="作者管理", no_args_is_help=True)


@app.command("list")
def author_list(
    type: str = typer.Option("all", "--type", help="筛选类型: all|short_video|live_replay"),
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """列出所有作者（含短视频/回放统计）"""
    if type not in ("all", "short_video", "live_replay"):
        error_output(f"无效类型: {type}，可选: all|short_video|live_replay")

    svc = get_author_service()
    authors = svc.get_all_authors()

    result = []
    for author in authors:
        video_svc = get_video_service()
        videos = video_svc.get_author_videos(author.id)
        short_videos = [v for v in videos if (v.video_type or "short_video") == "short_video"]
        replays = [v for v in videos if v.video_type == "live_replay"]

        if type == "short_video" and len(short_videos) == 0:
            continue
        if type == "live_replay" and len(replays) == 0:
            continue

        result.append({
            "id": author.id,
            "name": author.name,
            "username": author.source_author_id or "",
            "short_video": {
                "total": len(short_videos),
                "downloaded": sum(1 for v in short_videos if v.is_downloaded == 1),
            },
            "live_replay": {
                "total": len(replays),
                "downloaded": sum(1 for v in replays if v.is_downloaded == 1),
            },
        })

    format_output(
        {"code": 0, "message": "success", "data": result},
        pretty=pretty,
        table_config={
            "title": "作者列表",
            "columns": [
                {"name": "ID", "key": "id"},
                {"name": "名称", "key": "name"},
                {"name": "短视频", "key": "short_video"},
                {"name": "直播回放", "key": "live_replay"},
            ],
        },
    )


@app.command("get")
def author_get(
    id: str = typer.Option(..., "--id", help="作者ID"),
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """获取作者详情"""
    svc = get_author_service()
    author = svc.get_author(id)
    if not author:
        error_output(f"作者不存在: {id}")

    video_svc = get_video_service()
    videos = video_svc.get_author_videos(id)
    short_videos = [v for v in videos if (v.video_type or "short_video") == "short_video"]
    replays = [v for v in videos if v.video_type == "live_replay"]

    data = {
        "id": author.id,
        "name": author.name,
        "username": author.source_author_id or "",
        "bio": author.bio or "",
        "avatar_url": author.avatar_url or "",
        "short_video": {
            "total": len(short_videos),
            "downloaded": sum(1 for v in short_videos if v.is_downloaded == 1),
        },
        "live_replay": {
            "total": len(replays),
            "downloaded": sum(1 for v in replays if v.is_downloaded == 1),
        },
    }

    format_output({"code": 0, "message": "success", "data": data}, pretty=pretty)


@app.command("search")
def author_search(
    keyword: str = typer.Option(..., "--keyword", help="搜索关键词"),
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """搜索作者（需微信在线）"""
    svc = get_search_service()
    result = svc.search_author(keyword, exact_match=False)

    if result.get("code") != 0:
        error_output(result.get("msg", "搜索失败"))

    format_output(
        {"code": 0, "message": "success", "data": result.get("data", [])},
        pretty=pretty,
        table_config={
            "title": "搜索结果",
            "columns": [
                {"name": "用户名", "key": "username"},
                {"name": "昵称", "key": "nickname"},
                {"name": "签名", "key": "signature"},
            ],
        },
    )


@app.command("add")
def author_add(
    keyword: str = typer.Option(..., "--keyword", help="作者名（精确匹配）"),
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """添加作者（精确匹配，需微信在线）"""
    svc = get_author_service()
    result = svc.add_author(keyword)

    if result.get("code") != 0:
        error_output(result.get("msg", "添加失败"))

    author = result.get("data")
    data = {
        "id": author.id if author else None,
        "name": author.name if author else None,
        "username": author.source_author_id if author else None,
        "action": "已存在" if result.get("msg") == "作者已存在" else "新增",
    }

    format_output({"code": 0, "message": "success", "data": data}, pretty=pretty)


@app.command("sync")
def author_sync(
    id: str = typer.Option(..., "--id", help="作者ID"),
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """同步作者最新视频（需微信在线）"""
    svc = get_video_service()
    result = svc.add_author_latest_videos(id)

    format_output(
        {"code": 0, "message": "success", "data": result},
        pretty=pretty,
    )


@app.command("delete")
def author_delete(
    id: str = typer.Option(..., "--id", help="作者ID"),
    force: bool = typer.Option(False, "--force", help="跳过确认直接删除"),
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """删除作者及所有视频文件"""
    if not force:
        svc = get_author_service()
        info = svc.get_author_delete_info(id)
        if not info.get("exists"):
            error_output(f"作者不存在: {id}")

        typer.confirm(
            f"将删除作者 {id} 及 {info['total_count']} 个视频（{info['downloaded_count']} 已下载），确认？",
            abort=True,
        )

    svc = get_author_service()
    success = svc.delete_author(id)

    if not success:
        error_output(f"删除失败: {id}")

    format_output({"code": 0, "message": "success", "data": {"deleted": id}}, pretty=pretty)
```

- [ ] **Step 2: 验证 author 子命令**

Run:
```bash
cd "f:/setup_temp/剪辑合成拆散/监控/总下载器版本" && .venv/Scripts/python -m core.cli author --help
```
Expected: 显示 list/get/search/add/sync/delete 子命令

- [ ] **Step 3: Commit**

```bash
git add core/cli/author.py
git commit -m "feat(cli): add author subcommand group (list/get/search/add/sync/delete)"
```

---

### Task 6: 创建 video.py — 视频操作子命令

**Files:**
- Create: `core/cli/video.py`

- [ ] **Step 1: 实现 video.py**

```python
"""video 子命令组 — 视频操作"""

from typing import Optional
import typer

from core.cli.ctx import get_video_service, get_task_service
from core.cli.output import format_output, error_output

app = typer.Typer(help="视频操作", no_args_is_help=True)


@app.command("list")
def video_list(
    author_id: Optional[str] = typer.Option(None, "--author-id", help="作者ID"),
    type: str = typer.Option("all", "--type", help="类型: all|short_video|live_replay"),
    status: Optional[str] = typer.Option(None, "--status", help="状态: downloaded|pending"),
    page: int = typer.Option(1, "--page", help="页码"),
    page_size: int = typer.Option(20, "--page-size", help="每页数量"),
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """列出视频"""
    if type not in ("all", "short_video", "live_replay"):
        error_output(f"无效类型: {type}")
    if status and status not in ("downloaded", "pending"):
        error_output(f"无效状态: {status}")

    svc = get_video_service()

    if author_id:
        if type == "all":
            videos = svc.get_author_videos(author_id)
        else:
            videos = svc.get_author_videos_by_type(author_id, type)
    else:
        # 无作者ID时返回所有作者的视频
        all_data = svc.get_all_authors_with_videos()
        videos = []
        for item in all_data:
            for v in item["videos"]:
                if type != "all" and (v.video_type or "short_video") != type:
                    continue
                videos.append(v)

    # 状态过滤
    if status == "downloaded":
        videos = [v for v in videos if v.is_downloaded == 1]
    elif status == "pending":
        videos = [v for v in videos if v.is_downloaded != 1]

    # 分页
    total = len(videos)
    start = (page - 1) * page_size
    end = start + page_size
    page_videos = videos[start:end]

    items = []
    for v in page_videos:
        items.append({
            "id": v.video_id,
            "title": v.title,
            "video_type": v.video_type or "short_video",
            "downloaded": v.is_downloaded == 1,
            "file_size": v.file_size,
            "duration": v.duration,
            "create_time": v.create_time,
            "download_path": v.download_path or "",
        })

    format_output(
        {
            "code": 0,
            "message": "success",
            "data": {"items": items, "total": total, "page": page, "page_size": page_size},
        },
        pretty=pretty,
        table_config={
            "title": "视频列表",
            "columns": [
                {"name": "ID", "key": "id"},
                {"name": "标题", "key": "title"},
                {"name": "类型", "key": "video_type"},
                {"name": "已下载", "key": "downloaded"},
                {"name": "大小", "key": "file_size"},
            ],
        },
    )


@app.command("get")
def video_get(
    id: str = typer.Option(..., "--id", help="视频ID"),
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """获取视频详情"""
    svc = get_video_service()
    video = svc.get_video_detail(id)
    if not video:
        error_output(f"视频不存在: {id}")

    data = {
        "id": video.video_id,
        "title": video.title,
        "video_type": video.video_type or "short_video",
        "downloaded": video.is_downloaded == 1,
        "file_size": video.file_size,
        "duration": video.duration,
        "cover_url": video.cover_url or "",
        "create_time": video.create_time,
        "download_path": video.download_path or "",
        "author_id": video.author_id,
    }

    format_output({"code": 0, "message": "success", "data": data}, pretty=pretty)


@app.command("download")
def video_download(
    ids: str = typer.Option(..., "--ids", help="视频ID，逗号分隔"),
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """下载指定视频"""
    video_ids = [vid.strip() for vid in ids.split(",") if vid.strip()]
    if not video_ids:
        error_output("未提供视频ID")

    svc = get_task_service()
    results = []
    for vid in video_ids:
        result = svc.create_download_task(vid)
        results.append({
            "video_id": vid,
            "success": result.get("code") == 0,
            "task_id": result.get("data", {}).get("id", ""),
            "message": result.get("msg", ""),
        })

    success_count = sum(1 for r in results if r["success"])
    format_output(
        {
            "code": 0,
            "message": f"已创建 {success_count}/{len(video_ids)} 个下载任务",
            "data": results,
        },
        pretty=pretty,
    )


@app.command("download-all")
def video_download_all(
    type: str = typer.Option("all", "--type", help="类型: all|short_video|live_replay"),
    author_id: Optional[str] = typer.Option(None, "--author-id", help="作者ID（不指定则全部作者）"),
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """下载所有待下载视频"""
    if type not in ("all", "short_video", "live_replay"):
        error_output(f"无效类型: {type}")

    video_svc = get_video_service()
    task_svc = get_task_service()

    # 收集待下载视频
    if author_id:
        if type == "all":
            videos = video_svc.get_author_videos(author_id)
        else:
            videos = video_svc.get_author_videos_by_type(author_id, type)
    else:
        all_data = video_svc.get_all_authors_with_videos()
        videos = []
        for item in all_data:
            for v in item["videos"]:
                if type != "all" and (v.video_type or "short_video") != type:
                    continue
                videos.append(v)

    pending = [v for v in videos if v.is_downloaded != 1]
    if not pending:
        format_output({"code": 0, "message": "没有待下载视频", "data": {"count": 0}}, pretty=pretty)
        return

    # 批量创建下载任务
    results = []
    for v in pending:
        result = task_svc.create_download_task(v.video_id)
        results.append({
            "video_id": v.video_id,
            "success": result.get("code") == 0,
            "task_id": result.get("data", {}).get("id", ""),
        })

    success_count = sum(1 for r in results if r["success"])
    format_output(
        {
            "code": 0,
            "message": f"已创建 {success_count}/{len(pending)} 个下载任务",
            "data": {"total_pending": len(pending), "created": success_count, "tasks": results},
        },
        pretty=pretty,
    )


@app.command("delete")
def video_delete(
    ids: str = typer.Option(..., "--ids", help="视频ID，逗号分隔"),
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """删除视频"""
    video_ids = [vid.strip() for vid in ids.split(",") if vid.strip()]
    if not video_ids:
        error_output("未提供视频ID")

    svc = get_video_service()
    result = svc.delete_videos(video_ids)

    format_output(
        {"code": 0, "message": "success", "data": result},
        pretty=pretty,
    )


@app.command("stats")
def video_stats(
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """全局视频统计（按类型/状态）"""
    svc = get_video_service()
    all_data = svc.get_all_authors_with_videos()

    total = 0
    downloaded = 0
    short_total = 0
    short_downloaded = 0
    replay_total = 0
    replay_downloaded = 0

    for item in all_data:
        for v in item["videos"]:
            total += 1
            if v.is_downloaded == 1:
                downloaded += 1
            vtype = v.video_type or "short_video"
            if vtype == "short_video":
                short_total += 1
                if v.is_downloaded == 1:
                    short_downloaded += 1
            elif vtype == "live_replay":
                replay_total += 1
                if v.is_downloaded == 1:
                    replay_downloaded += 1

    data = {
        "total": total,
        "downloaded": downloaded,
        "pending": total - downloaded,
        "short_video": {"total": short_total, "downloaded": short_downloaded},
        "live_replay": {"total": replay_total, "downloaded": replay_downloaded},
    }

    format_output({"code": 0, "message": "success", "data": data}, pretty=pretty)
```

- [ ] **Step 2: 验证 video 子命令**

Run:
```bash
cd "f:/setup_temp/剪辑合成拆散/监控/总下载器版本" && .venv/Scripts/python -m core.cli video --help
```
Expected: 显示 list/get/download/download-all/delete/stats 子命令

- [ ] **Step 3: Commit**

```bash
git add core/cli/video.py
git commit -m "feat(cli): add video subcommand group (list/get/download/download-all/delete/stats)"
```

---

### Task 7: 创建 task.py — 任务管理子命令

**Files:**
- Create: `core/cli/task.py`

- [ ] **Step 1: 实现 task.py**

```python
"""task 子命令组 — 任务管理"""

from typing import Optional
import typer

from core.cli.ctx import get_task_service
from core.cli.output import format_output, error_output

app = typer.Typer(help="任务管理", no_args_is_help=True)


@app.command("list")
def task_list(
    status: Optional[str] = typer.Option(None, "--status", help="状态: running|pending|completed|failed"),
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """列出下载任务"""
    svc = get_task_service()

    if status in ("running", "pending"):
        tasks = svc.get_downloading_tasks()
        if status == "pending":
            tasks = [t for t in tasks if t.get("status") == "pending"]
        elif status == "running":
            tasks = [t for t in tasks if t.get("status") == "running"]
    else:
        from core.utils.database import db
        all_tasks = db.list_download_tasks(status=status)
        tasks = []
        for t in all_tasks:
            tasks.append({
                "task_id": t.task_id,
                "video_id": t.video_id,
                "title": t.title,
                "status": t.status,
                "progress": t.progress,
                "downloaded": t.downloaded,
                "total_size": t.total_size,
                "speed": t.speed,
                "error_msg": t.error_msg or "",
                "created_at": t.created_at,
            })

    format_output(
        {"code": 0, "message": "success", "data": tasks},
        pretty=pretty,
        table_config={
            "title": "下载任务",
            "columns": [
                {"name": "任务ID", "key": "task_id"},
                {"name": "标题", "key": "title"},
                {"name": "状态", "key": "status"},
                {"name": "进度%", "key": "progress"},
                {"name": "速度", "key": "speed"},
            ],
        },
    )


@app.command("cancel")
def task_cancel(
    id: str = typer.Option(..., "--id", help="任务ID"),
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """取消任务"""
    svc = get_task_service()
    success = svc.delete_task(id)

    if not success:
        error_output(f"取消失败: {id}")

    format_output(
        {"code": 0, "message": "success", "data": {"cancelled": id}},
        pretty=pretty,
    )


@app.command("cancel-all")
def task_cancel_all(
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """取消所有任务"""
    svc = get_task_service()
    tasks = svc.get_downloading_tasks()

    cancelled = 0
    failed = 0
    for task in tasks:
        if svc.delete_task(task["task_id"]):
            cancelled += 1
        else:
            failed += 1

    format_output(
        {"code": 0, "message": "success", "data": {"cancelled": cancelled, "failed": failed}},
        pretty=pretty,
    )


@app.command("progress")
def task_progress(
    id: str = typer.Option(..., "--id", help="任务ID"),
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """查看任务进度"""
    svc = get_task_service()
    result = svc.get_task_progress(id)

    if not result:
        error_output(f"任务不存在: {id}")

    format_output(
        {"code": 0, "message": "success", "data": result},
        pretty=pretty,
    )
```

- [ ] **Step 2: 验证 task 子命令**

Run:
```bash
cd "f:/setup_temp/剪辑合成拆散/监控/总下载器版本" && .venv/Scripts/python -m core.cli task --help
```
Expected: 显示 list/cancel/cancel-all/progress 子命令

- [ ] **Step 3: Commit**

```bash
git add core/cli/task.py
git commit -m "feat(cli): add task subcommand group (list/cancel/cancel-all/progress)"
```

---

### Task 8: 创建 service.py — 服务与监控子命令

**Files:**
- Create: `core/cli/service.py`

- [ ] **Step 1: 实现 service.py**

```python
"""service 子命令组 — 服务与监控"""

from typing import Optional
import typer

from core.cli.ctx import get_wechat_service, get_monitor_service
from core.cli.output import format_output, error_output

app = typer.Typer(help="服务与监控", no_args_is_help=True)
monitor_app = typer.Typer(help="监控控制", no_args_is_help=True)


@app.command("status")
def service_status(
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """查看 Go 后端 + 微信连接状态"""
    wechat_svc = get_wechat_service()
    go_running = wechat_svc.is_running()

    wechat_connected = False
    if go_running:
        try:
            import requests
            resp = requests.get("http://127.0.0.1:2022/api/channels/contact/search", timeout=3)
            wechat_connected = resp.json().get("code") == 0
        except Exception:
            wechat_connected = False

    from core.monitor.monitor import is_monitor_active
    monitor_running = is_monitor_active()

    from core.utils.database import db
    active_tasks = len(db.list_download_tasks(status="running"))
    today_downloaded = db.count_downloaded_today()
    total_videos = db.count_videos_total()

    data = {
        "go_backend_running": go_running,
        "wechat_connected": wechat_connected,
        "monitor_running": monitor_running,
        "active_tasks": active_tasks,
        "today_downloaded": today_downloaded,
        "total_videos": total_videos,
    }

    format_output({"code": 0, "message": "success", "data": data}, pretty=pretty)


@app.command("start")
def service_start(
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """启动 Go 后端"""
    svc = get_wechat_service()
    success = svc.start(wait_seconds=15)

    if not success:
        error_output("Go 后端启动失败")

    format_output({"code": 0, "message": "success", "data": {"started": True}}, pretty=pretty)


@app.command("stop")
def service_stop(
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """停止 Go 后端"""
    svc = get_wechat_service()
    success = svc.stop()

    if not success:
        error_output("Go 后端停止失败")

    format_output({"code": 0, "message": "success", "data": {"stopped": True}}, pretty=pretty)


@app.command("restart")
def service_restart(
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """重启 Go 后端"""
    svc = get_wechat_service()
    success = svc.restart()

    if not success:
        error_output("Go 后端重启失败")

    format_output({"code": 0, "message": "success", "data": {"restarted": True}}, pretty=pretty)


@app.command("config")
def service_config(
    key: Optional[str] = typer.Option(None, "--key", help="配置项名称"),
    value: Optional[str] = typer.Option(None, "--value", help="配置值"),
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """查看或修改配置"""
    from config.settings import settings

    if not key:
        # 显示所有配置
        data = {
            "project_version": settings.project_version,
            "log_level": settings.log_level,
            "wx_status_interval": settings.wx_status_interval,
            "wx_download_dir": str(settings.wx_download_dir),
            "max_concurrent": settings.max_concurrent,
        }
        format_output({"code": 0, "message": "success", "data": data}, pretty=pretty)
        return

    # 读取配置
    config_map = {
        "log_level": "log_level",
        "wx_status_interval": "wx_status_interval",
        "wx_download_dir": "wx_download_dir",
        "max_concurrent": "max_concurrent",
    }

    attr_name = config_map.get(key)
    if not attr_name:
        error_output(f"未知配置项: {key}，可选: {', '.join(config_map.keys())}")

    if value is None:
        # 读取
        current = getattr(settings, attr_name)
        format_output({"code": 0, "message": "success", "data": {key: str(current)}}, pretty=pretty)
    else:
        # 写入
        if attr_name == "max_concurrent":
            try:
                settings.max_concurrent = int(value)
            except ValueError:
                error_output(f"无效数值: {value}")
        else:
            error_output(f"配置项 {key} 暂不支持通过 CLI 修改")

        format_output({"code": 0, "message": "success", "data": {key: value, "updated": True}}, pretty=pretty)


@app.command("logs")
def service_logs(
    lines: int = typer.Option(50, "--lines", help="显示最近N行日志"),
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """查看最近日志"""
    from config.settings import settings
    from pathlib import Path

    log_dir = settings.log_dir
    if not log_dir.exists():
        format_output({"code": 0, "message": "日志目录不存在", "data": []}, pretty=pretty)
        return

    # 找最新的日志文件
    log_files = sorted(log_dir.glob("*.log"), key=lambda f: f.stat().st_mtime, reverse=True)
    if not log_files:
        format_output({"code": 0, "message": "无日志文件", "data": []}, pretty=pretty)
        return

    try:
        all_lines = log_files[0].read_text(encoding="utf-8", errors="replace").splitlines()
        recent = all_lines[-lines:] if len(all_lines) > lines else all_lines
        format_output({"code": 0, "message": "success", "data": recent}, pretty=pretty)
    except Exception as e:
        error_output(f"读取日志失败: {e}")


# ========== monitor 嵌套子命令 ==========

@monitor_app.command("start")
def monitor_start(
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """启动监控"""
    from core.api.routers.monitor import start_monitor
    result = start_monitor()

    if result.get("code") != 0:
        error_output(result.get("message", "启动失败"))

    format_output({"code": 0, "message": "监控已启动", "data": {"running": True}}, pretty=pretty)


@monitor_app.command("stop")
def monitor_stop(
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """停止监控"""
    from core.api.routers.monitor import stop_monitor
    result = stop_monitor()

    if result.get("code") != 0:
        error_output(result.get("message", "停止失败"))

    format_output({"code": 0, "message": "监控已停止", "data": {"running": False}}, pretty=pretty)


@monitor_app.command("status")
def monitor_status(
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """监控状态"""
    from core.monitor.monitor import is_monitor_active

    running = is_monitor_active()
    format_output({"code": 0, "message": "success", "data": {"running": running}}, pretty=pretty)


# 注册嵌套子命令组
app.add_typer(monitor_app, name="monitor")
```

- [ ] **Step 2: 验证 service 子命令**

Run:
```bash
cd "f:/setup_temp/剪辑合成拆散/监控/总下载器版本" && .venv/Scripts/python -m core.cli service --help
```
Expected: 显示 status/start/stop/restart/config/logs/monitor 子命令

- [ ] **Step 3: 验证 monitor 嵌套子命令**

Run:
```bash
cd "f:/setup_temp/剪辑合成拆散/监控/总下载器版本" && .venv/Scripts/python -m core.cli service monitor --help
```
Expected: 显示 start/stop/status 子命令

- [ ] **Step 4: Commit**

```bash
git add core/cli/service.py
git commit -m "feat(cli): add service subcommand group (status/start/stop/restart/config/logs/monitor)"
```

---

### Task 9: 端到端验证

**Files:** 无新文件

- [ ] **Step 1: 验证完整 CLI 帮助**

Run:
```bash
cd "f:/setup_temp/剪辑合成拆散/监控/总下载器版本" && .venv/Scripts/python -m core.cli --help
```
Expected: 显示 author/video/task/service 四个子命令组

- [ ] **Step 2: 验证 author list（JSON 输出）**

Run:
```bash
cd "f:/setup_temp/剪辑合成拆散/监控/总下载器版本" && .venv/Scripts/python -m core.cli author list
```
Expected: JSON 格式输出作者列表，包含 short_video/live_replay 统计

- [ ] **Step 3: 验证 video stats**

Run:
```bash
cd "f:/setup_temp/剪辑合成拆散/监控/总下载器版本" && .venv/Scripts/python -m core.cli video stats
```
Expected: JSON 格式输出全局视频统计

- [ ] **Step 4: 验证 service status**

Run:
```bash
cd "f:/setup_temp/剪辑合成拆散/监控/总下载器版本" && .venv/Scripts/python -m core.cli service status
```
Expected: JSON 格式输出服务状态

- [ ] **Step 5: 验证 --pretty 表格输出**

Run:
```bash
cd "f:/setup_temp/剪辑合成拆散/监控/总下载器版本" && .venv/Scripts/python -m core.cli author list --pretty
```
Expected: Rich 表格格式输出

- [ ] **Step 6: 验证 --type 筛选**

Run:
```bash
cd "f:/setup_temp/剪辑合成拆散/监控/总下载器版本" && .venv/Scripts/python -m core.cli author list --type live_replay
```
Expected: 只包含有直播回放的作者

---

### Task 10: 修复 monitor 子命令导入问题

**Files:**
- Modify: `core/cli/service.py` (可能需要调整 monitor 的导入方式)

- [ ] **Step 1: 检查 monitor 路由模块的函数签名**

Run:
```bash
cd "f:/setup_temp/剪辑合成拆散/监控/总下载器版本" && .venv/Scripts/python -c "from core.api.routers.monitor import start_monitor, stop_monitor; print('OK')"
```
Expected: 如果导入失败，需要调整 service.py 中 monitor 命令的实现方式

如果导入失败，改为直接调用 MonitorService：

```python
@monitor_app.command("start")
def monitor_start(pretty: bool = typer.Option(False, "--pretty", help="表格输出")):
    """启动监控"""
    from core.monitor.monitor import MonitorService, _monitor_running, _monitor_lock
    import threading

    with _monitor_lock:
        if _monitor_running:
            format_output({"code": 0, "message": "监控已在运行", "data": {"running": True}}, pretty=pretty)
            return

    svc = MonitorService()
    # 启动监控线程（参考 core/api/routers/monitor.py 的实现）
    try:
        svc.start()
        format_output({"code": 0, "message": "监控已启动", "data": {"running": True}}, pretty=pretty)
    except Exception as e:
        error_output(f"启动失败: {e}")
```

- [ ] **Step 2: 验证 monitor start/stop/status 命令**

Run:
```bash
cd "f:/setup_temp/剪辑合成拆散/监控/总下载器版本" && .venv/Scripts/python -m core.cli service monitor status
```
Expected: JSON 输出 `{"running": false}` 或 `{"running": true}`

- [ ] **Step 3: Commit**

```bash
git add core/cli/service.py
git commit -m "fix(cli): adjust monitor subcommand to use MonitorService directly"
```