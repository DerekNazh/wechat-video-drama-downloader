# SSE 实体响应式架构

> 本文档描述前端响应式架构的核心设计：SSE 事件 → State 层 → UI 组件的数据流程。

---

## 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                         后端                                     │
│  ┌──────────┐    ┌──────────┐    ┌──────────┐    ┌──────────┐  │
│  │ Go 后端   │    │ 监控器   │    │ 导入器   │    │ 任务服务  │  │
│  └────┬─────┘    └────┬─────┘    └────┬─────┘    └────┬─────┘  │
│       │               │               │               │         │
│       ▼               ▼               ▼               ▼         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    EventBus.emit()                       │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ SSE /api/events
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                         前端                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    SSE EventSource                       │   │
│  │  es.addEventListener('event_type', handler)              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    State 层                              │   │
│  │  State.service    State.authors    State.videos         │   │
│  │  State.tasks      State.import                            │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                    UI 组件层                             │   │
│  │  状态栏组件    作者卡片    视频行    下载进度条           │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

---

## 一、服务实体 (Service)

### 1.1 实体定义

服务实体负责监控 Go 后端服务和微信客户端的连接状态。

**State 结构**：
```javascript
State.service = {
  go_online: false,        // Go 后端是否在线
  wechat_connected: false, // 微信客户端是否已连接
  monitor_running: false,  // 监控器是否运行中
}
```

### 1.2 SSE 事件

| 事件类型 | 触发时机 | 数据结构 |
|---------|---------|---------|
| `service_status` | 定时检测（1秒间隔） | `{ service_online, wechat_connected }` |

**后端触发点**：
- `core/utils/service_status_push.py` - 后台线程定时检测

### 1.3 数据流程

```
┌─────────────────────────────────────────────────────────────────┐
│ 后端                                                            │
│                                                                 │
│  service_status_push.py                                         │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ while _running:                                          │   │
│  │     service_online = client.check_service()             │   │
│  │     wechat_connected = client.check_wechat_connected()  │   │
│  │     emit("service_status", {                            │   │
│  │         service_online,                                  │   │
│  │         wechat_connected                                │   │
│  │     })                                                  │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ SSE event: service_status
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 前端                                                            │
│                                                                 │
│  authorDetail.js                                                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ es.addEventListener('service_status', (e) => {          │   │
│  │     const data = JSON.parse(e.data);                    │   │
│  │     handleSESServiceStatus(data);                       │   │
│  │ });                                                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  State.service                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ State.service.setGoOnline(data.service_online);         │   │
│  │ State.service.setWechatConnected(data.wechat_connected);│   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  UI 组件                                                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ status.js: updateStatusFromPoll(status)                 │   │
│  │ - txtService.textContent = "在线"/"离线"                │   │
│  │ - dotService.className = "dot green"/"dot"              │   │
│  │ - txtWechat.textContent = "已连接"/"未连接"             │   │
│  │ - dotWechat.className = "dot green"/"dot"               │   │
│  │ - btnService.innerHTML = "■ 停止"/"▶ 启动"              │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 1.4 UI 组件响应

| 组件 | 订阅数据 | 响应行为 |
|------|---------|---------|
| 状态栏抽屉 | `go_online`, `wechat_connected` | 绿点/灰点，"在线"/"离线" |
| 服务启停按钮 | `go_online` | "启动"/"停止" 文案切换 |
| 微信连接指示器 | `wechat_connected` | "已连接"/"未连接" |
| 抽屉摘要 | `go_online`, `wechat_connected` | 摘要文案变化 |

---

## 二、作者实体 (Author)

### 2.1 实体定义

作者实体负责管理作者的统计信息，包括已下载数、总数、待下载数等。

**State 结构**：
```javascript
State.authors = {
  list: [],                    // 作者列表
  stats: {                     // 按作者ID的统计
    [author_id]: {
      downloaded: 0,          // 已下载数
      total: 0,                // 总视频数
      pending: 0,              // 待下载数
      progress: 0,             // 下载进度百分比
    }
  }
}

// 全局统计
State.global = {
  today_count: 0,              // 今日新增
  today_downloaded: 0,         // 今日已下载
  total_videos: 0,             // 总视频数
}
```

### 2.2 SSE 事件

| 事件类型 | 触发时机 | 数据结构 |
|---------|---------|---------|
| `task_completed` | 下载完成时 | `{ username, video_id, downloaded, total, download_path, today_count, today_downloaded, total_videos }` |

**后端触发点**：
- `core/utils/socket_client.py` - WebSocket 收到 done 状态
- `core/service/task.py` - 任务完成时

### 2.3 数据流程

```
┌─────────────────────────────────────────────────────────────────┐
│ 后端                                                            │
│                                                                 │
│  socket_client.py / task.py                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ if status in ("done", "completed"):                     │   │
│  │     db.update_video_downloaded(video_id, path)          │   │
│  │     emit_task_completed({                               │   │
│  │         video_id,                                        │   │
│  │         author_id                                        │   │
│  │     })                                                   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  sse.py: _transform_task_completed()                           │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ author = db.get_author(author_id)                       │   │
│  │ stats = db.get_author_download_stats(author_id)         │   │
│  │ return {                                                │   │
│  │     username: author.source_author_id,                  │   │
│  │     video_id,                                            │   │
│  │     downloaded: stats["downloaded"],                     │   │
│  │     total: stats["total"],                               │   │
│  │     download_path,                                       │   │
│  │     today_count: db.count_videos_today(),               │   │
│  │     today_downloaded: db.count_downloaded_today(),      │   │
│  │     total_videos: db.count_videos_total()               │   │
│  │ }                                                        │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ SSE event: task_completed
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 前端                                                            │
│                                                                 │
│  authorDetail.js                                                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ es.addEventListener('task_completed', (e) => {          │   │
│  │     const data = JSON.parse(e.data);                    │   │
│  │     handleSSETaskCompleted(data);                      │   │
│  │ });                                                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  State.authors                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ // 1. 更新 _catalogData                                 │   │
│  │ _catalogData[idx] = {                                   │   │
│  │     ..._catalogData[idx],                               │   │
│  │     downloaded: data.downloaded,                        │   │
│  │     pending: data.total - data.downloaded,             │   │
│  │     progress: Math.round(downloaded / total * 100)     │   │
│  │ };                                                      │   │
│  │                                                          │   │
│  │ // 2. 更新全局统计                                       │   │
│  │ State.global.today_count = data.today_count;           │   │
│  │ State.global.today_downloaded = data.today_downloaded; │   │
│  │ State.global.total_videos = data.total_videos;         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  UI 组件                                                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ // 1. 更新作者卡片统计                                   │   │
│  │ updateAuthorCardStats(username, _catalogData[idx]);    │   │
│  │                                                          │   │
│  │ // 2. 更新状态栏统计                                     │   │
│  │ txtTodayCount.textContent = data.today_count;          │   │
│  │ txtTodayDownloaded.textContent = data.today_downloaded;│   │
│  │ txtTotalVideos.textContent = data.total_videos;        │   │
│  │                                                          │   │
│  │ // 3. 更新作者详情页头部（如果在详情页）                 │   │
│  │ authorDownloaded.textContent = data.downloaded;        │   │
│  │ authorPending.textContent = data.total - data.downloaded;│  │
│  │ authorTotal.textContent = data.total;                  │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 2.4 UI 组件响应

| 组件 | 订阅数据 | 响应行为 |
|------|---------|---------|
| 作者卡片 | `downloaded`, `total`, `pending` | 统计数字更新 |
| 状态栏统计 | `today_count`, `today_downloaded`, `total_videos` | 数字更新 |
| 作者详情页头部 | `downloaded`, `total` | 顶部统计更新 |
| 抽屉摘要 | `downloaded`, `total` | 摘要文案变化 |

---

## 三、视频实体 (Video)

### 3.1 实体定义

视频实体负责管理单个视频的下载状态，包括是否已下载、下载路径等。

**State 结构**：
```javascript
State.videos = {
  [author_id]: {
    videos: {
      [video_id]: {
        downloaded: false,      // 是否已下载
        download_path: "",     // 下载路径
        status: "pending",     // pending/downloading/done/error
      }
    }
  }
}
```

### 3.2 SSE 事件

| 事件类型 | 触发时机 | 数据结构 |
|---------|---------|---------|
| `task_progress` | WebSocket 推送进度 | `{ id, video_id, status, downloaded, speed, total_size, download_path, error_msg }` |
| `task_completed` | 下载完成时 | `{ username, video_id, download_path, ... }` |

**后端触发点**：
- `core/utils/socket_client.py` - WebSocket 消息处理
- `core/api/app.py` - WebSocket 消息转发到 EventBus

### 3.3 数据流程

```
┌─────────────────────────────────────────────────────────────────┐
│ 后端                                                            │
│                                                                 │
│  Go 后端 WebSocket                                              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ { "type": "event", "data": { "task": { ... } } }        │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  socket_client.py: _normalize_and_callback()                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ // 终态时写 DB                                          │   │
│  │ if status in ("done", "completed"):                     │   │
│  │     db.update_video_downloaded(video_id, path)          │   │
│  │     emit_task_completed({ video_id, author_id })       │   │
│  │                                                          │   │
│  │ // 回调触发 SSE                                          │   │
│  │ self._callback(normalized)                              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  app.py: WebSocket 消息转发                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ emit("task_progress", normalized)                       │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ SSE event: task_progress
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 前端                                                            │
│                                                                 │
│  authorDetail.js                                                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ es.addEventListener('task_progress', (e) => {           │   │
│  │     const data = JSON.parse(e.data);                   │   │
│  │     handleSSETaskProgress(data);                      │   │
│  │ });                                                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  State.videos                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ // 完成/错误时更新视频状态                               │   │
│  │ if (data.status === 'done' && videoId) {               │   │
│  │     videos[videoId] = {                                │   │
│  │         ...video,                                       │   │
│  │         downloaded: true,                               │   │
│  │         download_path: data.download_path              │   │
│  │     };                                                 │   │
│  │ }                                                       │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  UI 组件                                                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ // 完成时更新单个视频行                                  │   │
│  │ if (data.status === 'done') {                          │   │
│  │     updateSingleVideoCompleted(videoId, videos[videoId]);│  │
│  │     // 隐藏下载框，显示"已下载"，添加播放按钮           │   │
│  │ }                                                       │   │
│  │                                                          │   │
│  │ // 错误时恢复为待下载                                    │   │
│  │ if (data.status === 'error') {                         │   │
│  │     updateSingleVideoError(videoId);                   │   │
│  │     // 隐藏下载框，恢复"待下载"状态                     │   │
│  │ }                                                       │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 3.4 UI 组件响应

| 组件 | 订阅数据 | 响应行为 |
|------|---------|---------|
| 视频行 | `downloaded`, `download_path` | 显示"已下载"/"待下载"，播放按钮 |
| 视频列表 | 视频列表 | 筛选、排序 |
| 下载进度条 | `status`, `progress` | 显示下载进度 |

---

## 四、任务实体 (Task)

### 4.1 实体定义

任务实体负责管理活跃的下载任务，包括任务进度、速度等。

**State 结构**：
```javascript
State.tasks = {
  active: [],                    // 活跃任务列表
  byVideoId: {                   // 按视频ID索引
    [video_id]: {
      task_id: "",
      status: "pending",         // pending/running/done/error
      progress: 0,                // 进度百分比
      downloaded: 0,              // 已下载字节数
      speed: 0,                   // 下载速度
      total_size: 0,              // 总大小
    }
  }
}
```

### 4.2 SSE 事件

| 事件类型 | 触发时机 | 数据结构 |
|---------|---------|---------|
| `task_progress` | WebSocket 推送进度 | `{ id, video_id, status, downloaded, speed, total_size, download_path, error_msg }` |

**后端触发点**：
- `core/utils/socket_client.py` - WebSocket 消息处理
- `core/api/app.py` - WebSocket 消息转发到 EventBus

### 4.3 数据流程

```
┌─────────────────────────────────────────────────────────────────┐
│ 后端                                                            │
│                                                                 │
│  Go 后端 WebSocket                                              │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ { "type": "event", "data": { "task": {                  │   │
│  │     "id": "xxx",                                        │   │
│  │     "status": "running",                                │   │
│  │     "progress": { "downloaded": 1024, "speed": 512 }    │   │
│  │ } } }                                                   │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  socket_client.py: _normalize_and_callback()                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ // 标准化任务数据                                        │   │
│  │ normalized = {                                          │   │
│  │     id: task["id"],                                     │   │
│  │     video_id: extra.get("id"),                          │   │
│  │     status: task["status"],                             │   │
│  │     downloaded: progress.get("downloaded", 0),          │   │
│  │     speed: progress.get("speed", 0),                    │   │
│  │     total_size: ...,                                    │   │
│  │ }                                                       │   │
│  │ self._callback(normalized)                              │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  app.py: WebSocket 消息转发                                     │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ emit("task_progress", normalized)                       │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ SSE event: task_progress
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 前端                                                            │
│                                                                 │
│  authorDetail.js: handleSSETaskProgress()                      │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ // 运行中：更新或插入 _activeTasks                       │   │
│  │ if (data.status === 'running') {                        │   │
│  │     const existing = _activeTasks.find(                 │   │
│  │         t => t.id === taskId                            │   │
│  │     );                                                  │   │
│  │     if (existing) {                                     │   │
│  │         // 更新现有任务                                  │   │
│  │         Object.assign(existing, {                       │   │
│  │             progress: ...,                              │   │
│  │             downloaded: ...,                            │   │
│  │             speed: ...                                  │   │
│  │         });                                             │   │
│  │     } else {                                            │   │
│  │         // 插入新任务                                    │   │
│  │         _activeTasks.push({...});                       │   │
│  │     }                                                   │   │
│  │ }                                                       │   │
│  │                                                          │   │
│  │ // 终态：从 _activeTasks 移除                            │   │
│  │ if (data.status === 'done' || data.status === 'error') {│   │
│  │     _activeTasks = _activeTasks.filter(                 │   │
│  │         t => t.id !== taskId                            │   │
│  │     );                                                  │   │
│  │ }                                                       │   │
│  │                                                          │   │
│  │ State.tasks.setAll(_activeTasks);                      │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  UI 组件                                                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ videoListRender.js: refreshActiveTasks()               │   │
│  │ // 遍历视频行，匹配活跃任务                              │   │
│  │ for (const video of filteredVideos) {                   │   │
│  │     const task = _activeTasks.find(                    │   │
│  │         t => t.video_id === video.id                   │   │
│  │     );                                                 │   │
│  │     if (task) {                                        │   │
│  │         // 显示下载进度条                                │   │
│  │         renderDownloadProgress(video.id, task);        │   │
│  │     } else {                                           │   │
│  │         // 隐藏下载进度条                                │   │
│  │         hideDownloadProgress(video.id);                │   │
│  │     }                                                  │   │
│  │ }                                                      │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 4.4 UI 组件响应

| 组件 | 订阅数据 | 响应行为 |
|------|---------|---------|
| 视频行下载框 | 任务状态 | 显示/隐藏下载进度条 |
| 下载进度条 | `progress`, `speed`, `downloaded` | 进度条动画、速度显示 |
| 状态栏监控状态 | `_activeTasks.length` | 显示活跃任务数 |

---

## 五、导入实体 (Import)

### 5.1 实体定义

导入实体负责管理 CSV/Excel/腾讯文档的导入进度。

**State 结构**：
```javascript
State.import = {
  phase: "idle",               // idle/start/processing/done
  total: 0,                    // 总数
  current: 0,                   // 当前进度
  success: 0,                   // 成功数
  fail: 0,                     // 失败数
  name: "",                     // 当前处理名称
  import_type: "",              // csv/excel/tencent_doc
}
```

### 5.2 SSE 事件

| 事件类型 | 触发时机 | 数据结构 |
|---------|---------|---------|
| `import_progress` | 导入过程中 | `{ phase, total, current, name, success, fail, import_type }` |

**后端触发点**：
- `core/api/routers/inputer.py` - CSV/Excel 导入
- `core/utils/excel_client.py` - Excel 导入
- `core/utils/tencent_doc.py` - 腾讯文档导入
- `core/monitor/doc_sync.py` - 文档同步监控

### 5.3 数据流程

```
┌─────────────────────────────────────────────────────────────────┐
│ 后端                                                            │
│                                                                 │
│  inputer.py / excel_client.py / tencent_doc.py                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ emit("import_progress", {                               │   │
│  │     phase: "start",                                     │   │
│  │     total: 100,                                          │   │
│  │     import_type: "csv"                                   │   │
│  │ })                                                       │   │
│  │                                                          │   │
│  │ for author in authors:                                   │   │
│  │     emit("import_progress", {                            │   │
│  │         phase: "processing",                            │   │
│  │         current: i,                                      │   │
│  │         name: author.name,                               │   │
│  │         success: success_count,                          │   │
│  │         fail: fail_count                                 │   │
│  │     })                                                   │   │
│  │                                                          │   │
│  │ emit("import_progress", {                                │   │
│  │     phase: "done",                                       │   │
│  │     success: success_count,                              │   │
│  │     fail: fail_count                                     │   │
│  │ })                                                       │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ SSE event: import_progress
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ 前端                                                            │
│                                                                 │
│  authorDetail.js                                                │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ es.addEventListener('import_progress', (e) => {         │   │
│  │     const data = JSON.parse(e.data);                   │   │
│  │                                                        │   │
│  │     // 文档监控事件由 DocSyncMonitor 处理               │   │
│  │     if (data.import_type === 'doc_sync') {            │   │
│  │         DocSyncMonitor.handleSSEProgress(data);        │   │
│  │         return;                                        │   │
│  │     }                                                  │   │
│  │                                                        │   │
│  │     // 其他导入事件由 ImportModal 处理                  │   │
│  │     ImportModal.handleSSEProgress(data);              │   │
│  │ });                                                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  State.import                                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ State.import.phase = data.phase;                        │   │
│  │ State.import.total = data.total;                        │   │
│  │ State.import.current = data.current;                   │   │
│  │ State.import.success = data.success;                   │   │
│  │ State.import.fail = data.fail;                         │   │
│  │ State.import.name = data.name;                         │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              │                                  │
│                              ▼                                  │
│  UI 组件                                                        │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ importModal.js: handleSSEProgress(data)                 │   │
│  │                                                          │   │
│  │ // 更新进度条                                            │   │
│  │ importProgressFill.style.width = `${progress}%`;        │   │
│  │ importProgressPercent.textContent = `${progress}%`;     │   │
│  │ importProgressLabel.textContent = data.name;           │   │
│  │                                                          │   │
│  │ // 更新计数器                                            │   │
│  │ importSuccessCount.textContent = data.success;         │   │
│  │ importFailCount.textContent = data.fail;               │   │
│  │ importTotalCount.textContent = data.total;              │   │
│  │                                                          │   │
│  │ // 完成时切换到结果视图                                   │   │
│  │ if (data.phase === 'done') {                            │   │
│  │     showResultView();                                   │   │
│  │ }                                                       │   │
│  └─────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
```

### 5.4 UI 组件响应

| 组件 | 订阅数据 | 响应行为 |
|------|---------|---------|
| 导入进度弹窗 | `phase`, `current`, `total` | 进度条动画 |
| 成功/失败计数器 | `success`, `fail` | 数字更新 |
| 当前处理项 | `name` | 显示当前处理名称 |
| 结果视图 | `phase === 'done'` | 显示成功/失败统计 |

---

## 六、事件命名规范

### 6.1 命名规则

```
<实体>_<动作>

例如：
- service_status      服务状态
- author_added        作者新增
- author_deleted      作者删除
- author_sync_completed 作者同步完成
- video_added         视频新增
- video_deleted       视频删除
- video_download_completed 视频下载完成
- task_created        任务创建
- task_progress       任务进度
- task_completed      任务完成
- task_deleted        任务删除
- import_progress     导入进度
- import_completed    导入完成
```

### 6.2 当前事件 vs 建议补充

| 实体 | 当前事件 | 建议补充事件 |
|------|---------|--------------|
| 服务 | `service_status` | `monitor_status`, `go_backend_version` |
| 作者 | `task_completed`（间接） | `author_added`, `author_deleted`, `author_sync_completed` |
| 视频 | `task_progress`, `task_completed` | `video_added`, `video_deleted`, `video_download_failed` |
| 任务 | `task_progress`, `task_completed` | `task_created`, `task_deleted`, `task_error` |
| 导入 | `import_progress` | `import_started`, `import_completed`, `import_error` |

---

## 七、前端 State 层设计

### 7.1 State 文件结构

```
static/js/api/state/
├── namespace.js          # State 命名空间定义
├── db.js                 # 数据库状态（authors, videos）
├── ui.js                 # UI 状态（currentPage, currentAuthor）
├── service.js            # 服务状态（go_online, wechat_connected）
└── tables/
    ├── catalog.js        # 作者目录数据
    ├── authors.js        # 作者详细数据
    ├── videos.js         # 视频数据
    └── tasks.js         # 任务数据
```

### 7.2 State API

```javascript
// 服务状态
State.service.setGoOnline(true);
State.service.setWechatConnected(true);
State.service.getGoOnline();

// 作者数据
State.authors.setAll(list);
State.authors.updateStats(author_id, stats);

// 视频数据
State.videos.set(author_id, video_id, data);
State.videos.get(author_id, video_id);

// 任务数据
State.tasks.setAll(activeTasks);
State.tasks.getByVideoId(video_id);

// 导入状态
State.import.setPhase('processing');
State.import.updateProgress(current, success, fail);
```

---

## 八、总结

### 8.1 数据流向

```
后端事件 → SSE 推送 → 前端监听 → State 更新 → UI 渲染
```

### 8.2 核心原则

1. **单一数据源**：每个实体的 State 只有一个来源
2. **事件驱动**：所有状态变化通过 SSE 事件触发
3. **响应式渲染**：UI 组件订阅 State 变化自动更新
4. **实体分组**：按实体类型组织 State 和事件处理

### 8.3 文件对应关系

| 实体 | 后端事件触发 | 前端事件处理 | State 定义 | UI 组件 |
|------|-------------|-------------|-----------|--------|
| 服务 | `service_status_push.py` | `authorDetail.js` | `State.service` | `status.js` |
| 作者 | `socket_client.py`, `task.py` | `authorDetail.js` | `State.authors` | `authorGridRender.js` |
| 视频 | `socket_client.py` | `authorDetail.js` | `State.videos` | `videoListRender.js` |
| 任务 | `socket_client.py`, `app.py` | `authorDetail.js` | `State.tasks` | `videoListRender.js` |
| 导入 | `inputer.py`, `excel_client.py` | `authorDetail.js` | `State.import` | `importModal.js` |
