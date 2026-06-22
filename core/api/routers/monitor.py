"""监控 API 路由"""
import logging
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from core.monitor.monitor import MonitorService
from core.utils.database import db
from core.api.deps import require_wechat

logger = logging.getLogger("api_monitor")

router = APIRouter(
    prefix="/api/monitor",
    tags=["monitor"],
    dependencies=[Depends(require_wechat)],
)


@router.post("/start")
def start_monitor():
    """一键启动视频监控"""
    try:
        service = MonitorService(db)
        result = service.start_monitor()
        return {"code": 0, "data": result, "msg": ""}
    except Exception as e:
        logger.error(f"[start_monitor] 启动失败: {e}")
        return {"code": -1, "msg": str(e)}


@router.post("/stop")
def stop_monitor():
    """一键停止视频监控"""
    try:
        service = MonitorService(db)
        result = service.stop_monitor()
        return {"code": 0, "data": result, "msg": ""}
    except Exception as e:
        logger.error(f"[stop_monitor] 停止失败: {e}")
        return {"code": -1, "msg": str(e)}


# ============================================================
# 腾讯文档监控
# ============================================================

_doc_sync_service = None


class DocSyncStartRequest(BaseModel):
    doc_url: str = ""
    client_id: str = ""
    access_token: str = ""
    openid: str = ""
    interval_min: int = 60


@router.post("/doc-sync/start")
def start_doc_sync(request: DocSyncStartRequest):
    """启动腾讯文档实时监控

    每 interval_min 分钟轮询文档，diff 新增行自动导入。
    """
    global _doc_sync_service

    logger.info(f"[API] 收到启动腾讯文档监控请求: interval={request.interval_min}min")
    logger.debug(f"[API] 请求详情: doc_url={request.doc_url[:50]}..., client_id={request.client_id[:8]}...")

    if not request.doc_url:
        logger.warning("[API] 启动失败: 缺少文档URL")
        return {"code": -1, "error_code": "DOC_URL_INVALID", "msg": "请提供腾讯文档 URL"}

    if not request.client_id or not request.access_token or not request.openid:
        logger.warning("[API] 启动失败: 凭证不完整")
        return {"code": -1, "error_code": "DOC_CREDENTIAL_MISSING", "msg": "请提供完整凭证"}

    # 检查微信视频号后端服务 + 客户端连接
    from core.utils.weixin_client import WechatVideoAPIClient
    wx_client = WechatVideoAPIClient()
    service_online = wx_client.check_service()
    if not service_online:
        logger.warning("[API] 启动失败: 微信视频号后端服务未启动")
        return {"code": -1, "error_code": "WECHAT_SERVICE_OFFLINE", "msg": "微信视频号后端服务未启动，请先启动服务"}

    wechat_connected = wx_client.check_wechat_connected()
    if not wechat_connected:
        logger.warning("[API] 启动失败: 微信客户端未连接")
        return {"code": -1, "error_code": "WECHAT_NOT_CONNECTED", "msg": "微信客户端未连接，请先登录微信"}

    from core.monitor.doc_sync import DocSyncService

    if _doc_sync_service is None:
        logger.debug("[API] 创建新的 DocSyncService 实例")
        _doc_sync_service = DocSyncService()

    result = _doc_sync_service.start(
        doc_url=request.doc_url,
        client_id=request.client_id,
        access_token=request.access_token,
        openid=request.openid,
        interval_min=request.interval_min,
    )
    logger.info(f"[API] 启动结果: code={result.get('code')}, msg={result.get('msg', '')}")
    return result


@router.post("/doc-sync/stop")
def stop_doc_sync():
    """停止腾讯文档实时监控"""
    global _doc_sync_service

    logger.info("[API] 收到停止腾讯文档监控请求")

    if _doc_sync_service is None:
        logger.warning("[API] 停止失败: 服务未初始化")
        return {"code": -1, "error_code": "DOC_SYNC_NOT_RUNNING", "msg": "文档监控未启动"}

    result = _doc_sync_service.stop()
    logger.info(f"[API] 停止结果: code={result.get('code')}")
    return result


@router.get("/doc-sync/status")
def doc_sync_status():
    """查看腾讯文档监控状态"""
    global _doc_sync_service

    if _doc_sync_service is None:
        logger.debug("[API] 查询状态: 服务未初始化")
        return {"code": 0, "data": {"running": False, "interval_min": 60}}

    return {"code": 0, "data": _doc_sync_service.get_status()}