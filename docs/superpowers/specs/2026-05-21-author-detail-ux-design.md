# 作者详情页交互优化设计

覆盖问题 #1-4：
1. 缺少全局进度条
2. 统计"已下载"含义模糊
3. "下载全部待下载"按钮无确认
4. 二级 Tab 无数量标注

---

## 1. 全局进度条

### 位置

作者详情页头部，紧邻统计行下方。

### 布局

```
┌─────────────────────────────────────────────────────────────┐
│ [头像] 作者名称                                              │
│        3 短视频 · 0 回放 · 2 已下载                          │
│                                                              │
│ ┌─────────────────────────────────────────────────────────┐ │
│ │ ████████████░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │ │
│ │ 已下载 2/3 个短视频 (67%)                    ● 正在下载 1 │ │
│ └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

### 视觉规范

**进度条：**
- 高度：8px，圆角 4px
- 已完成部分：渐变色 `var(--accent)` → `var(--success)`
- 未完成部分：`var(--border)` 背景
- 下载进行中时：shimmer 动画（1.5s 循环）
- 全部完成时：进度条变为纯 `var(--success)` 色

**文字信息：**
- 左侧：`已下载 X/Y 个[类型] (Z%)`
  - `[类型]` 根据当前视频类型 Tab 动态切换（"短视频" 或 "直播回放"）
- 右侧：`● 正在下载 N 个`
  - 仅在有当前类型的下载任务时显示
  - 圆点带呼吸动画（opacity 0.5 → 1，1.5s 循环）
  - 无下载任务时隐藏

**状态变化：**

| 状态 | 进度条 | 右侧指示 |
|------|--------|----------|
| 无下载任务 | 静态，显示当前完成比例 | 隐藏 |
| 有下载任务 | shimmer 动画 | `● 正在下载 N 个`（呼吸动画） |
| 全部完成 | 纯绿色 | 隐藏 |
| 当前类型 0 个视频 | 进度条隐藏，文字显示"已下载 0/0 个[类型] (0%)" | 隐藏 |

### HTML

在 `#authorHeader` 统计行下方添加：

```html
<div class="author-progress-section" id="authorProgressSection">
  <div class="author-progress-bar-wrapper">
    <div class="author-progress-bar" id="authorProgressBar">
      <div class="author-progress-fill" id="authorProgressFill" style="width: 0%"></div>
      <div class="author-progress-shimmer" id="authorProgressShimmer"></div>
    </div>
  </div>
  <div class="author-progress-info">
    <span class="author-progress-text" id="authorProgressText">已下载 0/0 个短视频 (0%)</span>
    <span class="author-progress-downloading" id="authorProgressDownloading"></span>
  </div>
</div>
```

### CSS

```css
.author-progress-section {
  margin-top: 8px;
  padding: 0 4px;
}

.author-progress-bar-wrapper {
  width: 100%;
}

.author-progress-bar {
  height: 8px;
  border-radius: 4px;
  background: var(--border);
  overflow: hidden;
  position: relative;
}

.author-progress-fill {
  height: 100%;
  border-radius: 4px;
  background: linear-gradient(90deg, var(--accent), var(--success));
  transition: width 0.4s ease;
}

.author-progress-fill.complete {
  background: var(--success);
}

.author-progress-shimmer {
  position: absolute;
  top: 0;
  left: -100%;
  width: 100%;
  height: 100%;
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.2), transparent);
  animation: none;
}

.author-progress-shimmer.active {
  animation: shimmer 1.5s infinite;
}

@keyframes shimmer {
  0% { left: -100%; }
  100% { left: 100%; }
}

.author-progress-info {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-secondary);
}

.author-progress-downloading {
  color: var(--accent);
  display: none;
}

.author-progress-downloading.active {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.author-progress-downloading .dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent);
  animation: breathe 1.5s ease-in-out infinite;
}

@keyframes breathe {
  0%, 100% { opacity: 0.5; }
  50% { opacity: 1; }
}
```

### JS

新增函数 `updateAuthorGlobalProgress()`，在以下位置调用：
1. `loadAuthorDetail()` 完成后
2. `ReactiveRenderer._updateHeaderStats()` 中
3. 视频类型 Tab 切换时

```javascript
function getDownloadingCountForCurrentType() {
  // 依赖全局变量 _activeTasks（由 SSE 推送维护的当前下载任务列表）
  if (typeof _activeTasks === 'undefined' || !_activeTasks) return 0;
  return _activeTasks.filter(function(t) {
    if (!t || !t.video_id) return false;
    var video = State.videos.get(State.videos.getAuthorByVideoId(t.video_id), t.video_id);
    if (!video) return false;
    var videoType = video.video_type || 'short_video';
    var videoAuthor = State.videos.getAuthorByVideoId(t.video_id);
    return videoType === _currentVideoType && videoAuthor === _currentAuthor.username;
  }).length;
}

function updateAuthorGlobalProgress() {
  if (!_currentAuthor) return;
  var cat = _catalogData.find(function(c) {
    return c.username === _currentAuthor.username;
  });
  if (!cat) return;

  var isReplay = _currentVideoType === 'live_replay';
  var total = isReplay ? cat.replay_count : cat.short_video_count;
  var downloaded = isReplay ? cat.replay_downloaded : cat.short_video_downloaded;
  var percent = total > 0 ? Math.round((downloaded / total) * 100) : 0;

  // 进度条：0 个视频时隐藏进度条，只显示文字
  var barWrapper = document.querySelector('.author-progress-bar-wrapper');
  if (barWrapper) {
    barWrapper.style.display = total > 0 ? '' : 'none';
  }

  var fill = document.getElementById('authorProgressFill');
  if (fill) {
    fill.style.width = percent + '%';
    fill.classList.toggle('complete', percent === 100);
  }

  var shimmer = document.getElementById('authorProgressShimmer');
  var downloadingCount = getDownloadingCountForCurrentType();
  if (shimmer) {
    shimmer.classList.toggle('active', downloadingCount > 0);
  }

  var text = document.getElementById('authorProgressText');
  var typeName = isReplay ? '直播回放' : '短视频';
  if (text) {
    text.textContent = '已下载 ' + downloaded + '/' + total + ' 个' + typeName + ' (' + percent + '%)';
  }

  var dl = document.getElementById('authorProgressDownloading');
  if (dl) {
    if (downloadingCount > 0) {
      dl.classList.add('active');
      dl.innerHTML = '<span class="dot"></span> 正在下载 ' + downloadingCount + ' 个';
    } else {
      dl.classList.remove('active');
    }
  }
}
```

---

## 2. 统计"已下载"含义优化

### 问题

当前统计行显示 `3 短视频 · 0 回放 · 2 已下载`，其中"已下载"只显示当前类型的已下载数，用户误以为是总已下载数。

### 修改

将统计行改为：

```
3 短视频 · 0 回放 · 已下载 2/5
```

"已下载"改为显示 `已下载 [当前类型已下载]/[当前类型总数]`，明确关联当前类型。

### HTML 修改

将 `index.html` 第 144 行改为：

```html
<span class="stat-item"><span id="authorDownloaded">0/0</span> 已下载</span>
```

### JS 修改

需同时修改两处，确保统计行"已下载"格式一致：

**1. `videoListRender.js` 中 `updateAuthorStatsByType()`：**

```javascript
// 旧：downloadedEl.textContent = downloadedCount;
// 新：显示 "已下载/总数" 格式
if (downloadedEl) downloadedEl.textContent = downloadedCount + '/' + total;
```

其中 `total` 和 `downloadedCount` 根据当前类型计算：

```javascript
var total = isReplay ? data.replay_count : data.short_video_count;
var downloadedCount = isReplay ? data.replay_downloaded : data.short_video_downloaded;
```

**2. `reactiveRenderer.js` 中 `ReactiveRenderer._updateHeaderStats()`：**

```javascript
// 旧：downloadedEl.textContent = downloadedCount;
// 新：显示 "已下载/总数" 格式
var totalForType = this._currentVideoType === 'live_replay'
  ? stats.live_replay.total
  : stats.short_video.total;
if (downloadedEl) downloadedEl.textContent = downloadedCount + '/' + totalForType;
```

两处必须保持格式一致（`X/Y`），避免 SSE 推送更新时格式与初始加载不同。

---

## 3. "下载全部待下载"按钮确认优化

### 问题

当前 `downloadAllPending()` 已经有 `showDownloadRangeDialog()` 弹窗让用户选择下载类型（短视频/回放/全部），但弹窗标题不够明确，用户无法预知下载数量。

### 修改

在 `showDownloadRangeDialog()` 弹窗中增加数量信息：

```
下载全部待下载视频 — 天天象棋

选择要下载的视频类型：

  ● 短视频（38 个待下载）
  ● 直播回放（17 个待下载）
  ● 全部类型（55 个待下载）

[开始下载]
```

### 实现位置

修改 `static/js/component/dialog.js` 中 `showDownloadRangeDialog()` 函数，在选项文本中追加数量。

传入参数 `shortVideoPending` 和 `replayPending` 已有，只需在选项文本中显示：

```javascript
// 旧：label = '短视频'
// 新：label = '短视频（' + shortVideoPending + ' 个待下载）'
```

**数据来源**：`shortVideoPending` 和 `replayPending` 由调用方 `downloadAllPending()` 计算并传入。调用方从 `_catalogData` 获取当前作者的 `short_video_count - short_video_downloaded` 和 `replay_count - replay_downloaded`。无需修改调用方逻辑，只需在 `showDownloadRangeDialog()` 的选项文本中使用已有参数。

---

## 4. 二级 Tab 数量标注

### 问题

二级 Tab（全部/正在下载/已下载/未下载）没有显示对应数量，用户无法预知每个 Tab 下有多少视频。

### 修改

在每个 Tab 文本后追加数量，格式：`全部 (3)` / `正在下载 (1)` / `已下载 (2)` / `未下载 (0)`。

### 数据来源

从当前类型的视频列表计算：
- 全部：当前类型视频总数
- 正在下载：当前类型正在下载数（从 `_activeTasks` 过滤）
- 已下载：当前类型已下载数
- 未下载：全部 - 已下载 - 正在下载

### JS 实现

新增函数 `updateVideoTabCounts()`，在以下时机调用：
1. `loadAuthorDetail()` 完成后
2. `switchVideoType()` 切换类型后
3. SSE 推送更新视频状态时

### 与 ReactiveRenderer._updateTabLabels() 的关系

`ReactiveRenderer._updateTabLabels()` 已有完整的 Tab 数量更新逻辑（含 `baseText` 缓存、`downloadingCount` 计算），**无需新增 `updateVideoTabCounts()` 函数**。

现有 `_updateTabLabels()` 的计算逻辑与本文档一致：
- `all` → `typeStats.total`
- `downloaded` → `typeStats.downloaded`
- `downloading` → 从 `State.tasks.getRunning()` 过滤当前类型
- `pending` → `total - downloaded - downloadingCount`

**唯一需要确认**：`_updateTabLabels()` 的调用时机是否覆盖所有场景。当前调用点为 `ReactiveRenderer._onStatsUpdate()`，需确保以下时机均触发 `_onStatsUpdate()`：
1. `loadAuthorDetail()` 完成后
2. `switchVideoType()` 切换类型后
3. SSE 推送 `tasks:update` / `tasks:complete` / `tasks:cancel` 时
4. `videos:status` 事件触发时

若以上时机均已覆盖，则 #4 无需额外代码修改，Tab 数量标注已由现有逻辑实现。

---

## 更新时机汇总

所有四个功能的更新时机统一为：

1. `loadAuthorDetail()` 完成后
2. `switchVideoType()` 切换类型后
3. `ReactiveRenderer._updateHeaderStats()` 中
4. SSE 推送 `tasks:update` / `tasks:complete` / `tasks:cancel` 时
5. `videos:status` 事件触发时

统一调用入口：在 `ReactiveRenderer._updateHeaderStats()` 中追加 `updateAuthorGlobalProgress()`。

#4（Tab 数量标注）已由现有 `ReactiveRenderer._updateTabLabels()` 实现，无需新增函数。只需确认 `_updateTabLabels()` 的调用时机覆盖以上所有场景。

## 全局变量依赖

- `_activeTasks`：当前下载任务列表，由 SSE 推送维护。`getDownloadingCountForCurrentType()` 依赖此变量过滤当前作者+当前类型的正在下载数量。
- `_catalogData`：作者分类统计数据，由 `/api/video/all` 接口返回。`updateAuthorGlobalProgress()` 依赖此变量获取 `short_video_count` / `replay_count` / `short_video_downloaded` / `replay_downloaded`。

---

## 测试要点

1. 进入作者详情页时进度条正确显示
2. 切换短视频/直播回放 Tab 时进度条、统计行、Tab 数量同步更新
3. 下载进行中时 shimmer 动画激活，Tab 数量实时变化
4. 下载完成后进度条变为纯绿色
5. 无下载任务时右侧指示隐藏
6. 统计行"已下载"显示为 `2/3` 格式而非单独数字
7. 下载弹窗显示各类型的待下载数量
8. 二级 Tab 显示数量标注，且数量随状态变化实时更新
9. SSE 推送更新时所有 UI 元素实时刷新