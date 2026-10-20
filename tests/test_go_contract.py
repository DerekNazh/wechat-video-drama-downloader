"""编排契约测试：我方 Python 代码 × 黑盒 Go（wx_video_download）交互契约

覆盖视频号主链路"我方那一段"（之前完全没有测试的最大空白）：
1. WechatVideoAPIClient 对 Go API 的调用契约（在线/离线/异常分支）
2. MonitorService 微信连接自愈语义（未连→等待不退出；连上→自动开始同步）
3. GO 离线防抖 + 恢复断点续传
4. link_status 四节点健康采集逻辑

黑盒边界（本文件不测、也无法自动化测）：
- Go 的 MITM 解密正确性 → 需真实微信流量，发版前 L3 冒烟
"""
import threading
import time

import pytest

from tests.mock_go_api import start_mock_go_api


# ---------------------------------------------------------------- Go API 契约

class TestGoAPIContract:
    """WechatVideoAPIClient 与 Go HTTP API 的交互契约"""

    def test_check_service_online(self):
        state = {"status_code": 0, "available": True}
        _, base = start_mock_go_api(state)
        from core.utils.weixin_client import WechatVideoAPIClient
        client = WechatVideoAPIClient(base_url=base, timeout=3)
        assert client.check_service() is True

    def test_check_service_code_nonzero_is_offline(self):
        state = {"status_code": -1}
        _, base = start_mock_go_api(state)
        from core.utils.weixin_client import WechatVideoAPIClient
        client = WechatVideoAPIClient(base_url=base, timeout=3)
        assert client.check_service() is False

    def test_check_service_available_false_not_fatal(self):
        """channels.available=false 是已知不可靠字段（Go 源码 bug 注释），
        不应判为故障，只留日志 —— 与 weixin_client 现状语义一致"""
        state = {"status_code": 0, "available": False}
        _, base = start_mock_go_api(state)
        from core.utils.weixin_client import WechatVideoAPIClient
        client = WechatVideoAPIClient(base_url=base, timeout=3)
        assert client.check_service() is True

    def test_check_service_unreachable(self):
        """后端不可达（端口未监听）→ False 且不抛异常"""
        from core.utils.weixin_client import WechatVideoAPIClient
        client = WechatVideoAPIClient(base_url="http://127.0.0.1:1", timeout=1)
        assert client.check_service() is False

    def test_wechat_connected_true(self):
        state = {"wechat_code": 0}
        _, base = start_mock_go_api(state)
        from core.utils.weixin_client import WechatVideoAPIClient
        client = WechatVideoAPIClient(base_url=base, timeout=3)
        assert client.check_wechat_connected() is True

    def test_wechat_connected_false(self):
        state = {"wechat_code": -1}
        _, base = start_mock_go_api(state)
        from core.utils.weixin_client import WechatVideoAPIClient
        client = WechatVideoAPIClient(base_url=base, timeout=3)
        assert client.check_wechat_connected() is False

    def test_wechat_unreachable_not_raise(self):
        from core.utils.weixin_client import WechatVideoAPIClient
        client = WechatVideoAPIClient(base_url="http://127.0.0.1:1", timeout=1)
        assert client.check_wechat_connected() is False

    def test_create_task_contract(self):
        """download_video 必须以 Go 契约格式 POST /api/task/create2"""
        state = {}
        _, base = start_mock_go_api(state)
        from core.utils.weixin_client import WechatVideoAPIClient
        client = WechatVideoAPIClient(base_url=base, timeout=3)
        result = client.download_video(
            video_id="v123", url="https://finder.video.qq.com/x.mp4",
            title="测试视频", spec="1080p", key=12345,
            author_name="作者A", create_time="2026-10-20T10:00:00",
            video_type="short_video")
        assert result.get("code") == 0
        assert result.get("data", {}).get("id")
        body = state["created"][0]
        assert body["url"] == "https://finder.video.qq.com/x.mp4"
        assert body["extra"]["id"] == "v123"
        assert body["extra"]["key"] == "12345"
        assert body["extra"]["suffix"] == ".mp4"
        # 文件名契约：日期_标题_规格_ID.mp4
        assert body["filename"] == "2026-10-20_测试视频_1080p_v123.mp4"
        # 目录契约：作者/类型（短剧视频归"短视频"）
        assert body["dir"] == "作者A/短视频"

    def test_cancel_task_contract(self):
        state = {}
        _, base = start_mock_go_api(state)
        from core.utils.weixin_client import WechatVideoAPIClient
        client = WechatVideoAPIClient(base_url=base, timeout=3)
        assert client.cancel_task("task-1") is True
        assert state["cancelled"][0] == {"id": "task-1"}

    def test_list_download_tasks_contract(self):
        state = {"tasks": [{"id": "t1", "status": "done", "save_path": "C:/v.mp4"}]}
        _, base = start_mock_go_api(state)
        from core.utils.weixin_client import WechatVideoAPIClient
        client = WechatVideoAPIClient(base_url=base, timeout=3)
        tasks = client.list_download_tasks()
        assert len(tasks) == 1
        assert tasks[0]["id"] == "t1"


# ---------------------------------------------------------------- 监控自愈语义

class TestMonitorSelfHeal:
    """MonitorService._monitor_loop 的微信连接自愈语义"""

    def test_waits_when_wechat_offline_then_works_when_connected(self, monkeypatch):
        """未连→等待重试（不退出、不同步）；连上→自动开始同步（生命周期自动化核心）"""
        import core.monitor.monitor as mon
        from core.monitor.monitor import MonitorService

        sync_started = threading.Event()
        sync_calls = {"n": 0}

        class FakeWx:
            def __init__(self):
                self.checks = 0
                self.connected = False

            def check_wechat_connected(self):
                self.checks += 1
                if self.checks >= 3:  # 前 2 轮未连接，之后连上
                    self.connected = True
                return self.connected

        class FakeVideo:
            def add_all_authors_latest_videos(self):
                sync_calls["n"] += 1
                sync_started.set()
                return {"added": 0}

        class FakeDB:
            def list_authors(self):
                return []

            def list_author_videos(self, author_id):
                return []

        class FakeTask:
            def get_downloading_tasks(self):
                return []

        monkeypatch.setattr("core.utils.weixin_client.WechatVideoAPIClient", FakeWx)
        svc = MonitorService(db=FakeDB(), video_service_cls=FakeVideo,
                             task_service_cls=FakeTask, event_bus=None)
        # 缩短等待，让循环快跑（不改变语义，只加速）
        monkeypatch.setattr(svc, "_wait_or_stop", lambda s: time.sleep(0.01))

        mon._monitor_running = True
        t = threading.Thread(target=svc._monitor_loop, daemon=True)
        t.start()
        try:
            assert sync_started.wait(5), "微信连上后应自动开始同步（自愈）"
            assert sync_calls["n"] >= 1
        finally:
            mon._monitor_running = False
            t.join(timeout=5)
        assert not t.is_alive(), "停止信号后监控线程应退出"

    def test_go_offline_debounce(self, monkeypatch):
        """GO 离线事件防抖：3 秒内恢复不暂停，持续离线才暂停"""
        from core.monitor.monitor import MonitorService

        svc = MonitorService(db=None, event_bus=None)
        svc._OFFLINE_DEBOUNCE_SEC = 0.05  # 缩短防抖窗口加速测试（语义不变）

        svc._on_go_offline()
        assert svc._paused is False, "防抖窗口内不应暂停"
        time.sleep(0.2)
        assert svc._paused is True, "持续离线超过防抖窗口应暂停"

    def test_go_online_resumes_and_resumes_pending(self, monkeypatch):
        """GO 恢复：取消暂停 + 触发断点续传（resume_pending_tasks）

        产品语义（2026-10-21 实测核对）：_on_go_online 无论是否防抖窗口内恢复
        都会触发续传 —— Go 恢复后恢复 pending 任务始终安全，无需区分瞬断。
        """
        from core.monitor.monitor import MonitorService

        resumed = {"called": False}

        def fake_resume():
            resumed["called"] = True
            return {"resumed": 2, "failed": 0}

        monkeypatch.setattr("core.service.task.resume_pending_tasks", fake_resume)
        svc = MonitorService(db=None, event_bus=None)
        svc._OFFLINE_DEBOUNCE_SEC = 0.05

        svc._on_go_offline()
        svc._on_go_online()  # 防抖窗口内恢复
        assert svc._paused is False
        assert resumed["called"] is True, "Go 恢复即触发断点续传（产品语义）"

        svc._on_go_offline()
        time.sleep(0.2)  # 持续离线 → 已暂停
        assert svc._paused is True
        svc._on_go_online()  # 之后恢复 → 同样触发续传
        assert svc._paused is False
        assert resumed["called"] is True


# ---------------------------------------------------------------- link_status

class TestLinkStatus:
    """link_status._collect_link_status 四节点健康采集逻辑"""

    @staticmethod
    def _monkeypatch_probes(monkeypatch, socket_open=True, res_api_ok=True,
                            go_api_code=0, proxy_server="127.0.0.1:8899",
                            proxy_enable=1):
        import core.api.routers.link_status as ls

        class _FakeSock:
            """支持 with 上下文协议（link_status 用 with socket.create_connection(...)）"""
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_connect(addr, timeout=1.0):
            if not socket_open:
                raise ConnectionRefusedError("mock: port closed")
            return _FakeSock()

        monkeypatch.setattr("socket.create_connection", fake_connect)

        class FakeResp:
            def __init__(self, status_code, json_body):
                self.status_code = status_code
                self._json = json_body

            def json(self):
                return self._json

        def fake_get(url, timeout=1.5):
            if "api/app-info" in url:
                return FakeResp(200 if res_api_ok else 500, {})
            if url.endswith("/api/status"):
                return FakeResp(200, {"code": go_api_code})
            raise AssertionError(f"unexpected url: {url}")

        monkeypatch.setattr("requests.get", fake_get)

        class FakeKey:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        def fake_open_key(*a, **k):
            return FakeKey()

        def fake_query_value(key, name):
            if name == "ProxyEnable":
                return (proxy_enable, 1)
            if name == "ProxyServer":
                return (proxy_server, 1)
            raise KeyError(name)

        import winreg
        monkeypatch.setattr(winreg, "OpenKey", fake_open_key)
        monkeypatch.setattr(winreg, "QueryValueEx", fake_query_value)
        return ls

    def test_all_nodes_up(self, monkeypatch):
        ls = self._monkeypatch_probes(monkeypatch)
        status = ls._collect_link_status()
        assert status["res_download"] == "up"
        assert status["upstream"] == "up"
        assert status["go_api"] == "up"
        assert status["system_proxy"] == "enabled"

    def test_go_api_down_when_code_nonzero(self, monkeypatch):
        ls = self._monkeypatch_probes(monkeypatch, go_api_code=-1)
        status = ls._collect_link_status()
        assert status["go_api"] == "down"

    def test_res_download_down(self, monkeypatch):
        ls = self._monkeypatch_probes(monkeypatch, res_api_ok=False)
        status = ls._collect_link_status()
        assert status["res_download"] == "down"

    def test_upstream_down_when_port_closed(self, monkeypatch):
        ls = self._monkeypatch_probes(monkeypatch, socket_open=False)
        status = ls._collect_link_status()
        assert status["upstream"] == "down"

    def test_system_proxy_points_elsewhere(self, monkeypatch):
        ls = self._monkeypatch_probes(monkeypatch, proxy_server="127.0.0.1:7890")
        status = ls._collect_link_status()
        assert status["system_proxy"] == "other"


def _raise_conn_refused():
    raise ConnectionRefusedError("mock: port closed")
