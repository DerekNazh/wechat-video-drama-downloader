"""真实视频源模拟服务器（严格模拟短剧 CDN 行为）

设计原则：不能太假。
- 提供真实 mp4 文件（ffmpeg 生成，带画面+音轨）
- 真实 HTTP 响应头：Content-Type: video/mp4、Content-Length、Accept-Ranges
- 防盗链校验：Referer 必须等于请求自身 origin（模拟视频号 CDN 行为）
- 特定场景路由模拟真实故障：404（失效链接）/ 0字节（空内容）/ 慢速（超时）/
  CDN 签名防盗链拒绝（403）
- 请求计数：验证"重复下载不重新请求"（严格：命中已存在 = 零网络请求）

用法：
    from tests.mock_video_server import start_server, stop_server, get_counter
"""
from __future__ import annotations

import threading
import time
import json
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, RedirectResponse, Response, StreamingResponse

PORT = 19099
ORIGIN = f"http://127.0.0.1:{PORT}"
# 模拟"真实 CDN 签名防盗链"：要求 Referer 必须是指定站点
CDN_REQUIRED_REFERER = "https://real-cdn.example.com/"

# 每个 video_id 的请求计数（线程安全）
_COUNTER: dict[str, int] = {}
_COUNTER_LOCK = threading.Lock()


def _count(video_id: str):
    with _COUNTER_LOCK:
        _COUNTER[video_id] = _COUNTER.get(video_id, 0) + 1


def get_counter(video_id: str) -> int:
    with _COUNTER_LOCK:
        return _COUNTER.get(video_id, 0)


def reset_counter():
    with _COUNTER_LOCK:
        _COUNTER.clear()


def _check_referer(request: Request) -> bool:
    """防盗链：Referer 必须等于本服务器 origin（模拟视频号 CDN）"""
    return request.headers.get("referer", "") == ORIGIN


def build_app(mp4_path: Path) -> FastAPI:
    app = FastAPI(title="mock-video-cdn")

    @app.get("/drama1/video1/video.mp4")
    async def video1(request: Request):
        _count("video1")
        if not _check_referer(request):
            return Response(status_code=403, content="hotlink denied")
        return FileResponse(
            str(mp4_path),
            media_type="video/mp4",
            headers={"Accept-Ranges": "bytes", "Cache-Control": "private"},
        )

    @app.get("/drama1/video2/video.mp4")
    async def video2(request: Request):
        _count("video2")
        return Response(status_code=404, content="not found")

    @app.get("/drama1/video3/video.mp4")
    async def video3(request: Request):
        _count("video3")
        return Response(status_code=200, content=b"", media_type="video/mp4")

    @app.get("/drama1/video4/video.mp4")
    async def video4(request: Request):
        """慢速响应：模拟网络拥塞/卡住的上游（配合短超时触发 502）"""
        _count("video4")
        time.sleep(6)
        return FileResponse(str(mp4_path), media_type="video/mp4")

    @app.get("/drama1/video5/video.mp4")
    async def video5(request: Request):
        """防盗链签名校验：Referer 必须是 CDN 站点，模拟真实 CDN 拒绝"""
        _count("video5")
        if request.headers.get("referer", "") != CDN_REQUIRED_REFERER:
            return Response(status_code=403, content="invalid referer")
        return FileResponse(str(mp4_path), media_type="video/mp4")

    @app.get("/drama1/video7/video.mp4")
    async def video7(request: Request):
        """正常视频：供序号/0字节残留等组合场景使用"""
        _count("video7")
        if not _check_referer(request):
            return Response(status_code=403, content="hotlink denied")
        return FileResponse(str(mp4_path), media_type="video/mp4")

    @app.get("/drama1/video8/video.mp4")
    async def video8(request: Request):
        """正常视频：供 0 字节残留重下场景使用（与已下载视频隔离）"""
        _count("video8")
        if not _check_referer(request):
            return Response(status_code=403, content="hotlink denied")
        return FileResponse(str(mp4_path), media_type="video/mp4")

    @app.get("/drama1/video9/video.mp4")
    async def video9(request: Request):
        """防盗链 302：模拟真实 CDN 被拒时重定向到提示页（阿里云 CDN 行为）

        follow_redirects=True 的下载器会跟到 HTML 页 → Content-Type 闸门必须拒绝，
        不能把 HTML 当 mp4 保存（否则前端假成功）。
        """
        _count("video9")
        return RedirectResponse(url="/login.html", status_code=302)

    @app.get("/drama1/video10/video.mp4")
    async def video10(request: Request):
        """中途断开（badhttp 风格）：声明 Content-Length=100000 只发 500 字节

        客户端若信任 Content-Length 不检查短读会拿到半截文件；
        流式下载器必须因连接提前结束而失败并清理残留。
        """
        _count("video10")
        async def partial():
            yield b"x" * 500
        headers = {"Content-Type": "video/mp4", "Content-Length": "100000"}
        return StreamingResponse(partial(), headers=headers)

    @app.get("/login.html")
    async def login_page():
        """302 重定向目标：登录/提示页（HTML）"""
        return Response(content="<html><body>请登录后观看</body></html>",
                        media_type="text/html")

    @app.get("/probe")
    async def probe(request: Request):
        """会话标记探测：验证流量真的穿过本机代理链到达本服务器

        代理实穿验证（行业实践：用 IP 回显/会话标记确认流量确实过代理）：
        请求带 marker 参数，若响应中 marker 回显一致，说明请求真的到达了
        mock 服务器（而非被拦截页/错误页吞掉）。
        """
        marker = request.query_params.get("marker", "")
        return Response(content=json.dumps({"ok": True, "marker": marker,
                                            "server": "mock-video-cdn"}),
                        media_type="application/json")

    return app


_server_ref: dict = {"thread": None, "config": None}


def start_server(mp4_path: Path) -> None:
    """在后台线程启动 uvicorn（daemon，随进程退出）"""
    if _server_ref["thread"] and _server_ref["thread"].is_alive():
        return
    app = build_app(mp4_path)
    config = uvicorn.Config(app, host="127.0.0.1", port=PORT, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True, name="mock-video-cdn")
    thread.start()
    _server_ref["thread"] = thread
    _server_ref["server"] = server
    # 等待端口就绪（最多 5 秒）
    import socket
    deadline = time.time() + 5
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=0.5):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError("mock video server failed to start")


def stop_server() -> None:
    server = _server_ref.get("server")
    if server:
        server.should_exit = True
        time.sleep(0.5)
    _server_ref["thread"] = None
    _server_ref["server"] = None
