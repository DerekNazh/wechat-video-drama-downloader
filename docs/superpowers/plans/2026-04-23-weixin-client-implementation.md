# WechatVideoAPIClient Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 WechatVideoAPIClient 类，封装调用微信视频号后端服务（Go）的 HTTP 接口

**Architecture:** 使用 requests 库直接调用 Go 后端 HTTP API，返回 (bool, dict) 元组或简单值

**Tech Stack:** Python, requests, logging

---

### Task 1: 创建 core/service 目录结构

**Files:**
- Create: `core/service/__init__.py`

- [ ] **Step 1: 创建目录和 __init__.py**

```python
# core/service/__init__.py
"""微信视频号后端服务 Client"""
```

- [ ] **Step 2: Commit**

---

### Task 2: 实现 WechatVideoAPIClient 类

**Files:**
- Create: `core/service/weixin_client.py`

- [ ] **Step 1: 编写 WechatVideoAPIClient 类**

```python
"""微信视频号后端服务 Client"""
import logging
import requests
from typing import Optional

logger = logging.getLogger("weixin_monitor")


class WechatVideoAPIClient:
    """微信视频号后端服务 Client"""

    def __init__(self, base_url: str = "http://127.0.0.1:2022", timeout: int = 30):
        self.base_url = base_url
        self.timeout = timeout

    def check_service(self) -> tuple[bool, dict]:
        """检查服务状态
        
        Returns:
            (是否在线, 响应数据)
        """
        try:
            resp = requests.get(
                f"{self.base_url}/api/status",
                timeout=self.timeout
            )
            data = resp.json()
            code = data.get("code", -1)
            return (code == 0, data)
        except Exception as e:
            logger.error(f"[check_service] 异常: {e}")
            return (False, {"code": -1, "msg": str(e)})

    def check_wechat(self) -> tuple[bool, dict]:
        """检查微信连接
        
        Returns:
            (是否已连接, 响应数据)
        """
        try:
            resp = requests.get(
                f"{self.base_url}/api/channels/contact/search",
                timeout=self.timeout
            )
            data = resp.json()
            code = data.get("code", -1)
            return (code == 0, data)
        except Exception as e:
            logger.error(f"[check_wechat] 异常: {e}")
            return (False, {"code": -1, "msg": str(e)})

    def create_task(self, video_id: str, object_nonce_id: str, title: str,
               path: str, spec: str) -> Optional[str]:
        """创建下载任务
        
        Args:
            video_id: 视频 ID
            object_nonce_id: 视频 objectNonceId
            title: 标题
            path: 保存路径
            spec: 视频规格
        
        Returns:
            任务 ID，失败返回 None
        """
        try:
            resp = requests.post(
                f"{self.base_url}/api/task/create",
                json={
                    "id": video_id,
                    "objectNonceId": object_nonce_id,
                    "title": title,
                    "path": path,
                    "spec": spec,
                },
                timeout=self.timeout
            )
            data = resp.json()
            if data.get("code") == 0:
                return data.get("data", {}).get("id")
            logger.warning(f"[create_task] 失��: {data.get('msg')}")
            return None
        except Exception as e:
            logger.error(f"[create_task] 异常: {e}")
            return None

    def get_task_status(self, task_id: str) -> Optional[str]:
        """查询任务状态
        
        Args:
            task_id: 任务 ID
        
        Returns:
            任务状态 (pending/running/completed/failed)，失败返回 None
        """
        try:
            resp = requests.get(
                f"{self.base_url}/api/task/profile",
                params={"id": task_id},
                timeout=self.timeout
            )
            data = resp.json()
            if data.get("code") == 0:
                return data.get("data", {}).get("status")
            return None
        except Exception as e:
            logger.error(f"[get_task_status] 异常: {e}")
            return None

    def cancel_task(self, task_id: str) -> bool:
        """取消任务
        
        Args:
            task_id: 任务 ID
        
        Returns:
            是否成功
        """
        try:
            resp = requests.post(
                f"{self.base_url}/api/task/delete",
                json={"id": task_id},
                timeout=self.timeout
            )
            data = resp.json()
            return data.get("code") == 0
        except Exception as e:
            logger.error(f"[cancel_task] 异常: {e}")
            return False

    @staticmethod
    def check_process_exists() -> bool:
        """检查下载进程是否存在
        
        Returns:
            是否存在
        """
        import subprocess
        try:
            result = subprocess.run(
                ["tasklist"],
                capture_output=True,
                text=True
            )
            return "wx_video_download.exe" in result.stdout
        except Exception:
            return False
```

- [ ] **Step 2: Commit**

```bash
git add core/service/weixin_client.py
git commit -m "feat: add WechatVideoAPIClient class"
```

---

### Task 3: 单元测试

**Files:**
- Create: `tests/unit/test_weixin_client.py`

- [ ] **Step 1: 编写测试**

```python
"""WechatVideoAPIClient 单元测试"""
import pytest
from unittest.mock import patch, MagicMock
from core.service.weixin_client import WechatVideoAPIClient


class TestWechatVideoAPIClient:
    
    def test_check_service_online(self):
        """服务在线时返回 True"""
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(json=lambda: {"code": 0, "msg": "ok"})
            client = WechatVideoAPIClient()
            result, _ = client.check_service()
            assert result is True
    
    def test_check_service_offline(self):
        """服务离线时返回 False"""
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(json=lambda: {"code": -1, "msg": "error"})
            client = WechatVideoAPIClient()
            result, _ = client.check_service()
            assert result is False
    
    def test_check_service_exception(self):
        """网络异常时返回 False"""
        with patch("requests.get") as mock_get:
            mock_get.side_effect = Exception("network error")
            client = WechatVideoAPIClient()
            result, _ = client.check_service()
            assert result is False
    
    @pytest.mark.parametrize("code,expected", [
        (0, True),
        (-1, False),
    ])
    def test_check_wechat(self, code, expected):
        """检查微信连接"""
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(json=lambda: {"code": code, "msg": "ok"})
            client = WechatVideoAPIClient()
            result, _ = client.check_wechat()
            assert result is expected
    
    def test_create_task_success(self):
        """创建任务成功返回 task_id"""
        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                json=lambda: {"code": 0, "data": {"id": "task123"}}
            )
            client = WechatVideoAPIClient()
            task_id = client.create_task(
                video_id="v1",
                object_nonce_id="o1",
                title="test",
                path="/download",
                spec="xWT111"
            )
            assert task_id == "task123"
    
    def test_create_task_failure(self):
        """创建任务失败返回 None"""
        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                json=lambda: {"code": -1, "msg": "error"}
            )
            client = WechatVideoAPIClient()
            task_id = client.create_task(
                video_id="v1",
                object_nonce_id="o1",
                title="test",
                path="/download",
                spec="xWT111"
            )
            assert task_id is None
    
    def test_get_task_status(self):
        """查询任务状态"""
        with patch("requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                json=lambda: {"code": 0, "data": {"status": "running"}}
            )
            client = WechatVideoAPIClient()
            status = client.get_task_status("task123")
            assert status == "running"
    
    def test_cancel_task_success(self):
        """取消任务成功"""
        with patch("requests.post") as mock_post:
            mock_post.return_value = MagicMock(
                json=lambda: {"code": 0, "msg": "ok"}
            )
            client = WechatVideoAPIClient()
            result = client.cancel_task("task123")
            assert result is True
```

- [ ] **Step 2: 运行测试**

```bash
pytest tests/unit/test_weixin_client.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/unit/test_weixin_client.py
git commit -m "test: add WechatVideoAPIClient unit tests"
```

---

## 集成测试补充：cancel_task 文件删除行为

**测试脚本**：`tests/集成测试/微信视频号后端服务和数据库服务/验证cancel_task是否删除本地文件.py`

**测试结论**：调用 `cancel_task` 后，**后端会删除本地已下载的视频文件**。

| 阶段 | 文件是否存在 | 文件大小 |
|------|------------|---------|
| cancel_task 前 | ✅ 是 | 4.73 MB |
| cancel_task 后 | ❌ 否 | - |

**影响**：如果需要保留已下载的视频文件，**不要调用 cancel_task**。

---

**Plan complete.**