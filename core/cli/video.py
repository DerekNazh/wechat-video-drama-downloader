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
        all_data = svc.get_all_authors_with_videos()
        videos = []
        for item in all_data:
            for v in item["videos"]:
                if type != "all" and (v.video_type or "short_video") != type:
                    continue
                videos.append(v)

    if status == "downloaded":
        videos = [v for v in videos if v.is_downloaded == 1]
    elif status == "pending":
        videos = [v for v in videos if v.is_downloaded != 1]

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


@app.command("sync-new")
def video_sync_new(
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """增量同步所有作者的新视频（需微信在线）"""
    svc = get_video_service()
    result = svc.sync_and_get_new_videos()

    format_output(
        {"code": 0, "message": "success", "data": result},
        pretty=pretty,
    )


@app.command("add-all")
def video_add_all(
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """同步所有作者最新视频（需微信在线）"""
    svc = get_video_service()
    result = svc.add_all_authors_latest_videos()

    format_output(
        {"code": 0, "message": "success", "data": result},
        pretty=pretty,
    )


@app.command("play")
def video_play(
    id: Optional[str] = typer.Option(None, "--id", help="视频ID"),
    path: Optional[str] = typer.Option(None, "--path", help="视频文件路径"),
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """播放视频（通过ID或文件路径）"""
    if not id and not path:
        error_output("请指定 --id 或 --path")

    file_path = path
    if id and not path:
        svc = get_video_service()
        video = svc.get_video_detail(id)
        if not video:
            error_output(f"视频不存在: {id}")
        if not video.download_path:
            error_output(f"视频未下载: {id}")
        file_path = video.download_path

    if not file_path:
        error_output("无法确定视频路径")

    import subprocess
    import sys

    if sys.platform == "win32":
        subprocess.run(["start", "", file_path], shell=True)
    elif sys.platform == "darwin":
        subprocess.run(["open", file_path])
    else:
        subprocess.run(["xdg-open", file_path])

    format_output(
        {"code": 0, "message": "success", "data": {"played": file_path}},
        pretty=pretty,
    )
