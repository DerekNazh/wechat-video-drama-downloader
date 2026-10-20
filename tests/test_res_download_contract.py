"""res_download_service 编排契约测试（8899 黑盒 × Python 编排）

覆盖短剧嗅探服务的启动编排、配置注入（UpstreamProxy/SaveDirectory 单一事实源）、
系统代理开闭与残留自愈 —— 全部是我方 Python 代码，mock 8899 HTTP API + 注册表。

黑盒边界：res_download 对微信流量的嗅探/转发逻辑不测（外部维护，L3 冒烟）。
"""
import threading
import time

import pytest
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse


def start_res_api(state: dict):
    """在随机端口启动模拟 res_download 黑盒的服务，返回 (server, base_url)"""
    app = build_res_api_app(state)
    config = uvicorn.Config(app, host="127.0.0.1", port=0, log_level="error")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True, name="mock-res-api")
    thread.start()
    for _ in range(100):
        if server.started and server.servers and server.servers[0].sockets:
            break
        time.sleep(0.05)
    port = server.servers[0].sockets[0].getsockname()[1]
    return server, f"http://127.0.0.1:{port}"


def build_res_api_app(state: dict):
    """模拟 res_download 黑盒的 HTTP API"""
    app = FastAPI(title="mock-res-api")
    state.setdefault("config", {})
    state.setdefault("proxy_open_ok", True)
    state.setdefault("app_info_ok", True)

    @app.get("/api/app-info")
    def app_info():
        if not state["app_info_ok"]:
            return JSONResponse(status_code=500, content={})
        return JSONResponse({"status": "ok"})

    @app.get("/api/get-config")
    def get_config():
        return JSONResponse({"code": 0, "data": state["config"]})

    @app.post("/api/set-config")
    async def set_config(request: Request):
        body = await request.json()
        state["config"] = body.get("data", body)
        state.setdefault("set_calls", []).append(body)
        return JSONResponse({"code": 0})

    @app.post("/api/set-type")
    async def set_type(request: Request):
        body = await request.json()
        state.setdefault("set_type_calls", []).append(body)
        return JSONResponse({"code": 0})

    @app.get("/api/proxy-open")
    def proxy_open():
        state["proxy_open_called"] = True
        if not state["proxy_open_ok"]:
            return JSONResponse(status_code=500, content={})
        return JSONResponse({"code": 0})

    @app.get("/api/proxy-unset")
    def proxy_unset():
        state["proxy_unset_called"] = True
        return JSONResponse({"code": 0})

    return app


@pytest.fixture
def res_svc(monkeypatch):
    """注入 mock base_url 的 ResDownloadService 实例"""
    from core.utils.res_download_service import ResDownloadService
    import config.settings as cs

    svc = ResDownloadService()
    monkeypatch.setattr(cs.settings, "res_api_url", svc.service_url)
    return svc


class TestResInjectConfig:
    def test_already_configured_no_change(self, monkeypatch):
        """配置已正确 → 无需修改，返回 True"""
        upstream = "http://127.0.0.1:2023"
        from config.settings import settings
        state = {"config": {"UpstreamProxy": upstream,
                            "SaveDirectory": str(settings.short_drama_download_dir),
                            "OpenProxy": True, "AutoProxy": False}}
        _, base = start_res_api(state)
        from core.utils.res_download_service import ResDownloadService
        svc = ResDownloadService()
        svc.service_url = base
        assert svc._inject_config() is True
        assert state.get("set_calls") is None  # 未触发写操作

    def test_inject_and_verify_roundtrip(self, monkeypatch):
        """配置缺失 → 注入 + 回读校验 → True"""
        state = {"config": {}}
        _, base = start_res_api(state)
        from core.utils.res_download_service import ResDownloadService
        svc = ResDownloadService()
        svc.service_url = base
        assert svc._inject_config() is True
        # 回读校验确认目标值
        assert state["config"]["UpstreamProxy"] == "http://127.0.0.1:2023"
        assert state["config"]["OpenProxy"] is True
        assert state["config"]["AutoProxy"] is False
        assert "SaveDirectory" in state["config"]
        # set-type 也按契约调用
        assert state["set_type_calls"] and state["set_type_calls"][0] == {"type": "video"}

    def test_verify_mismatch_retries_then_false(self, monkeypatch):
        """配置接口异常（黑盒 500）→ 重试仍失败 → False（不假成功）"""
        state = {"config": {}}
        _, base = start_res_api(state)

        # 注入期间 get-config/set-config 全部返回 500（黑盒异常）
        class FakeResp500:
            status_code = 500

            def json(self):
                return {}

        import requests
        monkeypatch.setattr("requests.get",
                            lambda url, timeout=5: FakeResp500())
        from core.utils.res_download_service import ResDownloadService
        svc = ResDownloadService()
        svc.service_url = base
        assert svc._inject_config(max_retries=2) is False


class TestResProxyManagement:
    def test_recover_stale_proxy_cleans_when_service_dead(self, monkeypatch):
        """系统代理指向本应用端口但服务已死 → 自动清理（自愈）"""
        import winreg
        from core.utils.res_download_service import ResDownloadService

        class FakeKey:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_open(*a, **k):
            return FakeKey()

        def fake_query(key, name):
            if name == "ProxyEnable":
                return (1, 1)
            if name == "ProxyServer":
                return ("127.0.0.1:8899", 1)
            raise KeyError(name)

        monkeypatch.setattr(winreg, "OpenKey", fake_open)
        monkeypatch.setattr(winreg, "QueryValueEx", fake_query)
        monkeypatch.setattr(winreg, "SetValueEx", lambda key, name, *rest: None)
        # 服务已死：app-info 不可达
        import requests
        monkeypatch.setattr("requests.get",
                            lambda url, timeout=2: (_raise_conn()))
        svc = ResDownloadService()
        result = svc.recover_stale_proxy()
        assert result["changed"] is True

    def test_recover_stale_proxy_keeps_when_service_alive(self, monkeypatch):
        """系统代理指向本应用且服务存活 → 正常，不清理"""
        import winreg
        from core.utils.res_download_service import ResDownloadService

        class FakeKey:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_open(*a, **k):
            return FakeKey()

        def fake_query(key, name):
            if name == "ProxyEnable":
                return (1, 1)
            if name == "ProxyServer":
                return ("127.0.0.1:8899", 1)
            raise KeyError(name)

        monkeypatch.setattr(winreg, "OpenKey", fake_open)
        monkeypatch.setattr(winreg, "QueryValueEx", fake_query)

        class FakeResp:
            status_code = 200

            def json(self):
                return {}

        import requests
        monkeypatch.setattr("requests.get", lambda url, timeout=2: FakeResp())
        svc = ResDownloadService()
        result = svc.recover_stale_proxy()
        assert result["changed"] is False
        assert "存活" in result["reason"]

    def test_recover_stale_proxy_skips_other_proxy(self, monkeypatch):
        """系统代理指向其他代理 → 跳过（不误清）"""
        import winreg
        from core.utils.res_download_service import ResDownloadService

        class FakeKey:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_open(*a, **k):
            return FakeKey()

        def fake_query(key, name):
            if name == "ProxyEnable":
                return (1, 1)
            if name == "ProxyServer":
                return ("127.0.0.1:7890", 1)
            raise KeyError(name)

        monkeypatch.setattr(winreg, "OpenKey", fake_open)
        monkeypatch.setattr(winreg, "QueryValueEx", fake_query)
        svc = ResDownloadService()
        result = svc.recover_stale_proxy()
        assert result["changed"] is False
        assert "其他代理" in result["reason"]

    def test_open_proxy_api_ok(self, monkeypatch):
        """开启系统代理：API 优先"""
        state = {"proxy_open_ok": True}
        _, base = start_res_api(state)
        from core.utils.res_download_service import ResDownloadService
        svc = ResDownloadService()
        svc.service_url = base
        assert svc.open_proxy() is True
        assert state.get("proxy_open_called") is True

    def test_open_proxy_fallback_registry(self, monkeypatch):
        """开启系统代理：API 失败 → 回退注册表直写"""
        state = {"proxy_open_ok": False}
        _, base = start_res_api(state)

        import winreg
        calls = []

        class FakeKey:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_open(*a, **k):
            return FakeKey()

        def fake_set(key, name, *rest):
            # SetValueEx(key, name, reserved, type, value) → value 在 rest[2]
            calls.append((name, rest[2]))

        monkeypatch.setattr(winreg, "OpenKey", fake_open)
        monkeypatch.setattr(winreg, "SetValueEx", fake_set)

        from core.utils.res_download_service import ResDownloadService
        svc = ResDownloadService()
        svc.service_url = base
        assert svc.open_proxy() is True
        assert ("ProxyServer", "127.0.0.1:8899") in calls
        assert ("ProxyEnable", 1) in calls

    def test_is_running_probe(self, monkeypatch):
        """在线判定：/api/app-info 200 → True；不可达 → False"""
        state = {"app_info_ok": True}
        _, base = start_res_api(state)
        from core.utils.res_download_service import ResDownloadService
        svc = ResDownloadService()
        svc.service_url = base
        assert svc.is_running() is True
        monkeypatch.setattr("requests.get", lambda url, timeout=2: (_raise_conn()))
        assert svc.is_running() is False


def _raise_conn():
    raise ConnectionRefusedError("mock: res_download not running")
