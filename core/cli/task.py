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
