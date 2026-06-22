# 服务停止→重启 断点续传设计

## Context

用户多选视频下载 → 点击"停止服务" → Go 后端被 taskkill /F → 进度停止 → 再点击"启动" → Go 启动后，**下载任务不会自动恢复**。

对比应用关闭时的流程（已实现断点续传）：

```
应用关闭:
  _shutdown_sequence()
    → _save_running_tasks_progress() (running→pending)
  下次启动:
    _startup_sequence()
    → _auto_start_go_backend() (stop Go → delete gopeed.db → start Go)
    → resume_all_running_tasks() (pending→Go download API)
    → OrphanTaskCleaner.cleanup_on_startup()
```

当前服务停止→启动的流程缺少关键步骤。

## 现有实现审计

以下功能**已经存在**，无需新建：

| 功能 | 文件 | 状态 |
|------|------|------|
| stop_service 保存 running→pending | `base_service.py:119-125` | ✅ 已实现 |
| start_service 后台异步恢复 | `base_service.py:79-98` | ✅ 已实现 |
| resume_pending_tasks() | `task.py:863-890` | ✅ 已实现，含 TASKS_RESUMED 事件 |
| TASKS_RESUMED 事件常量 | `event_bus.py:15` | ✅ 已添加 |
| 前端 tasks_resumed SSE 监听 | `authorDetail.js:94-109` | ✅ 已添加 |

以下功能**缺失**，需要新增：

| 缺失功能 | 风险 | 优先级 |
|----------|------|--------|
| URL 过期刷新 | 高 — 微信视频 URL 几小时过期，resume 用旧 URL 100% 失败 | P0 |
| resume 防重入锁 | 中 — 快速连点启动可能重复恢复任务 | P1 |
| 删除 gopeed.db | 中 — stop 时 Go 被强制杀，BoltDB 可能损坏 | P1 |
| 前端任务卡片状态同步 | 低 — 服务离线时 UI 显示"下载中"但无进度 | P2 |
| 全局 SSE toast | 低 — 当前只在作者详情页可见 | P2 |

## 方案：补齐缺失的 3 个关键改进

### 改进1: resume_download_task() 中 URL 过期刷新

**Why:** `resume_download_task()` (task.py:529-615) 用 DB 中保存的旧 URL 调用 `client.download_video()`，但微信视频 URL 几小时后过期。应用关闭时断点续传能成功，是因为从关闭到重启通常很短；服务停止→重启间隔可能更长，URL 过期概率高。

**How:** 在调用 `client.download_video()` 之前，增加 `SearchService.ensure_valid_url()` 调用。与 `CompensationTransactionManager.create_task_with_compensation()` (compensation_manager.py:104-109) 的模式一致。

**改动点:**

```python
# task.py:resume_download_task() — 在 L560 client.download_video() 之前
# 查找视频的 source_author_id（ensure_valid_url 需要）
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
```

然后用 `effective_url` 代替 `task.url` 调用 `client.download_video()`。

### 改进2: resume_pending_tasks() 防重入锁

**Why:** 用户快速连点"启动"或多个触发源（start_service + GO_CONNECTED）同时调用 `resume_pending_tasks()`，可能导致同一视频创建多个 Go 下载任务。

**How:** 在 task.py 模块级别添加 `_resume_lock = threading.Lock()`，在 `resume_pending_tasks()` 开头尝试获取锁（非阻塞），获取失败则跳过。

**改动点:**

```python
# task.py 模块顶部新增
_resume_lock = threading.Lock()

# resume_pending_tasks() 开头新增
def resume_pending_tasks():
    if not _resume_lock.acquire(blocking=False):
        logger.info("[resume_pending] 已有恢复任务正在进行，跳过")
        return {"resumed": 0, "failed": 0, "skipped": 1}

    try:
        # ... 现有逻辑 ...
    finally:
        _resume_lock.release()
```

同样在 `resume_all_running_tasks()` 添加锁保护。

### 改进3: start_service() 删除 gopeed.db

**Why:** `taskkill /F` 杀 Go 进程时，gopeed.db (BoltDB) 可能处于写入中间状态，文件损坏。应用启动时 `_auto_start_go_backend()` 会先删除 gopeed.db，但服务启动路由不做此操作。Go 的 `bbolt.Open()` 在文件不存在时会自动创建，所以删除是安全的。

**How:** 在 `start_service()` 中调用现有的 `_clear_go_tasks_safe()` (app.py:80-96)，或在 base_service.py 中复制其逻辑。

**改动点:**

```python
# base_service.py:start_service() — 在 svc.start() 之前
# 清空 Go 后端旧任务数据库（避免 taskkill /F 导致的 BoltDB 损坏）
from core.api.app import _clear_go_tasks_safe
_clear_go_tasks_safe()

success = svc.start(wait_seconds=10)
```

注意：`_clear_go_tasks_safe()` 只在 Go 进程已停止时安全执行（stop 之后已经停了，或首次启动时本就没运行）。当前 `start_service()` 的流程是：先检查是否已运行 → 如果没运行才 start → 所以在 start 之前删除 gopeed.db 是安全的。

### 改进4 (可选): 前端服务离线时任务卡片状态

**Why:** 服务离线后，前端 activeTasks 中的 running 任务卡在"下载中"但无进度更新，给用户困惑。

**How:** 在 `status.js` 的 `updateStatusFromPoll()` 中，当 `service_online` 从 true → false 时，将 running 任务标记为 paused。

**改动点:**

```js
// status.js:updateStatusFromPoll() — 在 serviceChanged 分支内
if (serviceChanged) {
    // ... 现有按钮/文字更新逻辑 ...

    // 服务离线时，将 running 任务标记为 paused
    if (!status.service_online && _lastStatus.service_online === false) {
        // 上一次 service_online=true, 现在变 false
        // 注意：此时 _lastStatus 已被更新，所以用 _goOnline 判断旧值
    }
}

// 更简洁的方式：在 _goOnline 赋值处检测变化
// 将 L38-41 的代码改为：
if (status.service_online !== undefined) {
    var wasOnline = _goOnline;
    _goOnline = status.service_online;
    State.service.setGoOnline(status.service_online);

    // 服务离线时，将 running 任务标记为 paused
    if (wasOnline && !_goOnline) {
        _activeTasks = _activeTasks.map(function(t) {
            return t.status === 'running'
                ? Object.assign({}, t, {status: 'paused', speed: 0})
                : t;
        });
        State.tasks.setAll(_activeTasks);
    }
}
```

## 修改文件清单

| # | 文件 | 改动 | 行号范围 |
|---|------|------|----------|
| 1 | `core/service/task.py` | resume_download_task() 增加 URL 刷新 | L559-570 |
| 2 | `core/service/task.py` | 新增 `_resume_lock` + 两个函数加锁 | L1(模块级), L618, L863 |
| 3 | `core/api/routers/base_service.py` | start_service() 删除 gopeed.db | L74 之前 |
| 4 | `static/js/component/status.js` | 服务离线时更新任务卡片 | updateStatusFromPoll |

## 不做的事

- **不在 `_on_go_online()` 中触发 resume**：start_service 已经有异步恢复线程，GO_CONNECTED 触发会造成重入。改用 `_resume_lock` 防护即可。
- **不将 SSE 监听器移到 app.js**：当前 SSE 连接在 authorDetail.js 中创建，所有事件（包括 tasks_resumed）已在该 ES 上监听。移到 app.js 需要重构 SSE 初始化架构，代价大于收益。
- **不在 restart_service 中做额外处理**：restart 已经有 save + async resume + 锁保护，足够。

## 时序图（改进后）

```
用户点击"停止" → stop_service()
  ├── running → pending (DB) [已有]
  └── taskkill Go 进程
       └── GO_DISCONNECTED 事件 → 监控暂停 + 前端任务卡片 "已暂停" [新增]

用户点击"启动" → start_service()
  ├── _clear_go_tasks_safe() (删除 gopeed.db) [新增]
  ├── svc.start(wait_seconds=10)
  └── _resume_tasks_async() (5s delay)
       ├── _resume_lock.acquire() [新增]
       ├── resume_pending_tasks()
       │   ├── resume_download_task(task_id)
       │   │   ├── ensure_valid_url() → URL 刷新 [新增]
       │   │   └── client.download_video(effective_url)
       │   └── TASKS_RESUMED 事件 → SSE → toast
       └── _resume_lock.release() [新增]
```

## 验证

1. 启动服务 → 多选下载 3 个视频 → 停止服务 → DB 中任务状态为 pending
2. 前端任务卡片显示"已暂停"
3. 等待 4+ 小时（URL 过期）→ 启动服务 → URL 自动刷新 → 任务恢复成功
4. 快速连点"启动" → 只恢复一次，无重复任务
5. gopeed.db 删除后 Go 正常重建 → 下载任务恢复
6. 无 pending 任务时启动 → 恢复跳过，不触发 toast

## 边界情况

| 场景 | 处理 |
|------|------|
| URL 刷新失败 | resume_download_task() 返回 False，任务计入 failed |
| Go 后端未就绪（5s 等待不够） | download_video() 失败，任务计为 failed，下次重试 |
| 无 pending 任务 | resume_pending_tasks() 立即返回，不触发 toast |
| 多次快速点击启动 | _resume_lock 防重入，第二次请求被跳过 |
| gopeed.db 删除失败 | _clear_go_tasks_safe() 只 warning 不中断启动流程 |