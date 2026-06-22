# 任务下载生命周期

## 概述

本文档描述一个视频下载任务从创建到完成的完整生命周期，包括 HTTP 请求、WebSocket 推送、SSE 事件流转。

---

## 1. 任务创建阶段（HTTP）

### 1.1 前端发起下载请求

**文件**: `static/js/component/videoOps.js`

```javascript
// 用户点击"下载选中"按钮
function downloadSelected() {
  // 收集选中的视频 ID
  var selectedIds = [];
  document.querySelectorAll('.video-checkbox:checked').forEach(cb => {
    selectedIds.push(cb.dataset.id);
  });

  // 调用批量创建任务 API
  fetch('/api/task/batch-create', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      video_ids: selectedIds,
      video_type: _currentVideoType  // 'short_video' 或 'live_replay'
    })
  });
}
```

### 1.2 后端批量创建任务

**文件**: `core/api/routers/task.py`

```python
@router.post("/api/task/batch-create")
def batch_create_tasks(request: BatchCreateRequest):
    """批量创建下载任务"""
    results = []
    for video_id in request.video_ids:
        result = task_service.create_download_task(video_id, request.video_type)
        results.append(result)

    return {"code": 0, "data": {"results": results}}
```

### 1.3 任务服务创建任务

**文件**: `core/service/task.py`

```python
def create_download_task(self, video_id: str, video_type: str) -> dict:
    """创建下载任务"""

    # 1. 从本地数据库获取视频信息
    video = self.db.get_author_video(video_id)
    if not video:
        return {"code": -1, "msg": "视频不存在"}

    # 2. 检查是否已下载
    if video.is_downloaded:
        return {"code": 0, "msg": "已下载", "data": {"skipped": True}}

    # 3. 调用 Go 后端创建任务
    result = self.weixin_client.download_video(
        video_id=video_id,
        url=video.video_url,
        title=video.title,
        spec=video.spec or "",
        key=video.decrypt_key or 0,
        author_name=author.nickname if author else "",
        create_time=video.create_time.isoformat() if video.create_time else "",
        video_type=video_type
    )

    # 4. 存储任务到本地数据库
    if result.get("code") == 0:
        task_id = result.get("data", {}).get("id")
        self.db.create_download_task(
            task_id=task_id,
            video_id=video_id,
            status="pending"
        )

    return result
```

### 1.4 调用 Go 后端 API

**文件**: `core/utils/weixin_client.py`

```python
def download_video(self, video_id: str, url: str, title: str, ...):
    """调用 Go 后端创建下载任务"""

    # 构建请求参数
    resp = requests.post(
        f"{self.base_url}/api/task/create2",
        json={
            "url": url,
            "filename": filename,      # 如 "2024-01-15_视频标题_1080p.mp4"
            "dir": dir_path,           # 如 "作者昵称/短视频"
            "extra": {
                "id": video_id,        # ⭐ 关键：视频 ID，用于后续关联
                "title": title,
                "key": str(key),
                "spec": spec,
                "suffix": ".mp4",
            },
        }
    )

    return resp.json()
    # 返回格式: {"code": 0, "data": {"id": "task_xxx"}, "msg": ""}
```

### 1.5 Go 后端返回

```json
{
  "code": 0,
  "data": {
    "id": "task_abc123"  // Go 后端生成的任务 ID
  },
  "msg": ""
}
```

**可能的错误码**:
- `code: 409` - URL 已存在（任务重复）
- `code: -1` - 其他错误

---

## 2. 进度推送阶段（WebSocket → SSE）

### 2.1 Go 后端 WebSocket 推送

Go 后端通过 WebSocket 推送任务进度：

```
WebSocket URL: ws://127.0.0.1:2022/ws/downloader
```

**消息格式**:

```json
{
  "type": "event",
  "data": {
    "task": {
      "id": "task_abc123",
      "name": "2024-01-15_视频标题_1080p.mp4",
      "status": "running",  // pending | running | wait | done | completed | error
      "progress": {
        "used": 5242880,      // 已下载字节数
        "speed": 1048576,     // 下载速度 (bytes/s)
        "downloaded": 5242880 // 已下载字节数
      },
      "meta": {
        "req": {
          "labels": {
            "id": "video_xxx"  // 视频 ID
          }
        },
        "res": {
          "size": 10485760     // 总大小 (bytes)
        },
        "opts": {
          "path": "作者昵称/短视频",
          "name": "2024-01-15_视频标题_1080p.mp4"
        }
      },
      "createdAt": "2024-01-15T10:30:00Z",
      "updatedAt": "2024-01-15T10:30:05Z"
    }
  }
}
```

### 2.2 Python WebSocket 监听器处理

**文件**: `core/utils/socket_client.py`

```python
def _on_message(self, ws, message):
    """接收 WebSocket 消息"""
    data = json.loads(message)
    msg_type = data.get("type")

    if msg_type == "event":
        task = data.get("data", {}).get("task")
        if task:
            self._normalize_and_callback(task)
    elif msg_type == "batch_tasks":
        tasks = data.get("data", [])
        for task in tasks:
            self._normalize_and_callback(task)

def _normalize_and_callback(self, task):
    """标准化任务数据并回调"""

    # 提取关键字段
    video_id = task.get("meta", {}).get("req", {}).get("labels", {}).get("id", "")

    # 如果 labels 中没有 video_id，从数据库补查
    if not video_id:
        task_id = task.get("id")
        dl_task = db.get_download_task(task_id)
        if dl_task:
            video_id = dl_task.video_id

    normalized = {
        "id": task.get("id"),
        "video_id": video_id,
        "status": task.get("status"),
        "downloaded": progress.get("downloaded", 0),
        "speed": progress.get("speed", 0),
        "total_size": total_size,
    }

    # ⭐ 终态时立即写 DB + 触发事件总线
    if status in ("done", "completed") and video_id:
        # 写入数据库
        db.update_video_downloaded(video_id, full_path)
        # 触发事件总线
        emit_task_completed({"video_id": video_id, "author_id": author_id})

    self._callback(normalized)
```

### 2.3 事件总线分发

**文件**: `core/utils/event_bus.py`

```python
def emit(event_type: str, data: dict):
    """发射事件，通知所有监听器"""
    payload = {"event_type": event_type, **data}

    for cb in _listeners:  # SSE 端点注册的回调
        cb(payload)
```

### 2.4 SSE 端点转发

**文件**: `core/api/routers/sse.py`

```python
@router.get("/api/events")
def sse_endpoint():
    """SSE 端点 - 前端通过此连接接收实时事件"""

    def on_event(payload):
        queue.put_nowait(payload)

    subscribe(on_event)  # 注册到事件总线

    async def generate():
        while True:
            payload = await queue.get()
            event_type = payload.get("event_type")
            sse_data = _transform_event(event_type, payload)
            yield f"event: {event_type}\ndata: {sse_data}\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
```

---

## 3. SSE 事件类型

### 3.1 task_progress（进度更新）

**触发时机**: 任务状态变化（pending → running → done/error）

**数据转换** (`_transform_task_progress`):

```python
def _transform_task_progress(payload: dict) -> str:
    """task_progress 事件：转发 WS 进度数据到前端"""

    task_id = payload.get("id")
    video_id = payload.get("video_id", "")
    status = payload.get("status", "")

    # ⭐ 终态时查 DB 补充 download_path
    download_path = ""
    if status in ("done", "completed") and video_id:
        video_record = db.get_video(video_id)
        if video_record:
            download_path = video_record.download_path

    return json.dumps({
        "id": task_id,
        "video_id": video_id,
        "status": status,
        "downloaded": payload.get("downloaded", 0),
        "speed": payload.get("speed", 0),
        "total_size": payload.get("total_size", 0),
        "download_path": download_path,  # ⭐ 关键：播放按钮依赖此字段
    })
```

**前端接收** (`authorDetail.js`):

```javascript
es.addEventListener('task_progress', function(e) {
    var data = JSON.parse(e.data);
    handleSSETaskProgress(data);
});
```

### 3.2 task_completed（完成事件）

**触发时机**: 任务完成时，由 `socket_client.py` 或 `task.py` 触发

**数据转换** (`_transform_task_completed`):

```python
def _transform_task_completed(payload: dict) -> str:
    """task_completed 事件：查 DB 补充作者统计"""

    author_id = payload.get("author_id")
    video_id = payload.get("video_id")

    # 查询作者统计
    stats = db.get_author_download_stats(author_id)

    # 查询下载路径
    video_record = db.get_video(video_id)
    download_path = video_record.download_path if video_record else ""

    return json.dumps({
        "username": author.source_author_id,
        "video_id": video_id,
        "downloaded": stats["downloaded"],
        "total": stats["total"],
        "download_path": download_path,
        "today_count": db.count_videos_today(),
        "today_downloaded": db.count_downloaded_today(),
        "total_videos": db.count_videos_total(),
    })
```

### 3.3 service_status（服务状态）

**触发时机**: 定时推送（每 5 秒）

```json
{
  "service_online": true,
  "wechat_connected": true
}
```

---

## 4. 前端处理流程

### 4.1 进度更新处理

**文件**: `static/js/datahandle/authorDetail.js`

```javascript
function handleSSETaskProgress(data) {
    var taskId = data.id;
    var videoId = data.video_id;
    var status = data.status;

    // 1. 忽略已取消任务的残留消息
    if (_cancelledTaskIds[taskId]) {
        return;
    }

    // 2. 终态处理（done/error）
    if (status === 'done' || status === 'error') {
        // 从 _activeTasks 移除
        _activeTasks = _activeTasks.filter(t => t.id !== taskId);

        if (status === 'done') {
            // 标记视频为已下载
            videos[videoId] = { ...video, downloaded: true, download_path: data.download_path };
            // 更新视频行 UI（显示播放按钮）
            updateSingleVideoCompleted(videoId, videos[videoId]);
        } else {
            // 错误状态：恢复为"待下载"
            updateSingleVideoError(videoId);
        }

        // 刷新任务列表
        refreshActiveTasks();
        return;
    }

    // 3. 更新 _activeTasks
    var taskIdx = _activeTasks.findIndex(t => t.id === taskId);
    if (taskIdx < 0) {
        // 新任务插入
        _activeTasks.push({
            id: taskId,
            video_id: videoId,
            status: status,
            percent: pct,
            downloaded: rawDownloaded,
            size: rawSize,
            speed: rawSpeed,
        });
    } else {
        // 更新现有任务
        _activeTasks[taskIdx] = { ..._activeTasks[taskIdx], ...newData };
    }

    // 4. 更新视频行 UI（显示进度条）
    updateSingleVideoProgress(videoId, _activeTasks[taskIdx]);
}
```

### 4.2 视频行 UI 更新

**文件**: `static/js/component/videoListRender.js`

```javascript
function updateSingleVideoProgress(videoId, task) {
    var row = document.querySelector('.video-row[data-id="' + videoId + '"]');
    var badge = row.querySelector('.video-status-badge');

    // 更新进度显示
    badge.className = 'video-status-badge downloading';
    badge.textContent = task.percent + '%';
}

function updateSingleVideoCompleted(videoId, video) {
    var row = document.querySelector('.video-row[data-id="' + videoId + '"]');
    var badge = row.querySelector('.video-status-badge');

    // 切换为"已下载"
    badge.className = 'video-status-badge downloaded';
    badge.textContent = '已下载';

    // ⭐ 添加播放按钮
    if (video.download_path) {
        var openBtn = document.createElement('button');
        openBtn.className = 'video-open-btn';
        openBtn.textContent = '播放';
        openBtn.onclick = () => openVideo(video.download_path);
        row.appendChild(openBtn);
    }
}

function updateSingleVideoError(videoId) {
    var row = document.querySelector('.video-row[data-id="' + videoId + '"]');
    var badge = row.querySelector('.video-status-badge');

    // 恢复为"待下载"
    badge.className = 'video-status-badge pending';
    badge.textContent = '待下载';
}
```

---

## 5. 完整流程图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           任务创建阶段                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  前端                      Python 后端                   Go 后端         │
│  ────                      ──────────                   ──────          │
│                                                                          │
│  downloadSelected()                                                    │
│       │                                                                 │
│       ├─ POST /api/task/batch-create ──→ batch_create_tasks()          │
│       │                                      │                          │
│       │                                      ├─ create_download_task()   │
│       │                                      │       │                  │
│       │                                      │       ├─ 查询视频信息     │
│       │                                      │       │                  │
│       │                                      │       └─ POST /api/task/create2 ──→
│       │                                      │                               │
│       │                                      │                               ├─ 创建任务
│       │                                      │                               │
│       │                                      │←── {"code":0,"data":{"id":"task_xxx"}}
│       │                                      │                               │
│       │                                      └─ 存储到本地 DB               │
│       │                                                                     │
│       │←────── {"code":0,"data":{"results":[...]}} ────────────────────────│
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                           进度推送阶段                                    │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  Go 后端                   Python 后端                   前端            │
│  ──────                    ──────────                   ────            │
│                                                                          │
│  WS: ws://127.0.0.1:2022/ws/downloader                                  │
│       │                                                                  │
│       ├─ 推送进度 ──────────────────→ socket_client.py                  │
│       │   {"type":"event",                  │                           │
│       │    "data":{"task":{...}}}           │                           │
│       │                                     │                           │
│       │                                     ├─ _normalize_and_callback() │
│       │                                     │       │                   │
│       │                                     │       ├─ 提取 video_id    │
│       │                                     │       │                   │
│       │                                     │       ├─ 终态? 写 DB      │
│       │                                     │       │                   │
│       │                                     │       └─ emit() ──→ event_bus
│       │                                     │                           │
│       │                                     └───────────────────────────│
│       │                                                                 │
│       │                                    SSE: /api/events             │
│       │                                         │                       │
│       │                                         ├─ _transform_event()    │
│       │                                         │       │               │
│       │                                         │       └─ 查 DB 补充    │
│       │                                         │           download_path
│       │                                         │                       │
│       │                                         └─ 推送 SSE ──────────→ │
│       │                                                                 │
│       │                                         event: task_progress    │
│       │                                         data: {"id":"task_xxx", │
│       │                                                "video_id":"...",│
│       │                                                "status":"done",│
│       │                                                "download_path":"..."}
│       │                                                                 │
│       │                                                              │  │
│       │                                                              ├─ handleSSETaskProgress()
│       │                                                              │       │
│       │                                                              │       ├─ 更新 _activeTasks
│       │                                                              │       │
│       │                                                              │       └─ updateSingleVideoCompleted()
│       │                                                              │               │
│       │                                                              │               ├─ 显示"已下载"
│       │                                                              │               │
│       │                                                              │               └─ 添加播放按钮
│       │                                                              │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## 6. 关键数据字段

### 6.1 任务状态

| 状态 | 含义 | 前端处理 |
|------|------|----------|
| `pending` | 等待中 | 显示"等待中" |
| `running` | 下载中 | 显示进度条 |
| `wait` | 等待重试 | 显示"等待重试" |
| `done` | 下载完成 | 显示"已下载" + 播放按钮 |
| `completed` | 完成（同 done） | 显示"已下载" + 播放按钮 |
| `error` | 失败 | 恢复为"待下载" |

### 6.2 关键字段映射

| Go 后端字段 | Python 标准化字段 | SSE 转发字段 | 前端使用 |
|-------------|-------------------|--------------|----------|
| `id` | `id` | `id` | 任务 ID |
| `meta.req.labels.id` | `video_id` | `video_id` | 视频 ID |
| `status` | `status` | `status` | 任务状态 |
| `progress.downloaded` | `downloaded` | `downloaded` | 已下载字节 |
| `progress.speed` | `speed` | `speed` | 下载速度 |
| `meta.res.size` | `total_size` | `total_size` | 总大小 |
| `meta.opts.path` + `meta.opts.name` | - | `download_path` | 文件路径（终态时查 DB） |

---

## 7. 已知问题与修复

### 7.1 播放按钮不显示

**原因**: `task_progress` SSE 消息不包含 `download_path`

**修复**:
1. `socket_client.py` 终态时写 DB
2. `sse.py` 终态时查 DB 补充 `download_path`

### 7.2 任务卡在 0%

**原因**: Go 后端返回 `error` 状态，前端未处理

**修复**: 添加 `updateSingleVideoError()` 函数，错误状态恢复为"待下载"

### 7.3 文件名含换行符导致 Go 后端立即 error

**原因**: 视频标题包含 `\n` 换行符，`safe_title` 只替换了 `<>:"/\|?*` 但未替换 `\n\r\t`，导致 Windows 文件名非法，Go 后端无法创建文件，立即返回 error

**修复**: `weixin_client.py` 的 `safe_title` 和 `safe_author` 正则中添加 `\n\r\t`

**症状**: 任务创建成功（code=0），但 Go 后端 WS 推送立即 status=error，error 字段为空字符串，createdAt 和 updatedAt 之间仅差几十毫秒

### 7.4 任务 ID 不匹配

**原因**: Go 后端和本地 DB 使用不同的 task_id

**解决**: 删除 Go 后端错误任务，重新创建

---

## 8. 调试日志关键字

```
[WS] 收到WS消息: type=event
[WS] event任务: id=task_xxx, status=running
[event_bus] 发射事件: type=task_progress
[SSE] task_progress: id=task_xxx, video_id=xxx, status=done
[SSE][数据层] 标记视频已下载: videoId=xxx
[SSE][渲染层] 更新视频行: id=xxx, downloaded=true
```
