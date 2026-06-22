"""service 子命令组 — 服务与监控"""

from typing import Optional
import typer

from core.cli.ctx import get_wechat_service, get_monitor_service
from core.cli.output import format_output, error_output

app = typer.Typer(help="服务与监控", no_args_is_help=True)
monitor_app = typer.Typer(help="监控控制", no_args_is_help=True)
doc_sync_app = typer.Typer(help="腾讯文档同步", no_args_is_help=True)


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


@app.command("wechat-status")
def service_wechat_status(
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """独立检查微信连接状态"""
    try:
        import requests
        resp = requests.get("http://127.0.0.1:2022/api/channels/contact/search", timeout=5)
        connected = resp.json().get("code") == 0
        format_output(
            {"code": 0, "message": "success", "data": {"wechat_connected": connected}},
            pretty=pretty,
        )
    except Exception as e:
        format_output(
            {"code": 1, "message": f"检查失败: {e}", "data": {"wechat_connected": False}},
            pretty=pretty,
        )


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
        data = {
            "project_version": settings.project_version,
            "log_level": settings.log_level,
            "wx_status_interval": settings.wx_status_interval,
            "wx_download_dir": str(settings.wx_download_dir),
            "max_concurrent": settings.max_concurrent,
            "doc_sync_interval": settings.doc_sync_interval,
        }
        format_output({"code": 0, "message": "success", "data": data}, pretty=pretty)
        return

    config_map = {
        "log_level": "log_level",
        "wx_status_interval": "wx_status_interval",
        "wx_download_dir": "wx_download_dir",
        "max_concurrent": "max_concurrent",
        "doc_sync_interval": "doc_sync_interval",
    }

    attr_name = config_map.get(key)
    if not attr_name:
        error_output(f"未知配置项: {key}，可选: {', '.join(config_map.keys())}")

    if value is None:
        current = getattr(settings, attr_name)
        format_output({"code": 0, "message": "success", "data": {key: str(current)}}, pretty=pretty)
    else:
        if attr_name == "max_concurrent":
            try:
                settings.max_concurrent = int(value)
            except ValueError:
                error_output(f"无效数值: {value}")
        elif attr_name == "doc_sync_interval":
            try:
                settings.doc_sync_interval = int(value)
            except ValueError:
                error_output(f"无效数值: {value}")
        elif attr_name == "wx_status_interval":
            try:
                settings.wx_status_interval = int(value)
            except ValueError:
                error_output(f"无效数值: {value}")
        elif attr_name == "log_level":
            settings.log_level = value
        elif attr_name == "wx_download_dir":
            settings.wx_download_dir = value
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
    """启动视频监控"""
    from core.monitor.monitor import MonitorService, _monitor_running, _monitor_lock
    import threading

    with _monitor_lock:
        if _monitor_running:
            format_output({"code": 0, "message": "监控已在运行", "data": {"running": True}}, pretty=pretty)
            return

    svc = MonitorService()
    try:
        svc.start()
        format_output({"code": 0, "message": "监控已启动", "data": {"running": True}}, pretty=pretty)
    except Exception as e:
        error_output(f"启动失败: {e}")


@monitor_app.command("stop")
def monitor_stop(
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """停止视频监控"""
    from core.monitor.monitor import MonitorService, _monitor_running, _monitor_lock

    with _monitor_lock:
        if not _monitor_running:
            format_output({"code": 0, "message": "监控未在运行", "data": {"running": False}}, pretty=pretty)
            return

    svc = MonitorService()
    try:
        svc.stop()
        format_output({"code": 0, "message": "监控已停止", "data": {"running": False}}, pretty=pretty)
    except Exception as e:
        error_output(f"停止失败: {e}")


@monitor_app.command("status")
def monitor_status(
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """查看视频监控状态"""
    from core.monitor.monitor import is_monitor_active

    running = is_monitor_active()
    format_output({"code": 0, "message": "success", "data": {"running": running}}, pretty=pretty)


# ========== doc-sync 嵌套子命令 ==========

@doc_sync_app.command("start")
def doc_sync_start(
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """启动腾讯文档同步"""
    from core.monitor.doc_sync import DocSyncService, _doc_sync_running, _doc_sync_lock

    with _doc_sync_lock:
        if _doc_sync_running:
            format_output({"code": 0, "message": "腾讯文档同步已在运行", "data": {"running": True}}, pretty=pretty)
            return

    svc = DocSyncService()
    try:
        svc.start()
        format_output({"code": 0, "message": "腾讯文档同步已启动", "data": {"running": True}}, pretty=pretty)
    except Exception as e:
        error_output(f"启动失败: {e}")


@doc_sync_app.command("stop")
def doc_sync_stop(
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """停止腾讯文档同步"""
    from core.monitor.doc_sync import DocSyncService, _doc_sync_running, _doc_sync_lock

    with _doc_sync_lock:
        if not _doc_sync_running:
            format_output({"code": 0, "message": "腾讯文档同步未在运行", "data": {"running": False}}, pretty=pretty)
            return

    svc = DocSyncService()
    try:
        svc.stop()
        format_output({"code": 0, "message": "腾讯文档同步已停止", "data": {"running": False}}, pretty=pretty)
    except Exception as e:
        error_output(f"停止失败: {e}")


@doc_sync_app.command("status")
def doc_sync_status(
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """查看腾讯文档同步状态"""
    from core.monitor.doc_sync import is_doc_sync_active

    running = is_doc_sync_active()
    format_output({"code": 0, "message": "success", "data": {"running": running}}, pretty=pretty)


# 注册嵌套子命令组
app.add_typer(monitor_app, name="monitor")
app.add_typer(doc_sync_app, name="doc-sync")