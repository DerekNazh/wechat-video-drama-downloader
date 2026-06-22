# 输入器  搜索作者导入  CSV导入  腾讯文档导入  飞书文档导入

import csv
from pathlib import Path
from typing import Dict, List, Optional


class CSVParser:
    """CSV 解析与校验器

    用于校验和解析作者导入 CSV 文件

    预期格式:
        author_name,search_type,search_value
        孤独,pages,1
        象棋小乔,date,2025-01-01
    """

    # 期望的表头字段
    REQUIRED_FIELDS = ["author_name", "search_type", "search_value"]

    # search_type 有效值
    VALID_SEARCH_TYPES = ["pages", "date", "all"]

    def __init__(self, file_path: str):
        """初始化解析器

        Args:
            file_path: CSV 文件路径
        """
        self.file_path = Path(file_path)
        self.errors: List[str] = []
        self.data: List[Dict] = []

    def validate(self) -> Dict:
        """校验并解析 CSV 文件

        Returns:
            {
                "valid": bool,
                "errors": List[str],
                "data": List[Dict],
                "total": int
            }
        """
        self.errors = []
        self.data = []

        # 1. 检查文件是否存在
        if not self._check_file_exists():
            return self._error_result()

        # 2. 读取 CSV 内容
        rows = self._read_csv()
        if rows is None:
            return self._error_result()

        # 3. 校验表头
        if not self._validate_header(rows[0]):
            return self._error_result()

        # 4. 校验所有数据行
        data_rows = rows[1:]  # 去掉表头
        self._validate_data_rows(data_rows)

        # 5. 返回结果
        if self.errors:
            return self._error_result()

        return {
            "valid": True,
            "errors": [],
            "data": self.data,
            "total": len(self.data)
        }

    def _check_file_exists(self) -> bool:
        """检查文件是否存在"""
        if not self.file_path.exists():
            self.errors.append(f"文件不存在: {self.file_path}")
            return False
        return True

    def _read_csv(self) -> Optional[List[List[str]]]:
        """读取 CSV 文件"""
        try:
            with open(self.file_path, "r", encoding="utf-8-sig") as f:
                reader = csv.reader(f)
                rows = list(reader)
                return rows
        except UnicodeDecodeError:
            # 尝试 GBK 编码
            try:
                with open(self.file_path, "r", encoding="gbk") as f:
                    reader = csv.reader(f)
                    rows = list(reader)
                    return rows
            except Exception as e:
                self.errors.append(f"文件编码不支持: {e}")
                return None
        except Exception as e:
            self.errors.append(f"读取文件失败: {e}")
            return None

    def _validate_header(self, header: List[str]) -> bool:
        """校验表头字段"""
        if not header:
            self.errors.append("CSV 文件表头为空")
            return False

        # 清理表头空白
        header = [h.strip() for h in header]

        if header != self.REQUIRED_FIELDS:
            self.errors.append(
                f"表头字段不匹配: 期望 {self.REQUIRED_FIELDS}, 实际 {header}"
            )
            return False
        return True

    def _validate_data_rows(self, rows: List[List[str]]) -> None:
        """校验所有数据行"""
        for index, row in enumerate(rows, start=2):
            # 跳过空行
            if self._is_empty_row(row):
                continue

            # 校验字段数量
            if len(row) != len(self.REQUIRED_FIELDS):
                self.errors.append(
                    f"第 {index} 行: 字段数量不匹配, 期望 {len(self.REQUIRED_FIELDS)}, 实际 {len(row)}"
                )
                continue

            author_name = row[0].strip()
            search_type = row[1].strip()
            search_value = row[2].strip()

            # 校验 author_name 不能为空
            if not author_name:
                self.errors.append(f"第 {index} 行: author_name 字段不能为空")
                continue

            # 校验 search_type 必须是有效值
            if search_type not in self.VALID_SEARCH_TYPES:
                self.errors.append(
                    f"第 {index} 行: search_type 必须是 {self.VALID_SEARCH_TYPES} 之一, 实际 '{search_type}'"
                )
                continue

            # 校验 search_value
            if search_type == "pages" or search_type == "all":
                # pages/all 模式必须是正整数
                try:
                    value = int(search_value)
                    if value <= 0:
                        self.errors.append(f"第 {index} 行: search_value 必须是正整数, 实际 {value}")
                        continue
                except ValueError:
                    self.errors.append(f"第 {index} 行: search_value 必须是数字, 实际 '{search_value}'")
                    continue
            elif search_type == "date":
                # date 模式兼容多种日期格式：YYYY-MM-DD、YYYY/M/D、YYYY-M-D
                from datetime import datetime
                normalized = self._normalize_date(search_value)
                if not normalized:
                    self.errors.append(f"第 {index} 行: search_value 必须是有效日期格式, 实际 '{search_value}'")
                    continue
                search_value = normalized

            # 构建数据字典
            self.data.append({
                "author_name": author_name,
                "search_type": search_type,
                "search_value": search_value
            })

    def _is_empty_row(self, row: List[str]) -> bool:
        """检查是否为空行"""
        return all(cell.strip() == "" for cell in row)

    @staticmethod
    def _normalize_date(date_str: str) -> str:
        """将多种日期格式标准化为 YYYY-MM-DD

        支持格式：
        - YYYY-MM-DD (2026-01-01)
        - YYYY/M/D   (2026/1/1, 2026/01/01)
        - YYYY-M-D   (2026-1-1)
        - YYYY/MM/DD HH:MM:SS (Excel 时间戳格式)
        """
        from datetime import datetime

        if not date_str:
            return ""

        date_str = date_str.strip()

        formats = [
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%Y-%m-%dT%H:%M:%S",
            "%Y/%m/%d %H:%M:%S",
            "%Y-%m-%d %H:%M:%S",
        ]

        for fmt in formats:
            try:
                dt = datetime.strptime(date_str, fmt)
                return dt.strftime("%Y-%m-%d")
            except ValueError:
                continue

        # 尝试非零填充格式（Excel 输出的 2026/1/1 格式）
        for sep in ["/", "-"]:
            parts = date_str.split(" ")[0].split(sep)
            if len(parts) == 3:
                try:
                    y, m, d = int(parts[0]), int(parts[1]), int(parts[2])
                    dt = datetime(y, m, d)
                    return dt.strftime("%Y-%m-%d")
                except (ValueError, IndexError):
                    continue

        return ""

    def _error_result(self) -> Dict:
        """返回错误结果"""
        return {
            "valid": False,
            "errors": self.errors,
            "data": [],
            "total": 0
        }


def parse_author_csv(file_path: str) -> Dict:
    """解析作者 CSV 文件

    Args:
        file_path: CSV 文件路径

    Returns:
        校验结果字典
    """
    parser = CSVParser(file_path)
    return parser.validate()