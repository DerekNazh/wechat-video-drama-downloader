# 前端状态架构重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 消除前端5个权威源，建立 State 单一数据源，以 video_id 为主键，解决 Go 重启后进度归零/跑错/task_id 失配问题。

**Architecture:** State.tasks / State.videos 作为唯一权威源，全局变量 `_activeTasks` / `_authorVideosData` 降为只读视图（每次 State 更新后立即同步）。数据流单向：SSE/Poll → State → 全局变量(只读) → DOM。SSE direct DOM path 保留为进度更新快速路径，但有严格边界约束。

**Tech Stack:** Vanilla JS (ES5/ES6 mix), State layer (Map-based reactive store), SSE (EventSource), DOM manipulation

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `static/js/api/state/tables/tasks.js` | Modify | State.tasks 核心：video_id 主键、_taskIdIndex 反向索引、merge 语义 setAll、update 浅合并 |
| `static/js/api/state/tables/videos.js` | Modify | State.videos：新增 allGrouped() 方法 |
| `static/js/stateBridge.js` | Modify | 删除 bridgeGlobalsToState，全局变量同步改为 State.all() 赋值 |
| `static/js/app.js` | Modify | refreshActiveTasks 改为 merge；loadAllDataFromBackend 直接写 State；全局变量降只读 |
| `static/js/datahandle/authorDetail.js` | Modify | SSE handler 改 State.tasks.update；tasks_resumed 先刷新再 UI；进度过渡动画 showResumeTransition；所有 _activeTasks 直接写改 State 调用 |
| `static/js/component/videoListRender.js` | Modify | renderVideoList/updateVideoListIncremental 读取改为 State.tasks.all()/State.videos；switchVideoType 写入改为 State.videos |
| `static/js/component/reactiveRenderer.js` | Modify | 适配新 State.tasks 接口（getByVideoId → get） |
| `static/js/datahandle/videoOps.js` | Modify | cancelDownload 通过 getByTaskId 查找 |
| `static/js/component/status.js` | Modify | 离线标记 paused 保留原始 percent |

---

### Task 1: State.tasks 改造 — video_id 主键 + 反向索引 + merge 语义

**Files:**
- Modify: `static/js/api/state/tables/tasks.js`

- [ ] **Step 1: 读取当前 tasks.js 完整内容**

Read the full file to understand current structure before making changes.

- [ ] **Step 2: 重写 State.tasks 核心数据结构**

Replace the entire tasks.js with the new implementation. Key changes:
- Map key from `task.id` to `task.video_id`
- Add `_taskIdIndex` reverse index
- `setAll` does upsert-only (no delete), merge semantics, maintains reverse index
- `update` does shallow merge, emits `tasks:update` event, maintains reverse index
- `removeByVideoId` cleans both maps
- `getByTaskId` uses reverse index (O(1))

```javascript
// State.tasks — 以 video_id 为主键的任务状态表
(function() {

  var _tasks = new Map();       // key = video_id, value = task object
  var _taskIdIndex = new Map(); // key = task_id, value = video_id (反向索引)

  function _emit(event, data) {
    if (typeof State !== 'undefined' && State.emit) {
      State.emit(event, data);
    }
  }

  function _emitChanges(changes) {
    changes.forEach(function(c) {
      if (c.old) {
        _emit('tasks:update', { videoId: c.videoId, task: c.task, changes: c.old });
      } else {
        _emit('tasks:add', { videoId: c.videoId, task: c.task });
      }
    });
  }

  function setAll(list) {
    if (!Array.isArray(list)) return;
    var changes = [];
    list.forEach(function(task) {
      if (!task || !task.video_id) return;
      var key = task.video_id;
      var old = _tasks.get(key);
      var newTask;
      if (old) {
        // merge：保留 SSE 实时进度（percent/speed/downloaded/size），只同步后端字段
        newTask = {};
        for (var k in old) { if (old.hasOwnProperty(k)) newTask[k] = old[k]; }
        newTask.id = task.id;
        newTask.status = task.status;
        newTask.video_id = task.video_id;
        newTask.name = task.name || old.name;
      } else {
        newTask = task;
      }
      if (!old || old.id !== task.id) {
        newTask._taskIdChanged = true;
        newTask._oldPercent = old ? old.percent : 0;
        _taskIdIndex.set(task.id, key);
      }
      _tasks.set(key, newTask);
      changes.push({ videoId: key, task: newTask, old: old });
    });
    // 只做 upsert，不做删除
    // 删除由显式 removeByVideoId 调用完成
    _emitChanges(changes);
  }

  function get(videoId) {
    return _tasks.get(videoId) || null;
  }

  function getByTaskId(taskId) {
    var videoId = _taskIdIndex.get(taskId);
    return videoId ? _tasks.get(videoId) : null;
  }

  function update(videoId, patch) {
    var task = _tasks.get(videoId);
    if (!task) return;
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
    _emit('tasks:update', { videoId: videoId, task: updated, changes: patch });
  }

  function removeByVideoId(videoId) {
    var task = _tasks.get(videoId);
    if (task && task.id) {
      _taskIdIndex.delete(task.id);
    }
    _tasks.delete(videoId);
  }

  function removeByTaskId(taskId) {
    var videoId = _taskIdIndex.get(taskId);
    if (videoId) {
      removeByVideoId(videoId);
    }
  }

  function all() {
    return Array.from(_tasks.values());
  }

  function clear() {
    _tasks.clear();
    _taskIdIndex.clear();
  }

  function getByVideoId(videoId) {
    // 别名，兼容旧调用
    return get(videoId);
  }

  // 暴露公共接口
  window.State = window.State || {};
  window.State.tasks = {
    setAll: setAll,
    get: get,
    getByTaskId: getByTaskId,
    getByVideoId: getByVideoId,
    update: update,
    removeByVideoId: removeByVideoId,
    removeByTaskId: removeByTaskId,
    all: all,
    clear: clear
  };

})();
```

- [ ] **Step 3: 验证 State.tasks 在浏览器控制台可访问**

Open the app in browser DevTools console, verify:
- `State.tasks.all()` returns array
- `State.tasks.setAll([{video_id:'test',id:'t1',status:'running',percent:0}])` works
- `State.tasks.get('test')` returns the task
- `State.tasks.getByTaskId('t1')` returns the task
- `State.tasks.update('test', {percent: 50})` works and `State.tasks.get('test').percent === 50`
- `State.tasks.removeByVideoId('test')` works and `State.tasks.get('test') === null`

- [ ] **Step 4: Commit**

```bash
git add static/js/api/state/tables/tasks.js
git commit -m "refactor(state): State.tasks 以 video_id 为主键，增加反向索引和 merge 语义"
```

---

### Task 2: State.videos 改造 — 新增 allGrouped()

**Files:**
- Modify: `static/js/api/state/tables/videos.js`

- [ ] **Step 1: 读取当前 videos.js 完整内容**

- [ ] **Step 2: 新增 allGrouped() 方法**

在现有 State.videos 对象中新增 `allGrouped()` 方法，返回与 `_authorVideosData` 兼容的格式：

```javascript
function allGrouped() {
  // 返回格式: { username: { username, nickname, videos: { videoId: videoObj } } }
  var result = {};
  _authors.forEach(function(authorData, username) {
    result[username] = {
      username: authorData.username,
      nickname: authorData.nickname,
      videos: {}
    };
    if (authorData.videos) {
      authorData.videos.forEach(function(v, vid) {
        result[username].videos[vid] = v;
      });
    }
  });
  return result;
}
```

Add `allGrouped: allGrouped` to the exported State.videos object.

- [ ] **Step 3: 新增 setAuthorVideos() 方法**

允许直接写入（替代从 _authorVideosData 桥接）：

```javascript
function setAuthorVideos(username, videoList, nickname) {
  if (!username || !Array.isArray(videoList)) return;
  var videosMap = new Map();
  videoList.forEach(function(v) {
    if (v && v.id) videosMap.set(v.id, v);
  });
  _authors.set(username, {
    username: username,
    nickname: nickname || username,
    videos: videosMap
  });
  _emit('videos:loaded', { username: username, count: videoList.length });
}
```

Add `setAuthorVideos: setAuthorVideos` to the exported State.videos object.

- [ ] **Step 4: Commit**

```bash
git add static/js/api/state/tables/videos.js
git commit -m "refactor(state): State.videos 新增 allGrouped() 和 setAuthorVideos()"
```

---

### Task 3: stateBridge.js 单向化

**Files:**
- Modify: `static/js/stateBridge.js`

- [ ] **Step 1: 读取当前 stateBridge.js 完整内容**

- [ ] **Step 2: 删除 bridgeGlobalsToState 函数**

删除整个 `bridgeGlobalsToState` 函数定义和调用。State 层是权威源，禁止从全局变量反向写入 State。

- [ ] **Step 3: 修改 bridgePollUpdate 中的同步逻辑**

将全局变量赋值改为从 State 层读取：

```javascript
function bridgePollUpdate(data) {
  if (!data) return;

  // 任务数据 → State.tasks（权威源）
  if (data.tasks) {
    State.tasks.setAll(data.tasks);
  }

  // 同步只读视图
  if (typeof _activeTasks !== 'undefined') {
    _activeTasks = State.tasks.all();
  }

  // 视频数据 → State.videos（权威源）
  if (data.videos) {
    Object.keys(data.videos).forEach(function(username) {
      var vData = data.videos[username];
      if (vData && vData.videos) {
        State.videos.setAuthorVideos(username, Object.values(vData.videos), vData.nickname);
      }
    });
  }

  // 同步只读视图
  if (typeof _authorVideosData !== 'undefined') {
    _authorVideosData = State.videos.allGrouped();
  }
}
```

- [ ] **Step 4: Commit**

```bash
git add static/js/stateBridge.js
git commit -m "refactor(state): stateBridge 单向化，删除 bridgeGlobalsToState"
```

---

### Task 4: app.js — refreshActiveTasks merge 语义 + 全局变量降只读

**Files:**
- Modify: `static/js/app.js`

- [ ] **Step 1: 读取当前 app.js 完整内容**

- [ ] **Step 2: 改造 refreshActiveTasks 为 merge 语义**

找到 `refreshActiveTasks` 函数，将全量替换改为：

```javascript
async function refreshActiveTasks() {
  try {
    var resp = await fetch('/api/task/list');
    var data = await resp.json();
    var list = data.tasks || data || [];

    // State.tasks.setAll 已内置 merge 语义（video_id 主键，保留 SSE 实时进度）
    State.tasks.setAll(list);

    // 同步只读视图
    _activeTasks = State.tasks.all();
  } catch (e) {
    // fetch 失败时保持现有状态不变
  }
}
```

- [ ] **Step 3: 改造 loadAllDataFromBackend 直接写 State**

找到 `loadAllDataFromBackend` 函数，将写入 `_authorVideosData` 改为写入 State.videos：

```javascript
async function loadAllDataFromBackend() {
  try {
    var resp = await fetch('/api/video/all');
    var data = await resp.json();
    if (data && typeof data === 'object') {
      // 写入 State.videos（权威源）
      Object.keys(data).forEach(function(username) {
        var vData = data[username];
        if (vData && vData.videos) {
          State.videos.setAuthorVideos(username, Object.values(vData.videos), vData.nickname);
        }
      });
      // 同步只读视图
      _authorVideosData = State.videos.allGrouped();
    }
    return data;
  } catch (e) {
    return {};
  }
}
```

- [ ] **Step 4: Commit**

```bash
git add static/js/app.js
git commit -m "refactor(state): refreshActiveTasks merge 语义，loadAllDataFromBackend 直接写 State"
```

---

### Task 5: authorDetail.js — SSE handler 改造 + 进度过渡动画 + tasks_resumed 流程

这是改动量最大、风险最高的 Task。按子步骤拆分。

**Files:**
- Modify: `static/js/datahandle/authorDetail.js`

- [ ] **Step 5a: 新增 showResumeTransition 函数**

在文件顶部（全局变量声明区域后）添加：

```javascript
function showResumeTransition(videoId, fromPercent, toPercent) {
  var row = document.querySelector('.video-row[data-id="' + videoId + '"]');
  if (!row) return;
  var badge = row.querySelector('.video-status-badge');
  if (!badge) return;

  var taskId = '';
  var task = State.tasks.get(videoId);
  if (task) taskId = task.id || '';

  // 先确保 badge 切换为 downloading 状态（可能还处于 paused/resuming）
  badge.className = 'video-status-badge downloading';
  badge.innerHTML =
    '<div class="download-header">' +
      '<span class="progress-percent">' + toPercent + '%</span>' +
      '<button class="cancel-btn" onclick="event.stopPropagation(); cancelDownload(\'' + taskId + '\')" aria-label="取消下载">×</button>' +
    '</div>' +
    '<div class="progress-bar" role="progressbar" aria-valuenow="' + toPercent + '" aria-valuemin="0" aria-valuemax="100"><div class="progress-fill" style="width:' + fromPercent + '%"></div></div>' +
    '<div class="download-stats">' +
      '<span class="stat-size">--/--</span>' +
      '<span class="stat-divider"></span><span class="stat-speed muted">恢复中...</span>' +
    '</div>';
  row.classList.add('downloading');

  // 过渡动画：进度条从旧位置滑到新位置
  var fill = badge.querySelector('.progress-fill');
  if (fill) {
    fill.style.transition = 'width 0.5s ease-out';
    fill.style.width = toPercent + '%';
    setTimeout(function() { fill.style.transition = ''; }, 500);
  }
}
```

- [ ] **Step 5b: 改造 handleSSETaskProgress — 用 video_id 匹配 + State 写入**

找到 SSE `task_progress` 事件处理器中更新 `_activeTasks` 的逻辑。将所有 `_activeTasks` 直接写改为 State 调用：

核心改动：匹配逻辑从 `t.id === taskId` 改为 `t.video_id === videoId`，找不到时 fallback，找到后更新 task_id：

```javascript
// 之前：
// var taskIdx = _activeTasks.findIndex(function(t) { return t.id === taskId; });

// 之后：
var taskIdx = _activeTasks.findIndex(function(t) { return t.video_id === videoId; });
if (taskIdx < 0 && taskId) {
  // video_id 也没匹配到，用 task_id fallback
  taskIdx = _activeTasks.findIndex(function(t) { return t.id === taskId; });
  if (taskIdx >= 0 && videoId) {
    // task_id 匹配但 video_id 不匹配：更新 video_id（防御性）
    _activeTasks[taskIdx].video_id = videoId;
  }
}
if (taskIdx >= 0) {
  // 更新 task_id（Go 重启后可能已变）
  if (_activeTasks[taskIdx].id !== taskId) {
    _activeTasks[taskIdx].id = taskId;
  }
  // 写入 State（权威源）
  State.tasks.update(videoId || _activeTasks[taskIdx].video_id, {
    id: taskId,
    percent: data.percent !== undefined ? data.percent : _activeTasks[taskIdx].percent,
    speed: data.speed !== undefined ? data.speed : 0,
    downloaded: data.downloaded !== undefined ? data.downloaded : _activeTasks[taskIdx].downloaded,
    size: data.size !== undefined ? data.size : _activeTasks[taskIdx].size,
    status: 'running'
  });
  // 同步只读视图
  _activeTasks = State.tasks.all();
}
```

在匹配到任务后、更新 DOM 前，检查是否需要过渡动画：

```javascript
if (taskIdx >= 0) {
  var task = _activeTasks[taskIdx];
  // 进度回退检测：Go 重启后从 0% 重新下载
  if (task._oldPercent !== undefined && data.percent < task._oldPercent) {
    showResumeTransition(videoId || task.video_id, task._oldPercent, data.percent);
    State.tasks.update(videoId || task.video_id, { _oldPercent: undefined, _taskIdChanged: false });
    _activeTasks = State.tasks.all();
    return; // 过渡动画接管 DOM 更新，不继续走 updateSingleVideoProgress
  }
  // ... 原有 updateSingleVideoProgress 逻辑 ...
}
```

- [ ] **Step 5c: 改造 tasks_resumed 处理器 — 先刷新再 UI**

找到 SSE `tasks_resumed` 事件处理器，替换为：

```javascript
es.addEventListener('tasks_resumed', function(e) {
  var data = JSON.parse(e.data);
  var resumed = data.resumed || 0;
  var failed = data.failed || 0;
  if (resumed > 0) {
    // 先刷新任务列表（获取新 task_id）
    if (typeof refreshActiveTasks === 'function') {
      refreshActiveTasks().then(function() {
        // task_id 已更新，只改当前视图范围内的 badge
        var container = document.getElementById('videoListContainer');
        if (container) {
          container.querySelectorAll('.video-status-badge.paused').forEach(function(badge) {
            badge.className = 'video-status-badge resuming';
            badge.innerHTML = '恢复中...';
            badge.title = '正在恢复下载...';
          });
        }
        // 显示 toast
        if (typeof showToast === 'function') {
          var msg = '已恢复 ' + resumed + ' 个下载任务';
          if (failed > 0) msg += '，' + failed + ' 个恢复失败';
          showToast({ type: failed > 0 ? 'warning' : 'success', title: '断点续传', message: msg });
        }
      });
    }
  }
});
```

- [ ] **Step 5d: 改造其他 _activeTasks 直接写为 State 调用**

在 authorDetail.js 中搜索所有 `_activeTasks = _activeTasks.filter`、`_activeTasks.push`、`_activeTasks[idx] =` 的位置，逐一改为：

```javascript
// _activeTasks = _activeTasks.filter(...) →
State.tasks.removeByVideoId(videoId);
_activeTasks = State.tasks.all();

// _activeTasks.push(task) →
State.tasks.update(task.video_id, task);
_activeTasks = State.tasks.all();

// _activeTasks[taskIdx] = {...} →
State.tasks.update(task.video_id, updatedTask);
_activeTasks = State.tasks.all();
```

逐一替换，每次替换后确认上下文正确（特别是 videoId 变量的来源）。

- [ ] **Step 5e: 删除 tasks_resumed debounce timer**

删除之前添加的 `_tasksResumedDebounceTimer` 相关代码（不再需要，因为 tasks_resumed 现在先 refreshActiveTasks 再改 UI）。

- [ ] **Step 5f: Commit**

```bash
git add static/js/datahandle/authorDetail.js
git commit -m "refactor(state): SSE handler 改 State 写入，进度过渡动画，tasks_resumed 先刷新再 UI"
```

---

### Task 6: videoListRender.js — 读取改为 State 层

**Files:**
- Modify: `static/js/component/videoListRender.js`

- [ ] **Step 6a: 读取当前 videoListRender.js 完整内容**

- [ ] **Step 6b: 改造 renderVideoList 中的 _activeTasks 读取**

找到 `renderVideoList` 函数中构建 `downloadingIds` 和 `progressMap` 的逻辑，将 `_activeTasks` 读取改为 `State.tasks.all()`：

```javascript
// 之前：
// var activeTasks = _activeTasks;

// 之后：
var activeTasks = State.tasks.all();
```

- [ ] **Step 6c: 改造 _authorVideosData 读取**

将所有 `_authorVideosData` 直接读取改为 `State.videos.allGrouped()`：

```javascript
// 之前：
// var videos = _authorVideosData[username];

// 之后：
var grouped = State.videos.allGrouped();
var videos = grouped[username];
```

- [ ] **Step 6d: 改造 switchVideoType 中的 _authorVideosData 写入**

找到 `switchVideoType` 函数中修改 `_authorVideosData` 的位置，改为 State 调用：

```javascript
// 之前：_authorVideosData[username].videos = ...

// 之后：State.videos.setAuthorVideos(username, newVideoList, nickname);
// _authorVideosData = State.videos.allGrouped();
```

- [ ] **Step 6e: Commit**

```bash
git add static/js/component/videoListRender.js
git commit -m "refactor(state): videoListRender 读取改为 State 层"
```

---

### Task 7: reactiveRenderer.js — 适配新 State.tasks 接口

**Files:**
- Modify: `static/js/component/reactiveRenderer.js`

- [ ] **Step 7a: 改造 _isTaskActive**

```javascript
// 之前：
// var task = State.tasks.getByVideoId(videoId);

// 之后：
var task = State.tasks.get(videoId);
```

- [ ] **Step 7b: 改造 _onTaskCancel**

```javascript
// 之前：
// var task = State.tasks.get(taskId);

// 之后：
var task = State.tasks.getByTaskId(taskId);
```

- [ ] **Step 7c: Commit**

```bash
git add static/js/component/reactiveRenderer.js
git commit -m "refactor(state): reactiveRenderer 适配新 State.tasks 接口"
```

---

### Task 8: videoOps.js — cancelDownload 适配

**Files:**
- Modify: `static/js/datahandle/videoOps.js`

- [ ] **Step 8a: 读取当前 videoOps.js 完整内容**

- [ ] **Step 8b: 改造 cancelDownload 中的任务查找和删除**

找到 `cancelDownload` 函数，将 `_activeTasks.findIndex(t => t.id === taskId)` 改为通过 State 查找：

```javascript
function cancelDownload(taskId) {
  var task = State.tasks.getByTaskId(taskId);
  if (!task) return;

  // 添加到已取消列表
  if (typeof _cancelledTaskIds !== 'undefined') {
    _cancelledTaskIds[taskId] = Date.now();
  }

  // 从 State 删除
  State.tasks.removeByVideoId(task.video_id);
  _activeTasks = State.tasks.all();

  // ... 其余 API 调用保持不变 ...
}
```

- [ ] **Step 8c: 改造其他 _activeTasks 直接写**

搜索 videoOps.js 中所有 `_activeTasks` 直接写，改为 State 调用 + 同步。

- [ ] **Step 8d: Commit**

```bash
git add static/js/datahandle/videoOps.js
git commit -m "refactor(state): videoOps cancelDownload 适配 getByTaskId"
```

---

### Task 9: status.js — 离线标记 paused 保留原始 percent

**Files:**
- Modify: `static/js/component/status.js`

- [ ] **Step 9a: 改造离线标记逻辑**

找到 `updateStatusFromPoll` 中离线 debounce timer 内标记 paused 的逻辑，将 speed 置 0 但保留 percent：

```javascript
// 之前：
// _activeTasks = _activeTasks.map(function(t) {
//   return (t.status === 'running' || t.status === 'wait')
//     ? Object.assign({}, t, { status: 'paused', speed: 0 })
//     : t;
// });

// 之后：
_activeTasks.forEach(function(t) {
  if (t.status === 'running' || t.status === 'wait') {
    State.tasks.update(t.video_id, { status: 'paused', speed: 0 });
  }
});
_activeTasks = State.tasks.all();
State.tasks.setAll(_activeTasks);
```

- [ ] **Step 9b: Commit**

```bash
git add static/js/component/status.js
git commit -m "refactor(state): 离线标记 paused 保留原始 percent"
```

---

### Task 10: 集成验证

- [ ] **Step 10a: 正常下载流程验证**

1. 启动应用
2. 连接微信
3. 开始下载视频
4. 验证进度实时更新（badge 显示百分比、进度条、速度）
5. 取消下载 → badge 回到"待下载"
6. 下载完成 → badge 切换为"已下载"
7. 切换 Tab（全部/正在下载/已下载/待下载）→ 过滤正确

- [ ] **Step 10b: Go 服务重启验证**

1. 下载 3+ 个视频（进度到 30%+）
2. 停止 Go 服务
3. 等待前端显示"暂停"（3s 防抖后）
4. 验证暂停前进度数字保留（不是 0%）
5. 重新启动 Go 服务
6. 等待 tasks_resumed toast 弹出
7. 验证 badge 显示"恢复中"→ 进度从 0% 平滑过渡（0.5s 动画）
8. 验证进度不会"跑到"其他视频上
9. 验证 DevTools 中 `_activeTasks` 条目数与预期一致（无重复）

- [ ] **Step 10c: SSE 断连重连验证**

1. 正常下载中
2. 断开网络（或关闭 Go 服务）
3. 验证前端显示离线状态
4. 恢复网络
5. 验证 SSE 重连后状态同步

- [ ] **Step 10d: 控制台验证 State 层一致性**

在 DevTools 中执行：
```javascript
// 验证 State.tasks 和 _activeTasks 一致
State.tasks.all().length === _activeTasks.length

// 验证 video_id 主键工作
State.tasks.all().every(t => State.tasks.get(t.video_id) !== null)

// 验证反向索引工作
State.tasks.all().every(t => State.tasks.getByTaskId(t.id) !== null)
```
