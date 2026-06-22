"""inputer 子命令组 — 导入管理"""

from typing import Optional
import typer

from core.cli.output import format_output, error_output

app = typer.Typer(help="导入管理", no_args_is_help=True)


@app.command("csv")
def inputer_csv(
    file: str = typer.Option(..., "--file", help="CSV文件路径"),
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """导入CSV文件（需微信在线）"""
    from pathlib import Path

    csv_path = Path(file)
    if not csv_path.exists():
        error_output(f"文件不存在: {file}")

    from core.service.inputer import CSVParser
    parser = CSVParser()
    try:
        authors = parser.parse(str(csv_path))
        format_output(
            {"code": 0, "message": "success", "data": {"parsed": len(authors), "authors": authors}},
            pretty=pretty,
        )
    except Exception as e:
        error_output(f"解析失败: {e}")


@app.command("excel")
def inputer_excel(
    file: str = typer.Option(..., "--file", help="Excel文件路径"),
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """导入Excel文件（需微信在线）"""
    from pathlib import Path

    excel_path = Path(file)
    if not excel_path.exists():
        error_output(f"文件不存在: {file}")

    from core.utils.excel_client import ExcelClient
    client = ExcelClient()
    try:
        authors = client.parse(str(excel_path))
        format_output(
            {"code": 0, "message": "success", "data": {"parsed": len(authors), "authors": authors}},
            pretty=pretty,
        )
    except Exception as e:
        error_output(f"解析失败: {e}")


@app.command("tencent-doc")
def inputer_tencent_doc(
    doc_url: Optional[str] = typer.Option(None, "--url", help="腾讯文档URL"),
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """导入腾讯文档（需微信在线）"""
    from core.utils.tencent_doc import TencentDocClient

    client = TencentDocClient()
    try:
        if doc_url:
            authors = client.fetch_from_url(doc_url)
        else:
            authors = client.fetch_all()
        format_output(
            {"code": 0, "message": "success", "data": {"parsed": len(authors), "authors": authors}},
            pretty=pretty,
        )
    except Exception as e:
        error_output(f"导入失败: {e}")


@app.command("template")
def inputer_template(
    type: str = typer.Option("csv", "--type", help="模板类型: csv|excel"),
    output: Optional[str] = typer.Option(None, "--output", help="输出路径"),
    pretty: bool = typer.Option(False, "--pretty", help="表格输出"),
):
    """下载导入模板"""
    if type not in ("csv", "excel"):
        error_output(f"无效类型: {type}，可选: csv|excel")

    from pathlib import Path
    from config.settings import settings

    template_dir = settings.static_dir / "templates"
    template_dir.mkdir(parents=True, exist_ok=True)

    if type == "csv":
        template_content = "作者名,备注\n示例作者1,备注1\n示例作者2,备注2\n"
        template_path = template_dir / "import_template.csv"
    else:
        template_path = template_dir / "import_template.xlsx"
        try:
            import openpyxl
            wb = openpyxl.Workbook()
            ws = wb.active
            ws.title = "作者列表"
            ws.append(["作者名", "备注"])
            ws.append(["示例作者1", "备注1"])
            ws.append(["示例作者2", "备注2"])
            wb.save(str(template_path))
            format_output(
                {"code": 0, "message": "success", "data": {"template": str(template_path)}},
                pretty=pretty,
            )
            return
        except Exception as e:
            error_output(f"创建Excel模板失败: {e}")

    template_path.write_text(template_content, encoding="utf-8")
    format_output(
        {"code": 0, "message": "success", "data": {"template": str(template_path)}},
        pretty=pretty,
    )
