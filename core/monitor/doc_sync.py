"""腾讯文档实时监控同步

在现有批量导入上层包一层定时轮询：
- 每 interval 分钟读取腾讯文档最新内容
- diff 对比上次快照，只导入新增行
- SSE 推送同步结果

与 VideoMonitor 独立运行，通过数据库解耦：
  DocSync → 写入新作者/视频到 DB → VideoMonitor 自动发现并下载

方案 A：不回写 author_id，多人共用文档无冲突
"""
import logging
import threading
import time
from datetime import datetime
from typing import Optional, Set, List, Dict

from core.api.error_codes import ErrorCode
from core.api.exceptions import BizError
from core.utils.event_bus import emit

logger = logging.getLogger("doc_sync")


# ============================================================
# 工具函数
# ============================================================

def row_fingerprint(row: dict) -> str:
    """生成行指纹：author_name|search_type|search_value

    用于 diff 对比，判断行是否新增。
    方案 A：不包含 author_id（文档只读，不回写）
    """
    name = str(row.get("author_name", "")).strip()
    stype = str(row.get("search_type", "")).strip()
    svalue = str(row.get("search_value", "")).strip()
    fp = f"{name}|{stype}|{svalue}"
    logger.debug(f"[DocSync] 生成指纹: {fp}")
    return fp


def diff_new_rows(current_rows: List[dict], last_snapshot: Set[str]) -> List[dict]:
    """对比当前行与上次快照，返回新增行

    Args:
        current_rows: 本次从文档读取的行
        last_snapshot: 上次的行指纹集合

    Returns:
        新增的行列表
    """
    if not current_rows:
        logger.debug("[DocSync] diff: 当前无数据行")
        return []

    new = []
    for row in current_rows:
        fp = row_fingerprint(row)
        if fp not in last_snapshot:
            logger.debug(f"[DocSync] diff: 发现新行 fingerprint={fp}")
            new.append(row)
        else:
            logger.debug(f"[DocSync] diff: 已存在 fingerprint={fp}")

    logger.debug(f"[DocSync] diff完成: 当前 {len(current_rows)} 行, 快照 {len(last_snapshot)} 行, 新增 {len(new)} 行")
    return new


# ============================================================
# DocSyncService
# ============================================================

class DocSyncService:
    """腾讯文档实时监控同步

    用法：
        service = DocSyncService()
        service.start(doc_url=..., client_id=..., access_token=..., openid=..., interval_min=45)
        ...
        service.stop()
    """

    def __init__(self):
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._client = None
        self._snapshot: Set[str] = set()
        self._interval: int = 60  # 分钟
        self._lock = threading.Lock()
        self._last_sync_at: Optional[str] = None
        self._last_sync_result: Optional[dict] = None

    def is_running(self) -> bool:
        return self._running

    def get_status(self) -> dict:
        """获取当前监控状态"""
        return {
            "running": self._running,
            "interval_min": self._interval,
            "last_sync_at": self._last_sync_at,
            "last_sync_result": self._last_sync_result,
            "snapshot_size": len(self._snapshot),
        }

    def start(self, doc_url: str, client_id: str, access_token: str, openid: str,
              interval_min: int = 60) -> dict:
        """启动文档监控

        Args:
            doc_url: 腾讯文档 URL
            client_id: 开放平台 Client ID
            access_token: 开放平台 Access Token
            openid: 开放平台 Open ID
            interval_min: 轮询间隔（分钟），默认 60

        Returns:
            {"code": 0, "msg": ""} 或错误
        """
        with self._lock:
            if self._running:
                return ErrorCode.to_dict(ErrorCode.DOC_SYNC_ALREADY_RUNNING)

        logger.info(f"[DocSync] 启动监控请求: doc_url={doc_url[:50]}..., interval={interval_min}min")
        logger.debug(f"[DocSync] 凭证详情: client_id={client_id[:8]}..., openid={openid[:8]}...")

        # 创建腾讯文档客户端
        try:
            from core.utils.tencent_doc import TencentDocClient
            self._client = TencentDocClient(
                doc_url=doc_url,
                client_id=client_id,
                access_token=access_token,
                openid=openid,
            )
            logger.debug(f"[DocSync] 腾讯文档客户端创建成功")
        except BizError as e:
            e.log()
            return e.to_response()
        except Exception as e:
            logger.error(f"[DocSync] 创建客户端失败: {e}")
            return {"code": -1, "msg": str(e)}

        self._interval = max(5, min(interval_min, 120))
        self._running = True
        self._snapshot = set()

        self._thread = threading.Thread(
            target=self._sync_loop,
            daemon=True,
            name="doc-sync-loop",
        )
        self._thread.start()

        logger.info(f"[DocSync] 监控已启动: interval={self._interval}min, 线程={self._thread.name}")
        return {"code": 0, "msg": f"文档监控已启动，每 {self._interval} 分钟同步一次"}

    def stop(self) -> dict:
        """停止文档监控"""
        logger.info("[DocSync] 收到停止监控请求")
        with self._lock:
            if not self._running:
                logger.debug("[DocSync] 监控未运行，无需停止")
                return ErrorCode.to_dict(ErrorCode.DOC_SYNC_NOT_RUNNING)
            self._running = False

        logger.info(f"[DocSync] 监控已停止, 快照大小={len(self._snapshot)}")
        return {"code": 0, "msg": "文档监控已停止"}

    # ============================================================
    # 内部方法
    # ============================================================

    def _sync_loop(self):
        """后台轮询循环"""
        logger.info(f"[DocSync] 轮询线程启动, 间隔={self._interval}分钟")

        # 首次立即同步
        logger.debug("[DocSync] 执行首次同步")
        self._do_one_sync()

        loop_count = 0
        while self._running:
            loop_count += 1
            # 等待 interval
            logger.debug(f"[DocSync] 轮询循环 #{loop_count}: 等待 {self._interval} 分钟")
            if self._wait(self._interval * 60):
                break

            if not self._running:
                break

            logger.debug(f"[DocSync] 轮询循环 #{loop_count}: 开始同步")
            self._do_one_sync()

        logger.info(f"[DocSync] 轮询线程退出, 共执行 {loop_count} 轮同步")

    def _do_one_sync(self):
        """执行一轮同步：读文档 → diff → 导入新行"""
        if not self._client:
            logger.warning("[DocSync] 客户端未初始化，跳过同步")
            return

        sync_start = datetime.now()
        logger.info(f"[DocSync] 开始同步 #{len(self._snapshot)+1}")

        try:
            # 1. 读取文档
            logger.debug("[DocSync] 步骤1: 调用腾讯文档API读取数据")
            sheet_data = self._client.get_sheet_data()
            if sheet_data.get("code") != 0:
                logger.warning(f"[DocSync] 读取文档失败: code={sheet_data.get('code')}, msg={sheet_data.get('msg')}")
                emit("import_progress", {
                    "phase": "done",
                    "import_type": "doc_sync",
                    "new_rows": 0,
                    "error": sheet_data.get("msg", "读取失败"),
                })
                return
            logger.debug(f"[DocSync] API返回成功, data keys={list(sheet_data.get('data', {}).keys())}")

            # 2. 验证结构
            logger.debug("[DocSync] 步骤2: 验证表结构")
            validation = self._client.validate_sheet_structure(sheet_data)
            if not validation.get("valid"):
                logger.warning(f"[DocSync] 表结构验证失败: {validation.get('errors')}")
                emit("import_progress", {
                    "phase": "done",
                    "import_type": "doc_sync",
                    "new_rows": 0,
                    "error": validation.get("msg", "表结构错误"),
                })
                return
            logger.debug(f"[DocSync] 表结构验证通过, 表头={validation.get('headers', [])}")

            # 3. 解析行
            logger.debug("[DocSync] 步骤3: 解析行数据")
            rows = self._client.parse_sheet_rows(sheet_data)
            logger.debug(f"[DocSync] 解析完成, 共 {len(rows)} 行数据")

            # 4. diff
            logger.debug(f"[DocSync] 步骤4: diff对比, 快照大小={len(self._snapshot)}")
            new_rows = diff_new_rows(rows, self._snapshot)
            logger.info(f"[DocSync] 文档共 {len(rows)} 行，新增 {len(new_rows)} 行")

            if not new_rows:
                self._last_sync_at = datetime.now().isoformat()
                self._last_sync_result = {"new_rows": 0, "imported": 0, "failed": 0}
                logger.debug(f"[DocSync] 无新增行，更新快照 {len(rows)} 个指纹")
                emit("import_progress", {
                    "phase": "done",
                    "import_type": "doc_sync",
                    "new_rows": 0,
                    "total_rows": len(rows),
                })
                return

            # 5. 导入新增行
            logger.debug(f"[DocSync] 步骤5: 导入 {len(new_rows)} 个新增行")
            result = self._import_rows(new_rows)
            logger.info(f"[DocSync] 导入完成: imported={result.get('imported')}, failed={result.get('failed')}")

            # 6. 更新快照
            logger.debug("[DocSync] 步骤6: 更新快照")
            for row in rows:
                self._snapshot.add(row_fingerprint(row))

            self._last_sync_at = datetime.now().isoformat()
            self._last_sync_result = result

            sync_duration = (datetime.now() - sync_start).total_seconds()
            logger.info(f"[DocSync] 同步完成, 耗时 {sync_duration:.2f}s, 快照大小={len(self._snapshot)}")

            emit("import_progress", {
                "phase": "done",
                "import_type": "doc_sync",
                "new_rows": len(new_rows),
                "total_rows": len(rows),
                "imported": result.get("imported", 0),
                "failed": result.get("failed", 0),
            })

        except BizError as e:
            e.log()
            if e.severity == "fatal":
                logger.error(f"[DocSync] fatal 错误，停止监控: {e.error_code}")
                self._running = False
            emit("import_progress", {
                "phase": "done",
                "import_type": "doc_sync",
                "new_rows": 0,
                "error": e.detail or e.message,
                "error_code": e.error_code,
                "severity": e.severity,
            })
        except Exception as e:
            logger.error(f"[DocSync] 同步异常: {e}", exc_info=True)
            emit("import_progress", {
                "phase": "done",
                "import_type": "doc_sync",
                "new_rows": 0,
                "error": str(e),
            })

    def _import_rows(self, rows: List[dict]) -> dict:
        """导入新增行

        搜索作者 → 创建入库 → 拉取视频
        不回写 author_id（方案 A：多人共用文档无冲突）

        Returns:
            {"imported": int, "failed": int}
        """
        logger.info(f"[DocSync] 开始导入 {len(rows)} 行数据")
        imported = 0
        failed = 0

        for i, row in enumerate(rows):
            logger.debug(f"[DocSync] 导入第 {i+1}/{len(rows)} 行: {row.get('author_name', '')}")
            result = self._import_single_row(row)

            if result.get("status") in ("updated", "created"):
                imported += 1
                logger.debug(f"[DocSync] 第 {i+1} 行导入成功: status={result.get('status')}, author_id={result.get('author_id')}")
            else:
                failed += 1
                logger.warning(f"[DocSync] 第 {i+1} 行导入失败: {result.get('msg')}")

        logger.info(f"[DocSync] 批量导入完成: imported={imported}, failed={failed}")
        return {"imported": imported, "failed": failed}

    def _import_single_row(self, row: dict) -> dict:
        """导入单行：搜索作者 → 创建/更新 → 拉视频

        Args:
            row: 包含 author_name, search_type, search_value

        Returns:
            {"status": "created"/"updated"/"failed", "author_id": "...", "msg": ""}
        """
        return self._search_and_create_author(row)

    def _search_and_create_author(self, row: dict) -> dict:
        """搜索作者 + 创建入库 + 拉视频

        Returns:
            {"status": "created"/"updated"/"failed", "author_id": "...", "msg": ""}
        """
        from core.utils.database import db
        from core.utils.store import Author, AuthorVideo
        from core.service.search import SearchService

        author_name = row.get("author_name", "").strip()
        search_type = row.get("search_type", "").strip()
        search_value = row.get("search_value", "")

        logger.debug(f"[DocSync] 处理行数据: name={author_name}, type={search_type}, value={search_value}")

        if not author_name:
            logger.warning("[DocSync] 作者名为空，跳过")
            return {"status": "failed", "author_id": "", "msg": "作者名为空"}

        service = SearchService()

        logger.debug(f"[DocSync] 搜索作者: {author_name}")
        search_result = service.search_author(author_name)
        if search_result.get("code") != 0 or not search_result.get("data"):
            logger.warning(f"[DocSync] 未找到作者: {author_name}, code={search_result.get('code')}")
            return {"status": "failed", "author_id": "", "msg": f"未找到作者: {author_name}"}

        author_data = search_result["data"]
        source_author_id = author_data.get("source_author_id", "")
        logger.debug(f"[DocSync] 找到作者: name={author_data.get('name')}, source_id={source_author_id}")

        # 检查是否已存在（幂等）
        existing = db.get_author_by_source_id(source_author_id)
        if existing:
            logger.info(f"[DocSync] 作者已存在: {author_name} (id={existing.id})")
            return {"status": "updated", "author_id": existing.id, "msg": ""}

        # 拉取视频
        logger.debug(f"[DocSync] 拉取视频: type={search_type}, value={search_value}")
        if search_type == "date":
            videos_result = service.get_author_videos_before_date(source_author_id, search_value)
        else:
            try:
                pages = int(search_value) if search_value else 1
            except ValueError:
                pages = 1
            videos_result = service.get_author_videos(source_author_id, pages=pages)

        if videos_result.get("code") != 0:
            logger.warning(f"[DocSync] 获取视频失败: {author_name}, code={videos_result.get('code')}")
            return {"status": "failed", "author_id": "", "msg": f"获取视频失败: {author_name}"}

        videos = videos_result.get("data", [])
        logger.debug(f"[DocSync] 获取到 {len(videos)} 个视频")

        # 创建作者入库
        now = datetime.now().isoformat()
        author_id = f"doc_sync_{int(datetime.now().timestamp() * 1000)}"
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
        if not db.create_author(author):
            logger.error(f"[DocSync] 创建作者失败: {author_name}")
            return {"status": "failed", "author_id": "", "msg": f"创建作者失败: {author_name}"}

        # 入库视频
        logger.debug(f"[DocSync] 入库 {len(videos)} 个视频到数据库")
        for video in videos:
            author_video = AuthorVideo(
                video_id=video.get("video_id", ""),
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
            )
            db.create_author_video(author_video)

        logger.info(f"[DocSync] 创建成功: {author_name} ({len(videos)} 个视频, id={author_id})")
        return {"status": "created", "author_id": author_id, "msg": ""}

    def _wait(self, seconds: int) -> bool:
        """等待指定秒数，返回 True 表示应该退出"""
        logger.debug(f"[DocSync] 开始等待 {seconds} 秒")
        for i in range(seconds):
            if not self._running:
                logger.debug(f"[DocSync] 等待中断: 检测到停止信号 (已等待 {i} 秒)")
                return True
            time.sleep(1)
        logger.debug(f"[DocSync] 等待完成: {seconds} 秒")
        return False