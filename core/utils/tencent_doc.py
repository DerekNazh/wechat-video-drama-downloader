"""腾讯文档客户端 - 批量导入视频数据到腾讯文档"""
import logging
import os
import re
import time
from pathlib import Path
from typing import Dict, List, Optional, Any

from core.utils.weixin_client import WechatVideoAPIClient
from core.api.error_codes import ErrorCode
from core.api.exceptions import BizError
from config.settings import settings

logger = logging.getLogger("tencent_doc")


class TencentDocClient:
    """腾讯文档批量导入客户端"""

    BASE_URL = "https://docs.qq.com"

    def __init__(self, doc_url: str = "", client_id: str = "", access_token: str = "", openid: str = ""):
        """初始化腾讯文档客户端

        Args:
            doc_url: 腾讯文档 URL，如果为空从环境变量读取
            client_id: 腾讯文档开放平台 Client ID，如果为空从环境变量读取
            access_token: 腾讯文档开放平台 Access Token，如果为空从环境变量读取
            openid: 腾讯文档开放平台 Open ID，如果为空从环境变量读取
        """
        from dotenv import load_dotenv

        # 加载 .env
        for _ in range(5):
            env_path = Path.cwd() / ".env"
            if env_path.exists():
                load_dotenv(env_path)
                break
            if Path.cwd().parent == Path.cwd():
                break

        # doc_url
        if not doc_url:
            doc_url = os.environ.get("TENCENT_DOC_URL", "") or os.environ.get("TENCENT_DOC_ID", "")
            if not doc_url:
                raise BizError(ErrorCode.DOC_URL_INVALID, detail="需要配置 TENCENT_DOC_URL 或 TENCENT_DOC_ID")

        self.doc_url = doc_url
        self.file_id, self.sheet_id = self._parse_doc_url(doc_url)

        # 凭证：优先使用参数，否则从环境变量读取
        self.access_token = access_token or os.environ.get("TENCENT_DOC_ACCESS_TOKEN", "")
        self.client_id = client_id or os.environ.get("TENCENT_DOC_CLIENT_ID", "")
        self.openid = openid or os.environ.get("TENCENT_DOC_OPENID", "")

        if not self.access_token or not self.client_id or not self.openid:
            raise BizError(ErrorCode.DOC_CREDENTIAL_MISSING)

        # wechat client
        self._wechat_client = WechatVideoAPIClient()

        # sheets 缓存
        self._sheets_cache: Dict[str, Dict] = {}

        logger.info(f"[TencentDoc] file_id={self.file_id}, sheet_id={self.sheet_id or '(默认)'}")

    def _parse_doc_url(self, url: str) -> tuple:
        """从 URL 提取 file_id 和 sheet_id"""
        match = re.search(r'/sheet/([^/?#]+)', url)
        if not match:
            raise BizError(ErrorCode.DOC_URL_INVALID, detail=f"无法从 URL 提取 file_id: {url}")
        file_id = match.group(1)
        tab_match = re.search(r'[?&]tab=([^&#]+)', url)
        sheet_id = tab_match.group(1) if tab_match else ""
        return file_id, sheet_id

    def _headers(self) -> dict:
        return {
            "Access-Token": self.access_token,
            "Client-Id": self.client_id,
            "Open-Id": self.openid,
            "Content-Type": "application/json",
        }

    def _request(self, method: str, path: str, **kwargs) -> dict:
        import requests
        url = f"{self.BASE_URL}{path}"
        kwargs.setdefault("timeout", 30)
        kwargs.setdefault("headers", self._headers())

        try:
            response = requests.request(method, url, **kwargs)
            response.raise_for_status()
        except requests.Timeout:
            raise BizError(ErrorCode.NETWORK_TIMEOUT, detail="腾讯文档 API 请求超时")
        except requests.ConnectionError:
            raise BizError(ErrorCode.NETWORK_ERROR, detail="腾讯文档 API 连接失败")
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 403:
                raise BizError(ErrorCode.DOC_PERMISSION_DENIED)
            raise BizError(ErrorCode.NETWORK_ERROR, detail=f"HTTP {e.response.status_code if e.response else '?'}")

        data = response.json()

        # 检查腾讯文档 API 业务错误码
        if isinstance(data, dict):
            code = data.get("code")
            message = data.get("message", "")

            # 400011: 请求配额用完
            if code == 400011:
                trace_id = data.get('details', {}).get('DebugInfo', {}).get('traceId', '')
                err = BizError(ErrorCode.DOC_QUOTA_EXCEEDED)
                err.log(extra=f"traceId={trace_id}")
                raise err

            # 400006: 认证失败
            if code == 400006:
                if "not matched" in message:
                    raise BizError(ErrorCode.DOC_TOKEN_MISMATCH)
                raise BizError(ErrorCode.DOC_AUTH_FAILED, detail=message)

            # 400004: 文档不存在
            if code == 400004:
                raise BizError(ErrorCode.DOC_NOT_FOUND, detail=message)

            # 400003: 权限不足
            if code == 400003:
                raise BizError(ErrorCode.DOC_PERMISSION_DENIED, detail=message)

            # 其他业务错误
            if code and code != 0:
                logger.warning(f"[腾讯文档] API 返回错误: code={code}, message={message}")
                raise BizError(ErrorCode.DOC_PARSE_ERROR, detail=f"code={code}, message={message}")

        return data

    def _query_sheets(self) -> List[Dict]:
        """查询所有工作表"""
        if self._sheets_cache:
            return list(self._sheets_cache.values())

        path = f"/openapi/spreadsheet/v3/files/{self.file_id}"
        data = self._request("GET", path)
        sheets = data.get("properties", [])

        # 验证只能有一个子表
        if len(sheets) > 1:
            raise BizError(ErrorCode.DOC_MULTI_SHEET, detail=f"当前有 {len(sheets)} 个子表，请删除多余的子表后重试")

        if len(sheets) == 0:
            raise BizError(ErrorCode.DOC_NO_SHEET)

        self._sheets_cache.clear()
        for sheet in sheets:
            sheet_id = sheet.get("sheetId", "")
            if sheet_id:
                self._sheets_cache[sheet_id] = sheet

        return sheets

    def get_first_sheet_id(self) -> str:
        """获取第一个（也是唯一的）子表 ID

        Returns:
            sheet_id

        Raises:
            ValueError: 如果没有子表或有多个子表
        """
        sheets = self._query_sheets()
        if not sheets:
            raise BizError(ErrorCode.DOC_NO_SHEET)

        return sheets[0].get("sheetId", "")

    def _find_sheet_by_title(self, title: str) -> Optional[str]:
        """根据标题查找工作表"""
        sheets = self._query_sheets()
        for sheet in sheets:
            if sheet.get("title") == title:
                return sheet.get("sheetId", "")
        return None

    def _create_sheet(self, title: str) -> str:
        """创建新工作表"""
        # 先检查是否已存在
        existing_id = self._find_sheet_by_title(title)
        if existing_id:
            logger.info(f"[TencentDoc] Sheet 已存在: {title}")
            return existing_id

        body = {"requests": [{"addSheetRequest": {"title": title}}]}
        path = f"/openapi/spreadsheet/v3/files/{self.file_id}/batchUpdate"
        try:
            data = self._request("POST", path, json=body)
            responses = data.get("responses", [])
            if not responses:
                # 可能权限不足无法创建，但可以尝试使用已有 sheet
                # 查找第一个可用的 sheet
                sheets = self._query_sheets()
                if sheets:
                    logger.warning(f"[TencentDoc] 创建 sheet 失败，使用已有 sheet")
                    return sheets[0].get("sheetId", "")
                raise BizError(ErrorCode.DOC_WRITE_FAILED, detail="创建工作表失败")

            sheet_id = responses[0].get("addSheetResponse", {}).get("properties", {}).get("sheetId", "")
            self._sheets_cache[sheet_id] = {"sheetId": sheet_id, "title": title, "rowCount": 0}
            return sheet_id
        except Exception as e:
            # 出错时尝试使用第一个 sheet
            sheets = self._query_sheets()
            if sheets:
                logger.warning(f"[TencentDoc] 创建 sheet 出错 {e}，使用已有 sheet")
                return sheets[0].get("sheetId", "")
            raise

    def _get_sheet_row_count(self, sheet_id: str) -> int:
        """获取 sheet 数据行数"""
        if sheet_id in self._sheets_cache:
            return max(1, self._sheets_cache[sheet_id].get("rowCount", 0))
        self._query_sheets()
        return 1

    def import_author_videos_by_pages(self, source_username: str, pages: int = 1) -> dict:
        """按页数导入作者视频

        Args:
            source_username: 作者 username
            pages: 页数（每页约15个视频）

        Returns:
            {"code": 0, "data": [...], "msg": ""}
        """
        if not source_username:
            return {"code": -1, "msg": "作者ID不能为空"}

        if pages < 1:
            return {"code": -1, "msg": "页数不能小于1"}

        all_videos = []
        next_marker = None

        # 分页拉取视频
        for _ in range(pages):
            result = self._wechat_client.get_author_videos(source_username, page_size=15, last_buff=next_marker)
            if result.get("code") != 0:
                break

            videos = result.get("data", [])
            if not videos:
                break

            all_videos.extend(videos)
            next_marker = result.get("next_marker")
            if not next_marker:
                break

        # 转换为任务数据（新格式）
        # 字段：author_name, search_type, search_value
        task_data = []
        for video in all_videos:
            obj_desc = video.get("objectDesc", {})
            task_data.append({
                # 第一个字段：作者名字
                "author_name": source_username,
                # 第二个字段：搜索类型（页数模式）
                "search_type": "pages",
                # 第三个字段：页数值
                "search_value": pages,
            })

        return {"code": 0, "data": task_data, "msg": ""}

    def import_author_videos_by_date(self, source_username: str, before_date: str) -> dict:
        """按日期导入作者视频（发布时间早于该日期）

        Args:
            source_username: 作者 username
            before_date: 日期字符串，如 "2025-04-23"（只导入早于该日期的视频）

        Returns:
            {"code": 0, "data": [...], "msg": ""}
        """
        if not source_username:
            return {"code": -1, "msg": "作者ID不能为空"}

        # 解析日期字符串为时间戳
        before_timestamp = 0
        if before_date:
            try:
                from datetime import datetime
                dt = datetime.strptime(before_date, "%Y-%m-%d")
                before_timestamp = int(dt.timestamp())
            except ValueError:
                return {"code": -1, "msg": f"日期格式错误: {before_date}，应为 YYYY-MM-DD"}

        # 拉取所有视频
        all_videos = []
        next_marker = None

        while True:
            result = self._wechat_client.get_author_videos(source_username, page_size=15, last_buff=next_marker)
            if result.get("code") != 0:
                break

            videos = result.get("data", [])
            if not videos:
                break

            all_videos.extend(videos)
            next_marker = result.get("last_buff")
            if not next_marker:
                break

        # 按时间戳过滤
        filtered = []
        for video in all_videos:
            createtime = video.get("createtime", 0)
            # createtime 是秒时间戳
            if before_timestamp and createtime > 0 and createtime > before_timestamp:
                continue
            filtered.append(video)

        # 转换为任务数据（新格式）
        # 字段：author_name, search_type, search_value
        task_data = []
        for video in filtered:
            task_data.append({
                # 第一个字段：作者名字
                "author_name": source_username,
                # 第二个字段：搜索类型（日期模式）
                "search_type": "date",
                # 第三个字段：截止日期
                "search_value": before_date,
            })

        return {"code": 0, "data": task_data, "msg": ""}

    def write_batch(self, data_list: List[Dict]) -> str:
        """批量写入腾讯文档

        Args:
            data_list: 数据列表

        Returns:
            文档 URL
        """
        if not data_list:
            return self.doc_url

        # 使用日期作为 sheet 名
        from datetime import datetime
        sheet_title = datetime.now().strftime("%Y-%m-%d")

        # 查找或创建 sheet
        sheet_id = self._find_sheet_by_title(sheet_title)
        if not sheet_id:
            sheet_id = self._create_sheet(sheet_title)

        # 写表头（新 sheet）
        start_row = self._get_sheet_row_count(sheet_id)
        if start_row == 0:
            # 写表头
            header_values = [{"cellValue": {"text": str(k)}} for k in data_list[0].keys()]
            header_body = {
                "requests": [{
                    "updateRangeRequest": {
                        "sheetId": sheet_id,
                        "gridData": {
                            "startRow": 0,
                            "startColumn": 0,
                            "rows": [{"values": header_values}],
                        }
                    }
                }]
            }
            path = f"/openapi/spreadsheet/v3/files/{self.file_id}/batchUpdate"
            self._request("POST", path, json=header_body)
            start_row = 1

        # 写数据
        rows_data = []
        for data in data_list:
            values = [{"cellValue": {"text": str(v) if v is not None else ""}} for v in data.values()]
            rows_data.append({"values": values})

        data_body = {
            "requests": [{
                "updateRangeRequest": {
                    "sheetId": sheet_id,
                    "gridData": {
                        "startRow": start_row,
                        "startColumn": 0,
                        "rows": rows_data,
                    }
                }
            }]
        }
        path = f"/openapi/spreadsheet/v3/files/{self.file_id}/batchUpdate"
        self._request("POST", path, json=data_body)

        logger.info(f"[TencentDoc] 写入完成: {len(data_list)} 行")
        return self.doc_url

    def update_cells(self, sheet_id: str, updates: list) -> bool:
        """精确更新指定单元格（回填 author_id 用）

        将多个单元格更新合并为一次 API 请求。

        Args:
            sheet_id: 工作表 ID
            updates: [{"row": 1, "col": 0, "value": "doc_author_xxx"}, ...]

        Returns:
            True 成功，False 失败
        """
        if not updates:
            return True

        # 按行分组，同一行的多个单元格合并为一个 row
        rows_map = {}
        for u in updates:
            r = u["row"]
            if r not in rows_map:
                rows_map[r] = {}
            rows_map[r][u["col"]] = u["value"]

        # 找出最小行号和列号作为起始偏移
        min_row = min(rows_map.keys())
        min_col = min(min(cols.keys()) for cols in rows_map.values())

        # 构造 rows 数组（需要填满连续行）
        max_row = max(rows_map.keys())
        rows_data = []
        for r in range(min_row, max_row + 1):
            cols = rows_map.get(r, {})
            if not cols:
                continue
            max_c = max(cols.keys())
            values = []
            for c in range(min_col, max_c + 1):
                val = cols.get(c, "")
                values.append({"cellValue": {"text": str(val)}})
            rows_data.append({
                "startRow": r,
                "values": values,
            })

        # 每个行范围作为独立 request（腾讯文档 API 限制单次请求）
        requests = []
        for rd in rows_data:
            max_c_in_row = min_col + len(rd["values"]) - 1
            requests.append({
                "updateRangeRequest": {
                    "sheetId": sheet_id,
                    "gridData": {
                        "startRow": rd["startRow"],
                        "startColumn": min_col,
                        "rows": [{"values": rd["values"]}],
                    }
                }
            })

        body = {"requests": requests}
        path = f"/openapi/spreadsheet/v3/files/{self.file_id}/batchUpdate"

        try:
            self._request("POST", path, json=body)
            logger.info(f"[TencentDoc] update_cells 成功: {len(updates)} 个单元格")
            return True
        except Exception as e:
            logger.error(f"[TencentDoc] update_cells 失败: {e}")
            return False

    def read_all_authors(self) -> List[Dict]:
        """从腾讯文档读取所有作者数据

        读取当前 sheet 的所有行数据，返回格式：
        [{"author_name": "...", "search_type": "pages", "search_value": 1}, ...]

        Returns:
            作者数据列表
        """
        sheets = self._query_sheets()
        if not sheets:
            logger.warning("[read_all_authors] 没有工作表")
            return []

        # 读取第一个 sheet 的数据
        sheet = sheets[0]
        sheet_id = sheet.get("sheetId", "")
        if not sheet_id:
            return []

        # 获取工作表总行数
        row_total = sheet.get("rowTotal", 200)

        # 使用 A1 表示法读取数据
        path = f"/openapi/spreadsheet/v3/files/{self.file_id}/{sheet_id}/A1:Z{row_total}"
        try:
            data = self._request("GET", path)
            return data
        except Exception as e:
            logger.error(f"[read_all_authors] 读取失败: {e}")
            return []

    def read_authors_from_sheet(self, sheet_title: str = "") -> List[Dict]:
        """从指定或最新 sheet 读取作者数据

        Args:
            sheet_title: sheet 标题，为空则读取最新的 sheet

        Returns:
            作者数据列表
        """
        if sheet_title:
            sheet_id = self._find_sheet_by_title(sheet_title)
        else:
            sheets = self._query_sheets()
            if not sheets:
                return []
            sheet_id = sheets[0].get("sheetId", "")

        if not sheet_id:
            logger.warning(f"[read_authors_from_sheet] 未找到 sheet: {sheet_title}")
            return []

        # 读取数据 - 腾讯文档 API 读取表格数据
        # 使用 v3 版本的获取数据范围 API
        path = f"/openapi/spreadsheet/v3/files/{self.file_id}/sheets/{sheet_id}/grid/all"
        try:
            data = self._request("GET", path)
            return data
        except Exception as e:
            logger.error(f"[read_authors_from_sheet] 读取失败: {e}")
            return []

    def get_sheet_data(self, sheet_id: str = "") -> dict:
        """获取指定 sheet 的所有数据

        Args:
            sheet_id: sheet ID，为空则读取第一个 sheet

        Returns:
            {"code": 0, "data": {...}, "msg": ""}
        """
        if not sheet_id:
            sheets = self._query_sheets()
            if not sheets:
                return {"code": -1, "data": {}, "msg": "没有工作表"}
            sheet_id = sheets[0].get("sheetId", "")

        if not sheet_id:
            return {"code": -1, "data": {}, "msg": "无效的 sheet_id"}

        # 查询工作表信息获取总行数
        sheets = self._query_sheets()
        row_total = 200  # 默认值
        for sheet in sheets:
            if sheet.get("sheetId") == sheet_id:
                row_total = sheet.get("rowTotal", 200)
                break

        # 使用 A1 表示法读取数据，动态使用总行数
        path = f"/openapi/spreadsheet/v3/files/{self.file_id}/{sheet_id}/A1:Z{row_total}"
        try:
            data = self._request("GET", path)
            # 检查 API 返回的错误
            if isinstance(data, dict):
                if data.get("code") == 400006:
                    return {"code": -1, "data": {}, "msg": f"认证失败: {data.get('message')}"}
                if data.get("code") and data.get("code") != 0:
                    return {"code": -1, "data": {}, "msg": f"API错误: {data.get('message')}"}
                # 成功时返回 ret==0
                if data.get("ret") and data.get("ret") != 0:
                    return {"code": -1, "data": {}, "msg": f"API错误: {data.get('msg')}"}
            return {"code": 0, "data": data, "msg": ""}
        except Exception as e:
            logger.error(f"[get_sheet_data] 读取失败: {e}")
            return {"code": -1, "data": {}, "msg": str(e)}

    def parse_sheet_rows(self, sheet_data: dict) -> List[Dict]:
        """解析 sheet 数据为行列表

        三列格式：author_name, search_type, search_value
        方案 A：不回写 author_id，文档保持三列

        Args:
            sheet_data: get_sheet_data 返回的数据

        Returns:
            行数据列表，每行包含 author_name, search_type, search_value
        """
        rows = []
        grid_data = sheet_data.get("data", {}).get("gridData", {})
        row_data_list = grid_data.get("rows", [])

        if not row_data_list:
            return rows

        # 三列格式：author_name(0), search_type(1), search_value(2)
        col_name, col_type, col_value = 0, 1, 2

        for row_idx, row in enumerate(row_data_list):
            if row_idx < 1:  # 跳过表头
                continue

            values = row.get("values", [])
            if not values:
                continue

            row_dict = {
                "author_name": "",
                "search_type": "",
                "search_value": "",
            }

            for idx, cell in enumerate(values):
                if idx > col_value:
                    break
                text = self._parse_cell_text(cell)

                if idx == col_name:
                    row_dict["author_name"] = text
                elif idx == col_type:
                    row_dict["search_type"] = text
                elif idx == col_value:
                    row_dict["search_value"] = text

            if row_dict.get("author_name"):
                rows.append(row_dict)
                logger.debug(f"[parse_sheet_rows] 第{row_idx}行解析结果: {row_dict}")

        logger.info(f"[parse_sheet_rows] 共解析 {len(rows)} 行数据")
        return rows

    def _parse_cell_text(self, cell: dict) -> str:
        """解析单元格文本值

        Args:
            cell: 单元格 dict，包含 cellValue

        Returns:
            字符串值
        """
        cell_value = cell.get("cellValue") or {}
        if not cell_value:
            return ""
        text = cell_value.get("text", "")
        if not text and "number" in cell_value:
            text = str(cell_value.get("number", ""))
        if not text and "time" in cell_value:
            t = cell_value.get("time", {})
            year = t.get("year", 0)
            month = t.get("month", 0)
            day = t.get("day", 0)
            if year and month and day:
                text = f"{year}-{month:02d}-{day:02d}"
        return str(text).strip()

    def validate_sheet_structure(self, sheet_data: dict) -> dict:
        """验证表结构是否符合预期

        验证规则：
        1. 第一行必须是表头：author_name, search_type, search_value（如果没有表头则报错）
        2. 每行必须有3个字段
        3. search_type 必须是 "pages" 或 "date"
        4. search_value 必须是有效数值

        Returns:
            {"code": 0, "valid": true, "errors": [], "msg": ""}
            或 {"code": -1, "valid": false, "errors": [...], "msg": "验证失败"}
        """
        errors = []

        if not sheet_data.get("data"):
            return {"code": -1, "valid": False, "errors": ["数据为空"], "msg": "数据为空"}

        grid_data = sheet_data.get("data", {}).get("gridData", {})
        row_data_list = grid_data.get("rows", [])

        if not row_data_list:
            return {"code": -1, "valid": False, "errors": ["表格没有数据"], "msg": "表格没有数据"}

        # 预期表头
        expected_headers = ["author_name", "search_type", "search_value"]

        # 验证第一行是否为表头
        first_row = row_data_list[0]
        first_values = first_row.get("values", [])

        # 检查第一行字段数
        if len(first_values) < 3:
            errors.append(f"第1行（表头）字段数不足：期望3个，实际{len(first_values)}个")
        else:
            # 验证表头字段名
            actual_headers = []
            for idx, cell in enumerate(first_values[:3]):
                cell_value = cell.get("cellValue") or {}
                text = cell_value.get("text", "").strip() if cell_value else ""
                actual_headers.append(text)

            # 检查第一行是否是表头（如果没有表头则报错）
            is_header = all(h == e for h, e in zip(actual_headers, expected_headers))
            if not is_header:
                errors.append(f"第1行必须是表头 {expected_headers}，实际：{actual_headers}。请先在文档第一行添加表头。")

        # 如果已经有错误，直接返回
        if errors:
            return {"code": -1, "valid": False, "errors": errors, "msg": f"验证失败，发现 {len(errors)} 个问题"}

        # 验证数据行（从第2行开始）
        for row_idx in range(1, len(row_data_list)):
            row = row_data_list[row_idx]
            values = row.get("values", [])

            # 检查字段数
            if len(values) < 3:
                errors.append(f"第{row_idx + 1}行字段数不足：期望3个，实际{len(values)}个")
                continue

            # 检查 author_name 不应为空
            cell_value_0 = values[0].get("cellValue") or {}
            author_name = cell_value_0.get("text", "").strip() if cell_value_0 else ""

            # 检查 search_type
            cell_value_1 = values[1].get("cellValue") or {}
            search_type = cell_value_1.get("text", "").strip() if cell_value_1 else ""
            if search_type and search_type not in ["pages", "date"]:
                errors.append(f"第{row_idx + 1}行 search_type 无效：'{search_type}'（应为 'pages' 或 'date'）")

            # 检查 search_value 有效性
            cell_value_2 = values[2].get("cellValue") or {}
            search_value_text = cell_value_2.get("text", "").strip() if cell_value_2 else ""

            if search_type == "pages":
                # pages 模式：search_value 必须是数字
                if search_value_text:
                    try:
                        int(search_value_text)
                    except ValueError:
                        errors.append(f"第{row_idx + 1}行 search_value 不是有效数值：'{search_value_text}'（pages 模式应为数字）")
            elif search_type == "date":
                # date 模式：search_value 必须是日期格式 YYYY-MM-DD
                if search_value_text:
                    try:
                        from datetime import datetime
                        datetime.strptime(search_value_text, "%Y-%m-%d")
                    except ValueError:
                        errors.append(f"第{row_idx + 1}行 search_value 不是有效日期：'{search_value_text}'（date 模式应为 YYYY-MM-DD 格式）")

        if errors:
            return {"code": -1, "valid": False, "errors": errors, "msg": f"验证失败，发现 {len(errors)} 个问题"}

        return {"code": 0, "valid": True, "errors": [], "msg": "验证通过"}

    def import_from_doc_to_database(self) -> dict:
        """从腾讯文档读取作者数据并保存到数据库

        完整流程：
        1. 读取腾讯文档数据
        2. 验证表结构
        3. 解析作者数据
        4. 通过 SearchService 搜索作者并获取视频（统一标准化处理）
        5. 保存到数据库（作者表 + 视频表）

        Returns:
            {"code": 0, "data": {"authors_saved": N, "videos_saved": M}, "msg": ""}
            或 {"code": -1, "msg": "错误信息"}
        """
        from datetime import datetime
        from core.utils.database import db
        from core.utils.store import Author, AuthorVideo
        from core.service.search import SearchService

        # 1. 读取腾讯文档数据
        sheet_data = self.get_sheet_data()
        if sheet_data.get("code") != 0:
            return {"code": -1, "msg": f"读取文档失败: {sheet_data.get('msg')}"}

        # 2. 验证表结构
        validation_result = self.validate_sheet_structure(sheet_data)
        if not validation_result.get("valid"):
            return {"code": -1, "msg": f"表结构验证失败: {validation_result.get('msg')}"}

        # 3. 解析作者数据（跳过表头，从第2行开始）
        rows = self.parse_sheet_rows(sheet_data)
        if not rows:
            return {"code": -1, "msg": "文档没有作者数据"}

        if len(rows) == 1:
            logger.info("[import_from_doc_to_database] 只有1条数据，跳过批量导入测试")

        service = SearchService()
        authors_saved = 0
        videos_saved = 0

        # 4. 遍历每个作者
        for row in rows:
            author_name = row.get("author_name", "").strip()
            search_type = row.get("search_type", "").strip()
            search_value = row.get("search_value", "")

            if not author_name:
                logger.warning("[import_from_doc_to_database] 跳过空作者名")
                continue

            # 通过 SearchService 搜索作者
            search_result = service.search_author(author_name)
            if search_result.get("code") != 0 or not search_result.get("data"):
                logger.warning(f"[import_from_doc_to_database] 未找到作者: {author_name}")
                continue

            author_data = search_result["data"]
            source_author_id = author_data.get("source_author_id", "")

            # 根据 search_type 分发到对应的视频拉取方法
            logger.info(f"[import_from_doc] 分发: author={author_name}, search_type='{search_type}', search_value='{search_value}'")
            if search_type == "date":
                logger.info(f"[import_from_doc] 调用 get_author_videos_before_date")
                videos_result = service.get_author_videos_before_date(
                    source_author_id, search_value
                )
            elif search_type == "pages":
                logger.info(f"[import_from_doc] 调用 get_author_videos (pages模式)")
                try:
                    pages = int(search_value) if search_value else 1
                except ValueError:
                    logger.warning(f"[import_from_doc_to_database] 无效页数: {search_value}")
                    continue
                videos_result = service.get_author_videos(
                    source_author_id, pages=pages
                )
            else:
                logger.warning(f"[import_from_doc_to_database] 无效搜索类型: '{search_type}'")
                continue

            if videos_result.get("code") != 0:
                logger.warning(f"[import_from_doc_to_database] 获取视频失败: {author_name}")
                continue

            videos = videos_result.get("data", [])
            if not videos:
                logger.warning(f"[import_from_doc_to_database] 作者 {author_name} 没有视频")
                continue

            # 5. 保存到数据库
            now = datetime.now().isoformat()

            existing_author = db.get_author_by_source_id(source_author_id)
            if existing_author:
                author_id = existing_author.id
                logger.info(f"[import_from_doc_to_database] 作者已存在: {author_name}")
            else:
                author_id = f"doc_author_{int(datetime.now().timestamp() * 1000)}"
                author = Author(
                    id=author_id,
                    source_author_id=source_author_id,
                    name=author_data.get("name", author_name),
                    tag="",
                    bio=author_data.get("bio", ""),
                    avatar_url=author_data.get("avatar_url", ""),
                    cover_img_url=author_data.get("cover_img_url", ""),
                    created_at=now,
                    updated_at=now,
                )
                if db.create_author(author):
                    authors_saved += 1
                    logger.info(f"[import_from_doc_to_database] 保存作者: {author_name}")
                else:
                    logger.error(f"[import_from_doc_to_database] 保存作者失败: {author_name}")
                    continue

            # 保存视频（SearchService 已标准化字段名）
            for video in videos:
                video_id = video.get('video_id', '')
                author_video = AuthorVideo(
                    video_id=video_id,
                    author_id=author_id,
                    title=video.get("title", ""),
                    object_nonce_id=video.get("object_nonce_id", ""),
                    url=video.get("url", ""),
                    spec=video.get("spec", ""),
                    file_size=video.get("file_size", 0),
                    cover_url=video.get("cover_url", ""),
                    decode_key=video.get("decode_key", 0),
                    author_avatar=video.get("author_avatar", ""),
                    duration=video.get("duration", 0),
                    create_time=video.get("create_time", ""),
                    is_downloaded=0,
                    download_path="",
                    downloaded_at=None,
                    video_type=video.get("video_type", "short_video"),
                )
                if db.create_author_video(author_video):
                    videos_saved += 1

            logger.info(f"[import_from_doc_to_database] 作者 {author_name}: {len(videos)} 个视频")

        return {
            "code": 0,
            "data": {
                "authors_saved": authors_saved,
                "videos_saved": videos_saved,
            },
            "msg": f"导入完成，保存 {authors_saved} 个作者，{videos_saved} 个视频"
        }

    def import_from_doc_to_database_with_progress(self):
        """从腾讯文档读取作者数据并保存到数据库（带 SSE 进度推送）

        与 import_from_doc_to_database 逻辑相同，但通过 SSE 推送进度。
        """
        from core.utils.event_bus import emit

        sheet_data = self.get_sheet_data()
        if sheet_data.get("code") != 0:
            emit("import_progress", {"phase": "done", "success": 0, "fail": 0, "total": 0, "error": f"读取文档失败: {sheet_data.get('msg')}", "import_type": "tencent_doc"})
            return

        validation_result = self.validate_sheet_structure(sheet_data)
        if not validation_result.get("valid"):
            emit("import_progress", {"phase": "done", "success": 0, "fail": 0, "total": 0, "error": f"表结构验证失败: {validation_result.get('msg')}", "import_type": "tencent_doc"})
            return

        rows = self.parse_sheet_rows(sheet_data)
        total = len(rows)

        if total == 0:
            emit("import_progress", {"phase": "done", "success": 0, "fail": 0, "total": 0, "import_type": "tencent_doc"})
            return

        emit("import_progress", {"phase": "start", "total": total, "import_type": "tencent_doc"})

        from datetime import datetime
        from core.utils.database import db
        from core.utils.store import Author, AuthorVideo
        from core.service.search import SearchService

        service = SearchService()
        authors_saved = 0
        videos_saved = 0

        for idx, row in enumerate(rows):
            author_name = row.get("author_name", "").strip()
            search_type = row.get("search_type", "").strip()
            search_value = row.get("search_value", "")

            logger.debug(f"[import_from_doc] 第{idx+1}行: author={author_name}, type={search_type!r}, value={search_value!r}")

            try:
                if not author_name:
                    continue

                search_result = service.search_author(author_name)
                if search_result.get("code") != 0 or not search_result.get("data"):
                    continue

                author_data = search_result["data"]
                source_author_id = author_data.get("source_author_id", "")

                if search_type == "date":
                    videos_result = service.get_author_videos_before_date(source_author_id, search_value)
                elif search_type == "pages":
                    try:
                        pages = int(search_value) if search_value else 1
                    except ValueError:
                        continue
                    videos_result = service.get_author_videos(source_author_id, pages=pages)
                else:
                    continue

                if videos_result.get("code") != 0:
                    continue

                videos = videos_result.get("data", [])
                if not videos:
                    continue

                now = datetime.now().isoformat()

                existing_author = db.get_author_by_source_id(source_author_id)
                if existing_author:
                    author_id = existing_author.id
                else:
                    author_id = f"doc_author_{int(datetime.now().timestamp() * 1000)}"
                    author = Author(
                        id=author_id,
                        source_author_id=source_author_id,
                        name=author_data.get("name", author_name),
                        tag="",
                        bio=author_data.get("bio", ""),
                        avatar_url=author_data.get("avatar_url", ""),
                        cover_img_url=author_data.get("cover_img_url", ""),
                        created_at=now,
                        updated_at=now,
                    )
                    if db.create_author(author):
                        authors_saved += 1
                    else:
                        continue

                for video in videos:
                    video_id = video.get('video_id', '')
                    author_video = AuthorVideo(
                        video_id=video_id,
                        author_id=author_id,
                        title=video.get("title", ""),
                        object_nonce_id=video.get("object_nonce_id", ""),
                        url=video.get("url", ""),
                        spec=video.get("spec", ""),
                        file_size=video.get("file_size", 0),
                        cover_url=video.get("cover_url", ""),
                        decode_key=video.get("decode_key", 0),
                        author_avatar=video.get("author_avatar", ""),
                        duration=video.get("duration", 0),
                        create_time=video.get("create_time", ""),
                        is_downloaded=0,
                        download_path="",
                        downloaded_at=None,
                        video_type=video.get("video_type", "short_video"),
                    )
                    if db.create_author_video(author_video):
                        videos_saved += 1

            except Exception as e:
                logger.error(f"[import_from_doc_to_database_with_progress] 处理 {author_name} 失败: {e}")
            finally:
                emit("import_progress", {
                    "phase": "processing",
                    "total": total,
                    "current": idx + 1,
                    "name": author_name,
                    "success": authors_saved,
                    "fail": (idx + 1) - authors_saved,
                    "import_type": "tencent_doc",
                })

        emit("import_progress", {
            "phase": "done",
            "total": total,
            "success": authors_saved,
            "fail": total - authors_saved,
            "import_type": "tencent_doc",
        })