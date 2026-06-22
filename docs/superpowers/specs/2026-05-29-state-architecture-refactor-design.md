# 前端状态架构重构设计

## 问题

Go服务重启后出现3个现象：
1. 正在下载的任务进度归零
2. 进度"跑到"其他任务上
3. 10s后才弹出断点续传提示，且每次有1个任务恢复失败

根因不是某个变量的bug，而是前端状态管理架构存在系统性缺陷。

## 根因分析

### 5个权威源争抢同一个真相

| 权威源 | 位置 | 写入方 |
|--------|------|--------|
| `_activeTasks` 全局数组 | app.js | SSE handler, refreshActiveTasks, status.js, videoOps.js |
| `_authorVideosData` 全局对象 | app.js | SSE handler, loadAllDataFromBackend, loadAuthorDetail |
| `State.tasks` (Map) | tasks.js | setAll() from _activeTasks |
| `State.videos` (Map) | videos.js | setAllFromAuthorVideos() from _authorVideosData |
| DOM (视频行/badge) | HTML | SSE direct path, ReactiveRenderer |

### 核心缺陷

1. **task_id 不稳定**：Go重启后 `resume_download_task` 创建新 task_id，前端 `_activeTasks` 持旧 ID，SSE 推送新 ID 时找不到匹配
2. **全量替换语义**：`refreshActiveTasks()` 做 `_activeTasks = list.map(...)`，覆盖 SSE 正在写入的进度
3. **双向桥接**：stateBridge 双向同步，写入方向不确定
4. **SSE 双链路写 DOM**：SSE direct path 和 ReactiveRenderer 同时操作同一 badge

## 设计方案

### 方案选择

方案 B：State 单一权威源 + gopeed.db 容错备份（用户选择"前端优化，后端不改"变体）

后端保持现状（gopeed.db 被删除，resume 从0%开始），前端负责：
- 统一状态管理（单一权威源）
- 进度归零的UX过渡动画
- task_id 变化时自动适配

### 核心原则

1. **video_id 是唯一稳定的身份标识** — task_id 会变（Go重启），video_id 永远不变
2. **State 层是唯一权威源** — 全局变量降为只读视图
3. **单向数据流** — SSE/Poll → State → 全局变量(只读) → DOM
4. **Merge 语义** — 刷新任务列表时 merge 而非 replace，保留 SSE 实时进度

## 前端架构

### 目标数据流

```
SSE / Poll ──写入──→ State 层 ──读取──→ DOM
                        ↑
              全局变量 = State.all() 的只读快照
```

### State.tasks 改造

**当前**：`Map<taskId, task>`，以 task_id 为 key
**改为**：`Map<videoId, task>`，以 video_id 为 key

```javascript
var _tasks = new Map(); // key = video_id
var _taskIdIndex = new Map(); // key = task_id, value = video_id（反向索引，O(1)查找）

function setAll(list) {
  var changes = [];
  list.forEach(function(task) {
    var key = task.video_id;
    var old = _tasks.get(key);
    var newTask = old
      ? { ...old, id: task.id, status: task.status } // merge：保留SSE实时进度
      : task;
    if (!old || old.id !== task.id) {
      newTask._taskIdChanged = true;
      newTask._oldPercent = old ? old.percent : 0;
      _taskIdIndex.set(task.id, key); // 维护反向索引
    }
    _tasks.set(key, newTask);
    changes.push({ videoId: key, task: newTask, old: old });
  });
  // 只做 upsert，不做删除
  // 删除由显式调用 removeByVideoId 完成（终态处理：done/error/cancel）
  // 因为 /api/task/list 只返回活跃任务，不含已完成任务，
  // 如果 setAll 自动删除不在列表中的条目，终态事件还在路上时就会被误删
  _emitChanges(changes);
}

function get(videoId) { return _tasks.get(videoId); }
function getByTaskId(taskId) { var vid = _taskIdIndex.get(taskId); return vid ? _tasks.get(vid) : null; }
function update(videoId, patch) {
  var task = _tasks.get(videoId);
  if (!task) return;
  // 浅合并：patch 中的字段覆盖 task 中的同名字段
  var updated = {};
  for (var k in task) { if (task.hasOwnProperty(k)) updated[k] = task[k]; }
  for (var k in patch) { if (patch.hasOwnProperty(k)) updated[k] = patch[k]; }
  // 如果 task_id 变了，更新反向索引
  if (patch.id && patch.id !== task.id) {
    _taskIdIndex.delete(task.id);
    _taskIdIndex.set(patch.id, videoId);
    updated._taskIdChanged = true;
  }
  _tasks.set(videoId, updated);
  // 发射 tasks:update 事件，携带 videoId 和变化的字段
  State.emit('tasks:update', { videoId: videoId, task: updated, changes: patch });
}
function removeByVideoId(videoId) {
  var task = _tasks.get(videoId);
  if (task) _taskIdIndex.delete(task.id);
  _tasks.delete(videoId);
}
function all() { return Array.from(_tasks.values()); }
```

### State.videos 改造

**当前**：从 `_authorVideosData` 桥接
**改为**：直接管理，`loadAllDataFromBackend` 数据直接写入 State.videos

```javascript
var _videos = new Map(); // key = username, value = { videos: Map<videoId, video> }

function setAuthorVideos(username, videoList) {
  // 直接写入，不走 _authorVideosData
}
```

### 全局变量降级为只读视图

```javascript
// app.js
var _activeTasks = [];       // 只读！= State.tasks.all()
var _authorVideosData = {};  // 只读！= State.videos.allGrouped()
```

所有写入操作改为通过 State 层：
```javascript
// 之前：_activeTasks[idx].percent = 50;
// 之后：State.tasks.update(videoId, { percent: 50 }); _activeTasks = State.tasks.all();
```

### DOM 渲染链路

**SSE direct path** (handleSSETaskProgress → updateSingleVideoProgress) **保留**：
- 这是进度更新的快速路径（60fps），不能走 State 事件再 render
- 但 SSE handler 写入 State 层，而非直接写 `_activeTasks`

```javascript
function handleSSETaskProgress(taskId, videoId, data) {
  // 1. 更新 State（权威源）
  State.tasks.update(videoId, {
    id: taskId,
    percent: data.percent,
    speed: data.speed,
    downloaded: data.downloaded,
    size: data.size,
  });
  // 2. 同步只读视图
  _activeTasks = State.tasks.all();
  // 3. 直接更新 DOM（快速路径）
  updateSingleVideoProgress(videoId, data);
}
```

**ReactiveRenderer** 只处理终态变化（下载完成、取消、状态变化），不处理进度更新。

### SSE direct DOM path 的边界约束

SSE direct path 绕过 State 层直接写 DOM，这是性能妥协（60fps 进度更新不能走事件再 render）。
但这条路径有严格的边界约束，防止与 State → DOM 路径冲突：

**允许的操作**（SSE direct path 专用）：
- 更新 `.progress-percent` 文本
- 更新 `.progress-fill` 的 width 样式
- 更新 badge 的 title 属性（下载统计 tooltip）

**禁止的操作**（必须走 State → ReactiveRenderer 路径）：
- 改变 badge 的 className（如 downloading → downloaded）
- 改变 badge 的 innerHTML 结构（如添加/移除播放按钮）
- 改变 row 的 class（如添加/移除 downloading）
- 添加或移除 DOM 元素

违反这些约束的改动曾导致 resuming class 被 downloading 覆盖的 bug（已修复）。

### 进度归零的 UX 过渡动画

Go重启后 resume 创建新任务，SSE推送 `percent=0`。前端处理：

1. **收到 tasks_resumed** → 通过 State.tasks 每个 task 记住 `oldPercent`
2. **SSE 推送 percent < oldPercent** → 检测到进度回退（= 从0%重新下载）
3. **过渡动画**：badge 显示 "恢复中 (65%→0%)"，0.5s 动画从旧进度过渡到新进度
4. **过渡完成后**：正常显示实时进度

具体实现（在 handleSSETaskProgress 中）：
```javascript
var task = State.tasks.get(videoId);
if (task && task._oldPercent !== undefined && data.percent < task._oldPercent) {
  // 进度回退：显示过渡动画
  showResumeTransition(videoId, task._oldPercent, data.percent);
  // 清除标记
  State.tasks.update(videoId, { _oldPercent: undefined, _taskIdChanged: false });
}
```

showResumeTransition 实现：
```javascript
function showResumeTransition(videoId, fromPercent, toPercent) {
  var row = document.querySelector('.video-row[data-id="' + videoId + '"]');
  if (!row) return;
  var badge = row.querySelector('.video-status-badge');
  if (!badge) return;

  // 先确保 badge 是 downloading 状态（可能还处于 paused/resuming）
  var pct = toPercent;
  var taskId = State.tasks.get(videoId)?.id || '';
  var dlStr = '--';
  var szStr = '--';
  badge.className = 'video-status-badge downloading';
  badge.innerHTML =
    '<div class="download-header">' +
      '<span class="progress-percent">' + pct + '%</span>' +
      '<button class="cancel-btn" onclick="event.stopPropagation(); cancelDownload(\'' + taskId + '\')" aria-label="取消下载">×</button>' +
    '</div>' +
    '<div class="progress-bar" role="progressbar" aria-valuenow="' + pct + '" aria-valuemin="0" aria-valuemax="100"><div class="progress-fill" style="width:' + fromPercent + '%"></div></div>' +
    '<div class="download-stats">' +
      '<span class="stat-size">' + dlStr + '/' + szStr + '</span>' +
      '<span class="stat-divider"></span><span class="stat-speed muted">恢复中...</span>' +
    '</div>';
  row.classList.add('downloading');

  // 设置过渡动画：进度条从旧位置滑到新位置
  var fill = badge.querySelector('.progress-fill');
  if (fill) {
    fill.style.transition = 'width 0.5s ease-out';
    fill.style.width = toPercent + '%';
    setTimeout(function() { fill.style.transition = ''; }, 500);
  }
}
```

### tasks_resumed 处理流程

```javascript
es.addEventListener('tasks_resumed', function(e) {
  var data = JSON.parse(e.data);
  var resumed = data.resumed || 0;
  if (resumed > 0) {
    // 1. 先刷新任务列表（获取新 task_id）
    if (typeof refreshActiveTasks === 'function') {
      refreshActiveTasks().then(function() {
        // 2. task_id 已更新，只改当前作者视图范围内的 badge（避免误改其他作者）
        var container = document.getElementById('videoListContainer');
        if (container) {
          container.querySelectorAll('.video-status-badge.paused').forEach(function(badge) {
            badge.className = 'video-status-badge resuming';
            badge.innerHTML = '恢复中...';
          });
        }
        // 3. 显示 toast
        showToast({
          type: 'success',
          title: '断点续传',
          message: '已恢复 ' + resumed + ' 个下载任务'
        });
      });
    }
  }
});
```

## 改动文件清单

| 文件 | 改动 | 风险 |
|------|------|------|
| `static/js/api/state/tables/tasks.js` | Map key task_id → video_id；新增 getByTaskId、removeByVideoId；setAll 改 merge | 高 |
| `static/js/api/state/tables/videos.js` | 新增 allGrouped() 方法 | 低 |
| `static/js/stateBridge.js` | 删除 bridgeGlobalsToState；全局变量改为 State.all() 赋值 | 中 |
| `static/js/app.js` | refreshActiveTasks 改 merge；全局变量降只读；loadAllDataFromBackend 直接写 State | 高 |
| `static/js/datahandle/authorDetail.js` | SSE handler 改 State.tasks.update；tasks_resumed 先刷新再UI；进度过渡动画；所有 _activeTasks 直接写改 State 调用 | 高 |
| `static/js/component/videoListRender.js` | renderVideoList/updateVideoListIncremental 读取改为 State.tasks.all()/State.videos；switchVideoType 写入改为 State.videos | 高 |
| `static/js/component/reactiveRenderer.js` | 适配新 State.tasks 接口 | 低 |
| `static/js/datahandle/videoOps.js` | cancelDownload 通过 getByTaskId 查找 | 中 |
| `static/js/component/status.js` | 离线标记 paused 保留原始 percent | 低 |

### 只读视图同步时机

每次 `State.tasks.update()` / `State.videos.update()` 后，**立即**同步：
```javascript
_activeTasks = State.tasks.all();
_authorVideosData = State.videos.allGrouped();
```

这样所有读取全局变量的组件（videoSelect.js、authorDialog.js、pagination.js、dateFilter.js、authorProgress.js 等）拿到的都是最新数据，无需修改读取方式。

## 验证方案

1. **Go服务重启**：下载7视频 → 停Go → 重启 → 验证 badge 显示"恢复中(65%→0%)"过渡 → 进度从0%平滑增长
2. **task_id 变化**：DevTools 监控 SSE，确认 resume 后新 task_id 自动匹配旧条目，无重复
3. **正常下载**：开始/取消/完成/切换Tab 全流程
4. **SSE 断连重连**：断网→重连→状态同步
5. **进度跑错**：确认不再出现进度显示到其他视频上
