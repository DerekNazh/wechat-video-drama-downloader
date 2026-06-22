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
