# SSE 实时推送作者下载统计

## 背景

一键监控运行时，后端创建下载任务并发下载视频。当前前端通过 `/api/task/list` 每秒轮询获取进度，但作者卡片上的「已下载/待下载/总数」数字不会实时更新——只能等用户点返回按钮触发全量刷新。

之前尝试过在前端内存中推导统计变化（`deriveAuthorDownloadStatus`、`applyCompletedTasks`），但因任务消失、对象引用比较、增量 DOM patch 等问题失败。

## 目标

- 每个视频下载完成时，首页对应作者卡片的「已下载」「待下载」数字立即变化
- 数据源为后端 DB（权威），前端不自行推导
- 不修改任何现有接口

## 方案：SSE 推送

### 数据流

```
Go 后端完成下载
  → Python get_task_progress() 检测到 status=done
    → db.update_video_downloaded() 标记视频已下载（现有逻辑）
    → emit_task_completed() 触发事件总线（新增）
      → SSE 端点收到事件，查 DB 统计，推送 {"username", "downloaded", "total"}
        → 前端 EventSource 收到，更新 _catalogData + DOM
```

### SSE 事件格式

```
event: task_completed
data: {"username":"xxx","downloaded":52,"total":91}
```

## 改动清单

### 1. 新建 `core/utils/event_bus.py` — 事件总线

```python
_listeners = []

def on_task_completed(callback):
    _listeners.append(callback)

def emit_task_completed(data):
    for cb in _listeners:
        try:
            cb(data)
        except Exception:
            pass
```

解耦任务完成检测和 SSE 推送，避免 TaskService 直接依赖 SSE 端点。

### 2. `core/utils/database/base.py` — 新增轻量统计查询

```python
def get_author_download_stats(self, author_id: str) -> dict:
    """单条 SQL 查询作者的 total/downloaded 统计"""
```

避免全量查视频再 count。

### 3. `core/service/task.py` — 完成时触发事件

在 `get_task_progress()` 第167-179行的现有完成检测处，`db.update_video_downloaded()` 之后加一行：

```python
emit_task_completed({"video_id": local_task.video_id, "author_id": video.author_id})
```

### 4. `core/api/routers/task.py` — 新增 SSE 端点

```python
@router.get("/events")
async def task_events():
    # FastAPI StreamingResponse + text/event-stream
    # 监听事件总线，收到 task_completed 时：
    #   1. 查 DB 获取 author 的 source_author_id (username)
    #   2. 查 DB 获取统计 (total, downloaded)
    #   3. 推送 SSE 事件
```

### 5. `static/js/datahandle/progress.js` — 前端 SSE 监听

```javascript
const _es = new EventSource('/api/task/events');
_es.addEventListener('task_completed', (e) => {
    const data = JSON.parse(e.data);
    // 更新 _catalogData
    // 更新对应作者卡片 DOM
});
```

## 不改的

- 现有 API 接口（`/api/task/list`、`/api/video/all`、`/api/service/status`）
- 现有轮询逻辑（500ms 状态、1s 进度、30min 同步）
- Go 后端
- 下载状态面板
- 视频详情页

## 验证

1. 启动一键监控 → 作者卡片实时显示已下载数字递增
2. 数字与后端 DB 一致（刷新页面后数字不变）
3. SSE 连接断开后不影响现有功能
4. 停止监控 → 数字保持最终状态

## TDD 测试计划

### 后端测试（真实 DB）

| 测试文件 | 测试内容 |
|---|---|
| `tests/单元测试/后端/test_event_bus.py` | `emit_task_completed` 触发回调、多监听器、异常不阻断 |
| `tests/单元测试/后端/test_author_stats_query.py` | `get_author_download_stats` 查询准确、空作者返回 0/0 |
| `tests/单元测试/后端/test_task_completion_event.py` | `get_task_progress` 检测到完成时触发事件总线 |

### 前端测试（Jest + jsdom）

| 测试文件 | 测试内容 |
|---|---|
| `tests/单元测试/前端/author/SSE作者统计更新.js` | 收到 SSE 事件后更新 `_catalogData`、计算 pending/progress |
