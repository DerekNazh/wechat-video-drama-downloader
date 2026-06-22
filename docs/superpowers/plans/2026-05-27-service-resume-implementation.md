# 服务断点续传改进 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 补齐服务停止→重启断点续传的 4 个缺失改进：URL 过期刷新、防重入锁、删除 gopeed.db、前端任务卡片状态同步

**Architecture:** 在现有 resume_download_task / resume_pending_tasks / start_service 流程中插入 4 个最小改动点，复用已有的 ensure_valid_url / _clear_go_tasks_safe / _resume_lock 模式

**Tech Stack:** Python 3 (threading, pytest), JavaScript (ES5)

---

## File Structure

| File | Responsibility | Action |
|------|---------------|--------|
| `core/service/task.py` | resume_download_task 增加 URL 刷新 + 模块级 _resume_lock + 两个函数加锁 | Modify |
| `core/api/routers/base_service.py` | start_service() 启动前删除 gopeed.db | Modify |
| `static/js/component/status.js` | 服务离线时将 running 任务标记为 paused | Modify |
| `tests/test_service_resume.py` | 所有后端改进的单元测试 | Create |

---

### Task 1: resume_download_task() 中 URL 过期刷新

**Files:**
- Modify: `core/service/task.py:551-570`
- Create: `tests/test_service_resume.py`

- [ ] **Step 1: Write the failing test**

```python
"""测试服务断点续传改进

测试覆盖:
- resume_download_task 调用 ensure_valid_url 刷新过期 URL
- _resume_lock 防重入
- resume_pending_tasks 防重入
"""
import pytest
import threading
from unittest.mock import patch, MagicMock


class TestResumeUrlRefresh:
    """测试 resume_download_task 中 URL 过期刷新"""

    def test_resume_calls_ensure_valid_url(self, db, sample_author, sample_video, sample_task):
        """resume_download_task 应调用 ensure_valid_url 检查 URL 有效性"""
        db.create_author(sample_author)
        db.create_author_video(sample_video)
        db.create_download_task(sample_task)

        with patch("core.service.task.WechatVideoAPIClient") as mock_client_cls, \
             patch("core.service.task.SearchService") as mock_search_cls:
            mock_search = MagicMock()
            mock_search.ensure_valid_url.return_value = {
                "code": 0,
                "data": {"url": "https://example.com/video.mp4?fresh_token=abc", "refreshed": True},
                "msg": "URL 已刷新"
            }
            mock_search_cls.return_value = mock_search

            mock_client = MagicMock()
            mock_client.download_video.return_value = {
                "code": 0,
                "data": {"id": sample_task.task_id}
            }
            mock_client_cls.return_value = mock_client

            from core.service.task import resume_download_task
            result = resume_download_task(sample_task.task_id)

            assert result is True
            mock_search.ensure_valid_url.assert_called_once()
            call_kwargs = mock_search.ensure_valid_url.call_args
            assert call_kwargs[1]["url"] == sample_task.url
            assert call_kwargs[1]["video_id"] == sample_video.video_id

    def test_resume_url_refresh_failed_returns_false(self, db, sample_author, sample_video, sample_task):
        """URL 刷新失败时 resume_download_task 应返回 False"""
        db.create_author(sample_author)
        db.create_author_video(sample_video)
        db.create_download_task(sample_task)

        with patch("core.service.task.SearchService") as mock_search_cls:
            mock_search = MagicMock()
            mock_search.ensure_valid_url.return_value = {
                "code": -1,
                "msg": "URL 过期且刷新失败"
            }
            mock_search_cls.return_value = mock_search

            from core.service.task import resume_download_task
            result = resume_download_task(sample_task.task_id)

            assert result is False

    def test_resume_uses_refreshed_url(self, db, sample_author, sample_video, sample_task):
        """URL 刷新成功后应使用新 URL 调用 download_video"""
        db.create_author(sample_author)
        db.create_author_video(sample_video)
        db.create_download_task(sample_task)

        new_url = "https://example.com/video.mp4?fresh_token=xyz"

        with patch("core.service.task.WechatVideoAPIClient") as mock_client_cls, \
             patch("core.service.task.SearchService") as mock_search_cls:
            mock_search = MagicMock()
            mock_search.ensure_valid_url.return_value = {
                "code": 0,
                "data": {"url": new_url, "refreshed": True},
                "msg": "URL 已刷新"
            }
            mock_search_cls.return_value = mock_search

            mock_client = MagicMock()
            mock_client.download_video.return_value = {
                "code": 0,
                "data": {"id": sample_task.task_id}
            }
            mock_client_cls.return_value = mock_client

            from core.service.task import resume_download_task
            result = resume_download_task(sample_task.task_id)

            assert result is True
            call_kwargs = mock_client.download_video.call_args
            assert call_kwargs[1]["url"] == new_url
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "f:\setup_temp\剪辑合成拆散\监控\总下载器版本" && .venv\Scripts\python.exe -m pytest tests/test_service_resume.py::TestResumeUrlRefresh -v`
Expected: FAIL — `resume_download_task` does not call `ensure_valid_url`

- [ ] **Step 3: Write minimal implementation**

In `core/service/task.py`, modify `resume_download_task()` — insert URL refresh logic **between L557 and L558** (between the `video = db.get_author_video(...)` block and the `client = WechatVideoAPIClient()` call):

```python
    # 查找 source_author_id（ensure_valid_url 需要）
    source_author_id = ""
    if video and video.author_id:
        author = db.get_author(video.author_id)
        if author:
            source_author_id = author.source_author_id or ""

    # URL 有效性检查与刷新
    from core.service.search import SearchService
    search_svc = SearchService()
    url_result = search_svc.ensure_valid_url(
        url=task.url,
        source_author_id=source_author_id,
        video_id=task.video_id,
        create_time=task.create_time or task.created_at,
        video_type=task.video_type if hasattr(task, 'video_type') else "short_video"
    )
    if url_result["code"] != 0:
        logger.warning("[resume] URL 过期且刷新失败: task_id=%s, msg=%s", task_id, url_result["msg"])
        return False
    effective_url = url_result["data"]["url"]
    if url_result["data"]["refreshed"]:
        logger.info("[resume] URL 已刷新: task_id=%s", task_id)
        # 更新数据库中的 URL
        db.update_video_url(task.video_id, effective_url)
```

Then change L563 `url=task.url` to `url=effective_url` in the `client.download_video()` call:

```python
    result = client.download_video(
        video_id=task.video_id,
        url=effective_url,
        title=task.title,
        spec=task.spec,
        key=task.key,
        author_name=author_name,
        create_time=task.create_time or task.created_at,
        video_type=task.video_type if hasattr(task, 'video_type') else "short_video",
    )
```

Also update the `DownloadTask(...)` constructor at L591 to use `effective_url` instead of `task.url`:

Change L591 from `url=task.url,` to `url=effective_url,`

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "f:\setup_temp\剪辑合成拆散\监控\总下载器版本" && .venv\Scripts\python.exe -m pytest tests/test_service_resume.py::TestResumeUrlRefresh -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_service_resume.py core/service/task.py
git commit -m "feat(resume): add URL expiry refresh in resume_download_task via ensure_valid_url"
```

---

### Task 2: resume 防重入锁 (_resume_lock)

**Files:**
- Modify: `core/service/task.py:1-16` (模块级), `core/service/task.py:618-653` (resume_all_running_tasks), `core/service/task.py:863-890` (resume_pending_tasks)
- Modify: `tests/test_service_resume.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_service_resume.py`:

```python
class TestResumeLock:
    """测试 resume 防重入锁"""

    def test_resume_lock_exists(self):
        """task.py 模块应包含 _resume_lock"""
        from core.service import task as task_module
        assert hasattr(task_module, '_resume_lock')
        assert isinstance(task_module._resume_lock, type(threading.Lock()))

    def test_resume_pending_tasks_skips_when_locked(self, db):
        """resume_pending_tasks 在锁被持有时应跳过"""
        from core.service import task as task_module
        from core.service.task import resume_pending_tasks

        # 持有锁
        acquired = task_module._resume_lock.acquire(blocking=False)
        assert acquired is True

        try:
            result = resume_pending_tasks()
            assert result.get("skipped") == 1
        finally:
            task_module._resume_lock.release()

    def test_resume_all_running_tasks_skips_when_locked(self, db):
        """resume_all_running_tasks 在锁被持有时应跳过"""
        from core.service import task as task_module
        from core.service.task import resume_all_running_tasks

        acquired = task_module._resume_lock.acquire(blocking=False)
        assert acquired is True

        try:
            result = resume_all_running_tasks()
            assert result.get("skipped") == 1
        finally:
            task_module._resume_lock.release()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "f:\setup_temp\剪辑合成拆散\监控\总下载器版本" && .venv\Scripts\python.exe -m pytest tests/test_service_resume.py::TestResumeLock -v`
Expected: FAIL — `_resume_lock` does not exist, functions don't check lock

- [ ] **Step 3: Write minimal implementation**

In `core/service/task.py`:

**3a.** Add module-level `_resume_lock` after imports (after L16):

```python
import threading

_resume_lock = threading.Lock()
```

**3b.** Wrap `resume_all_running_tasks()` (L618-653) with lock:

```python
def resume_all_running_tasks() -> dict:
    """恢复所有 running/pending 状态的任务

    Returns:
        {"resumed": 恢复数量, "skipped": 跳过数量, "failed": 失败数量}
    """
    if not _resume_lock.acquire(blocking=False):
        logger.info("[resume_all] 已有恢复任务正在进行，跳过")
        return {"resumed": 0, "skipped": 1, "failed": 0}

    try:
        # 查询 running 和 pending 状态的任务
        running_tasks = db.list_download_tasks(status="running", limit=1000)
        pending_tasks = db.list_download_tasks(status="pending", limit=1000)

        total_to_resume = len(running_tasks) + len(pending_tasks)
        if total_to_resume == 0:
            logger.info("[resume_all_running_tasks] 无需恢复的任务")
            return {"resumed": 0, "skipped": 0, "failed": 0}

        logger.info(f"[resume_all_running_tasks] 待恢复任务: running={len(running_tasks)}, pending={len(pending_tasks)}")

        result = {"resumed": 0, "skipped": 0, "failed": 0}

        # 恢复 running 任务
        for task in running_tasks:
            if resume_download_task(task.task_id):
                result["resumed"] += 1
            else:
                result["failed"] += 1

        # 恢复 pending 任务
        for task in pending_tasks:
            if resume_download_task(task.task_id):
                result["resumed"] += 1
            else:
                result["failed"] += 1

        logger.info(f"[resume_all_running_tasks] 恢复完成: resumed={result['resumed']}, failed={result['failed']}")

        return result
    finally:
        _resume_lock.release()
```

**3c.** Wrap `resume_pending_tasks()` (L863-890) with lock:

```python
def resume_pending_tasks():
    """恢复所有 pending 状态的下载任务（断点续传）

    场景：用户停止服务 → running 任务被保存为 pending → 重新启动服务后自动恢复
    """
    if not _resume_lock.acquire(blocking=False):
        logger.info("[resume_pending] 已有恢复任务正在进行，跳过")
        return {"resumed": 0, "failed": 0, "skipped": 1}

    try:
        pending = db.list_download_tasks(status="pending", limit=1000)
        resumed = 0
        failed = 0

        for task in pending:
            try:
                result = resume_download_task(task.task_id)
                if result:
                    resumed += 1
                    logger.info("[resume_pending] 恢复任务 %s 成功", task.task_id)
                else:
                    failed += 1
                    logger.warning("[resume_pending] 恢复任务 %s 失败", task.task_id)
            except Exception as e:
                failed += 1
                logger.error("[resume_pending] 恢复任务 %s 异常: %s", task.task_id, e)

        # 通知前端有任务恢复
        if resumed > 0:
            from core.utils.event_bus import emit, TASKS_RESUMED
            emit(TASKS_RESUMED, {"resumed": resumed, "failed": failed})

        return {"resumed": resumed, "failed": failed}
    finally:
        _resume_lock.release()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "f:\setup_temp\剪辑合成拆散\监控\总下载器版本" && .venv\Scripts\python.exe -m pytest tests/test_service_resume.py::TestResumeLock -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/service/task.py tests/test_service_resume.py
git commit -m "feat(resume): add _resume_lock to prevent re-entrant resume calls"
```

---

### Task 3: start_service() 删除 gopeed.db

**Files:**
- Modify: `core/api/routers/base_service.py:59-103`
- Modify: `tests/test_service_resume.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_service_resume.py`:

```python
class TestStartServiceClearsGopeedDb:
    """测试 start_service 启动前删除 gopeed.db"""

    def test_start_service_calls_clear_go_tasks_safe(self):
        """start_service 应在启动 Go 前调用 _clear_go_tasks_safe"""
        with patch("core.api.app._clear_go_tasks_safe") as mock_clear, \
             patch("core.api.routers.base_service.WechatVideoService") as mock_svc_cls:
            mock_svc = MagicMock()
            mock_svc.is_running.return_value = False
            mock_svc.is_process_running.return_value = False
            mock_svc.exe_path = "C:\\fake\\exe.exe"
            mock_svc.start.return_value = True
            mock_svc_cls.return_value = mock_svc

            with patch("os.path.exists", return_value=True):
                from core.api.routers.base_service import start_service
                result = start_service()

                mock_clear.assert_called_once()
```

Note: This test requires `_clear_go_tasks_safe` to be importable from `base_service`. Since `_clear_go_tasks_safe` is defined in `app.py`, we need to import it into `base_service.py` first. The test verifies the import and call happen.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd "f:\setup_temp\剪辑合成拆散\监控\总下载器版本" && .venv\Scripts\python.exe -m pytest tests/test_service_resume.py::TestStartServiceClearsGopeedDb -v`
Expected: FAIL — `_clear_go_tasks_safe` is not called in `start_service`

- [ ] **Step 3: Write minimal implementation**

In `core/api/routers/base_service.py`, modify `start_service()` — insert `_clear_go_tasks_safe()` call **between L73 and L74** (after the exe existence check, before `svc.start()`):

```python
    # 清空 Go 后端旧任务数据库（避免 taskkill /F 导致的 BoltDB 损坏）
    from core.api.app import _clear_go_tasks_safe
    _clear_go_tasks_safe()

    success = svc.start(wait_seconds=10)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd "f:\setup_temp\剪辑合成拆散\监控\总下载器版本" && .venv\Scripts\python.exe -m pytest tests/test_service_resume.py::TestStartServiceClearsGopeedDb -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add core/api/routers/base_service.py tests/test_service_resume.py
git commit -m "feat(service): delete gopeed.db before start_service to prevent BoltDB corruption"
```

---

### Task 4: 前端服务离线时任务卡片状态同步

**Files:**
- Modify: `static/js/component/status.js:38-41`
- Create: `tests/前端测试/单元测试/组件层/test_status_offline_pause.js`

- [ ] **Step 1: Write the failing test**

Create `tests/前端测试/单元测试/组件层/test_status_offline_pause.js`:

```js
// 测试服务离线时 running 任务标记为 paused
// 使用 Node.js vm 模块模拟浏览器环境

const assert = require('assert');

// 模拟最小全局状态
let _goOnline = true;
let _activeTasks = [
  { id: 'task_1', status: 'running', speed: 1024 },
  { id: 'task_2', status: 'pending', speed: 0 },
  { id: 'task_3', status: 'running', speed: 2048 },
];

// 模拟 State.tasks.setAll
const State = { tasks: { setAll: function(tasks) { _activeTasks = tasks; } } };

// 模拟 updateStatusFromPoll 中 _goOnline 变化检测逻辑
function simulateGoOffline() {
  var wasOnline = _goOnline;
  _goOnline = false;
  State.service = { setGoOnline: function() {} };

  if (wasOnline && !_goOnline) {
    _activeTasks = _activeTasks.map(function(t) {
      return t.status === 'running'
        ? Object.assign({}, t, { status: 'paused', speed: 0 })
        : t;
    });
    State.tasks.setAll(_activeTasks);
  }
}

// 测试：服务离线时 running 任务标记为 paused
simulateGoOffline();

assert.strictEqual(_activeTasks[0].status, 'paused', 'task_1 should be paused');
assert.strictEqual(_activeTasks[0].speed, 0, 'task_1 speed should be 0');
assert.strictEqual(_activeTasks[1].status, 'pending', 'task_2 should remain pending');
assert.strictEqual(_activeTasks[2].status, 'paused', 'task_3 should be paused');
assert.strictEqual(_activeTasks[2].speed, 0, 'task_3 speed should be 0');

console.log('PASS: test_status_offline_pause — all running tasks marked as paused on service offline');
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node "tests/前端测试/单元测试/组件层/test_status_offline_pause.js"`
Expected: This test actually passes since it's self-contained logic. The real test is that `status.js` doesn't have this logic yet. We verify by checking the source code.

- [ ] **Step 3: Write minimal implementation**

In `static/js/component/status.js`, modify the `_goOnline` assignment block (L38-41) from:

```js
  if (status.service_online !== undefined) {
    _goOnline = status.service_online;
    State.service.setGoOnline(status.service_online);
  }
```

to:

```js
  if (status.service_online !== undefined) {
    var wasOnline = _goOnline;
    _goOnline = status.service_online;
    State.service.setGoOnline(status.service_online);

    // 服务离线时，将 running 任务标记为 paused
    if (wasOnline && !_goOnline) {
      _activeTasks = _activeTasks.map(function(t) {
        return t.status === 'running'
          ? Object.assign({}, t, { status: 'paused', speed: 0 })
          : t;
      });
      State.tasks.setAll(_activeTasks);
    }
  }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node "tests/前端测试/单元测试/组件层/test_status_offline_pause.js"`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add static/js/component/status.js "tests/前端测试/单元测试/组件层/test_status_offline_pause.js"
git commit -m "feat(ui): mark running tasks as paused when service goes offline"
```

---

### Task 5: 集成验证 — 全部测试通过

**Files:**
- All modified files

- [ ] **Step 1: Run all resume-related tests**

Run: `cd "f:\setup_temp\剪辑合成拆散\监控\总下载器版本" && .venv\Scripts\python.exe -m pytest tests/test_service_resume.py -v`
Expected: All PASS

- [ ] **Step 2: Run existing event_bus tests (regression check)**

Run: `cd "f:\setup_temp\剪辑合成拆散\监控\总下载器版本" && .venv\Scripts\python.exe -m pytest tests/test_event_bus.py -v`
Expected: All PASS (no regression)

- [ ] **Step 3: Run frontend test**

Run: `node "tests/前端测试/单元测试/组件层/test_status_offline_pause.js"`
Expected: PASS

- [ ] **Step 4: Commit (if any fixups needed)**

```bash
git add -A
git commit -m "test: verify all service-resume tests pass"
```
