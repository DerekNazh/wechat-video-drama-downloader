"""search 子命令组 — 搜索与批量添加"""

from typing import Optional
import typer

from core.cli.ctx import get_search_service, get_author_service
from core.cli.output import format_output, error_output

app = typer.Typer(help="搜索与批量添加", no_args_is_help=True)


@app.command("authors")
def search_authors(
    keyword: str = typer.Option(..., "--keyword", help="搜索关键词"),
    exact: bool = typer.Option(False, "--exact", help="精确匹配"),
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """搜索作者（需微信在线）"""
    svc = get_search_service()
    result = svc.search_author(keyword, exact_match=exact)

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
def search_add(
    keyword: str = typer.Option(..., "--keyword", help="作者名（精确匹配）"),
    pages: int = typer.Option(1, "--pages", help="拉取视频页数"),
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """搜索并添加作者+视频（需微信在线）"""
    svc = get_search_service()
    result = svc.add_author_with_videos(keyword, pages=pages)

    if result.get("code") != 0:
        error_output(result.get("msg", "添加失败"))

    data = result.get("data", {})
    format_output(
        {
            "code": 0,
            "message": "success",
            "data": {
                "author": data.get("author", {}),
                "videos_added": data.get("videos_added", 0),
            },
        },
        pretty=pretty,
    )


@app.command("batch-add")
def search_batch_add(
    keywords: str = typer.Option(..., "--keywords", help="作者名列表，逗号分隔"),
    pages: int = typer.Option(1, "--pages", help="每个作者拉取视频页数"),
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """批量添加多个作者+视频（需微信在线）"""
    keyword_list = [k.strip() for k in keywords.split(",") if k.strip()]
    if not keyword_list:
        error_output("未提供作者名")

    svc = get_search_service()
    result = svc.batch_add_authors_with_videos(keyword_list, pages=pages)

    format_output(
        {
            "code": 0,
            "message": "success",
            "data": result,
        },
        pretty=pretty,
    )
