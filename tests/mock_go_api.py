"""模拟微信视频号后端 (wx_video_download.exe / Go 黑盒) 的 HTTP API

用途：编排契约测试 —— 覆盖我方 Python 代码与黑盒 Go 的交互契约：
- GET /api/status             → 服务在线判定（code / channels.available）
- GET /api/channels/contact/search → 微信连接判定（code==0 已连接）
- POST /api/task/create2      → 创建下载任务（记录请求体供断言）
- POST /api/task/delete       → 取消任务
- GET /api/task/list          → 任务列表（可配置）

黑盒 Go 的外部维护约定：我们只测"我方代码与它的契约"，不测解密逻辑本身。
"""
import json
import threading
import time

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


def build_go_api_app(state: dict):
    """按 state 构造可配置的假 Go 后端

    state 支持键：
      status_code   (int)   /api/status 的 code（0=在线）
      available     (bool)  channels.available（证书状态，已知不可靠字段）
      wechat_code   (int)   /api/channels/contact/search 的 code（0=微信已连接）
      tasks         (list)  /api/task/list 返回的任务列表
    state 记录：
      created       (list)  create2 收到的请求体
      cancelled     (list)  delete 收到的请求体
    """
    app = FastAPI(title="mock-go-api")

    @app.get("/api/status")
    def status():
        return JSONResponse({
            "code": state.get("status_code", 0),
            "data": {"channels": {"available": state.get("available", True)},
                     "version": "mock-go"},
        })

    @app.get("/api/channels/contact/search")
    def search(keyword: str = ""):
        if state.get("wechat_code", 0) != 0:
            return JSONResponse({
                "code": state["wechat_code"], "msg": "wechat not connected",
                "data": {"data": {"infoList": [], "lastBuff": ""}},
            })
        return JSONResponse({
            "code": 0,
            "data": {"data": {"infoList": [{"id": "c1", "nickname": keyword}],
                              "lastBuff": ""}},
        })

    @app.post("/api/task/create2")
    async def create2(request: Request):
        body = await request.json()
        state.setdefault("created", []).append(body)
        tid = f"mock-task-{len(state['created'])}"
        return JSONResponse({"code": 0, "data": {"id": tid}, "msg": ""})

    @app.post("/api/task/delete")
    async def delete(request: Request):
        body = await request.json()
        state.setdefault("cancelled", []).append(body)
        return JSONResponse({"code": 0, "msg": ""})

    @app.get("/api/task/list")
    def task_list():
        return JSONResponse({"code": 0, "data": {"list": state.get("tasks", [])}})

    return app


def start_mock_go_api(state: dict):
    """在随机端口启动假 Go 后端，返回 (server, base_url)"""
    app = build_go_api_app(state)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True, name="mock-go-api")
    thread.start()
    for _ in range(100):
        if server.started and server.servers and server.servers[0].sockets:
            break
        time.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    return server, f"http://127.0.0.1:{port}"
