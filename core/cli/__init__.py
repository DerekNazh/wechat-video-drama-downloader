"""AI-Callable CLI 命令行系统

用法: python -m core.cli <资源> <动作> [选项]

资源:
  author    作者管理
  video     视频操作
  task      任务管理
  service   服务与监控
  search    搜索与批量添加
  inputer   导入管理
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
from core.cli import author, video, task, service, search, inputer  # noqa: E402

app.add_typer(author.app, name="author")
app.add_typer(video.app, name="video")
app.add_typer(task.app, name="task")
app.add_typer(service.app, name="service")
app.add_typer(search.app, name="search")
app.add_typer(inputer.app, name="inputer")