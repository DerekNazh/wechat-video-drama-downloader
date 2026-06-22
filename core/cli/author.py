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
