# 作者详情页交互优化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在作者详情页添加全局进度条、优化"已下载"统计格式、增强下载弹窗数量显示、确认 Tab 数量标注已由现有逻辑覆盖。

**Architecture:** 纯前端修改，涉及 HTML 结构、CSS 样式、JS 逻辑三个层面。进度条和统计格式修改需同步更新 `videoListRender.js` 和 `reactiveRenderer.js` 两处逻辑，确保 SSE 推送更新时格式一致。Tab 数量标注已由 `ReactiveRenderer._updateTabLabels()` 实现，仅需验证调用时机。

**Tech Stack:** Vanilla JS (ES5/ES6 混合), CSS Custom Properties (Win11 Fluent Design), HTML5

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `static/index.html` | Modify | 添加进度条 HTML 结构，修改"已下载"统计 HTML |
| `static/css/styles.css` | Modify | 添加进度条、shimmer、呼吸动画 CSS |
| `static/js/component/videoListRender.js` | Modify | 修改 `updateAuthorStatsByType()` 显示 `X/Y` 格式 |
| `static/js/component/reactiveRenderer.js` | Modify | 修改 `_updateHeaderStats()` 显示 `X/Y` 格式，添加 `updateAuthorGlobalProgress()` 调用 |
| `static/js/datahandle/authorDetail.js` | Modify | 在 `loadAuthorDetail()` 和 `switchVideoType()` 后调用 `updateAuthorGlobalProgress()` |
| `static/js/component/authorProgress.js` | Create | 新增 `getDownloadingCountForCurrentType()` 和 `updateAuthorGlobalProgress()` 函数 |

---

### Task 1: 添加进度条 HTML 结构

**Files:**
- Modify: `static/index.html:141-145`

- [ ] **Step 1: 在 `#authorHeader` 统计行下方添加进度条 HTML**

在 `static/index.html` 第 145 行（`</div>` 关闭 `.author-stats-row`）之后、第 146 行（`</div>` 关闭 `.author-info-large` 内层 div）之前，插入：

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

- [ ] **Step 2: 修改"已下载"统计 HTML**

将第 144 行：
```html
              <span class="stat-item"><span id="authorDownloaded">0</span> 已下载</span>
```
改为：
```html
              <span class="stat-item"><span id="authorDownloaded">0/0</span> 已下载</span>
```

- [ ] **Step 3: 在 index.html 底部引入新 JS 文件**

在 `</body>` 前的 script 标签区域，添加：
```html
<script src="/js/component/authorProgress.js"></script>
```

确保此 script 标签在 `reactiveRenderer.js` 之后（因为 `updateAuthorGlobalProgress()` 依赖 `State` 和 `_catalogData`）。

- [ ] **Step 4: Commit**

```bash
git add static/index.html
git commit -m "feat(author-detail): add progress bar HTML structure and update downloaded stat format"
```

---

### Task 2: 添加进度条 CSS 样式

**Files:**
- Modify: `static/css/styles.css` (在 `.author-stats-row .stat-item span` 样式块后，约第 1322 行)

- [ ] **Step 1: 在 `.author-stats-row .stat-item span` 样式块后添加进度条样式**

在第 1322 行后追加：

```css
/* ========== 作者详情页全局进度条 ========== */
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

- [ ] **Step 2: Commit**

```bash
git add static/css/styles.css
git commit -m "feat(author-detail): add global progress bar CSS with shimmer and breathe animations"
```

---

### Task 3: 创建进度条 JS 逻辑

**Files:**
- Create: `static/js/component/authorProgress.js`

- [ ] **Step 1: 创建 `authorProgress.js` 文件**

```javascript
// 作者详情页全局进度条组件

// 辅助函数：获取当前作者+当前类型的正在下载数量
// 依赖全局变量 _activeTasks（由 SSE 推送维护的当前下载任务列表）
function getDownloadingCountForCurrentType() {
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

// 更新作者详情页全局进度条
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

- [ ] **Step 2: Commit**

```bash
git add static/js/component/authorProgress.js
git commit -m "feat(author-detail): add updateAuthorGlobalProgress() and getDownloadingCountForCurrentType()"
```

---

### Task 4: 修改"已下载"统计格式为 X/Y

**Files:**
- Modify: `static/js/component/videoListRender.js:76-91`
- Modify: `static/js/component/reactiveRenderer.js:343-356`

- [ ] **Step 1: 修改 `updateAuthorStatsByType()` 显示 `X/Y` 格式**

在 `static/js/component/videoListRender.js` 第 76-91 行，将 `updateAuthorStatsByType()` 函数修改为：

```javascript
function updateAuthorStatsByType(data) {
  console.log(`[updateAuthorStatsByType] 接收数据:`, data);
  const shortVideoEl = document.getElementById("authorShortVideo");
  const replayEl = document.getElementById("authorReplay");
  const downloadedEl = document.getElementById("authorDownloaded");

  if (shortVideoEl) shortVideoEl.textContent = data.short_video_count || 0;
  if (replayEl) replayEl.textContent = data.replay_count || 0;
  // downloaded 显示 "已下载/总数" 格式，明确关联当前类型
  const isReplay = _currentVideoType === 'live_replay';
  const downloadedCount = isReplay
    ? (data.replay_downloaded || 0)
    : (data.short_video_downloaded || 0);
  const totalForType = isReplay
    ? (data.replay_count || 0)
    : (data.short_video_count || 0);
  if (downloadedEl) downloadedEl.textContent = downloadedCount + '/' + totalForType;

  console.log(`[updateAuthorStatsByType] 更新后: 短视频=${data.short_video_count}, 回放=${data.replay_count}, 已下载=${downloadedCount}/${totalForType}`);
}
```

- [ ] **Step 2: 修改 `ReactiveRenderer._updateHeaderStats()` 显示 `X/Y` 格式**

在 `static/js/component/reactiveRenderer.js` 第 343-356 行，将 `_updateHeaderStats()` 方法修改为：

```javascript
  _updateHeaderStats: function(stats) {
    var shortVideoEl = document.getElementById('authorShortVideo');
    var replayEl = document.getElementById('authorReplay');
    var downloadedEl = document.getElementById('authorDownloaded');

    if (shortVideoEl) shortVideoEl.textContent = stats.short_video.total;
    if (replayEl) replayEl.textContent = stats.live_replay.total;

    // downloaded 显示 "已下载/总数" 格式，与 updateAuthorStatsByType() 保持一致
    var downloadedCount = this._currentVideoType === 'live_replay'
      ? stats.live_replay.downloaded
      : stats.short_video.downloaded;
    var totalForType = this._currentVideoType === 'live_replay'
      ? stats.live_replay.total
      : stats.short_video.total;
    if (downloadedEl) downloadedEl.textContent = downloadedCount + '/' + totalForType;
  },
```

- [ ] **Step 3: 修改 SSE 完成事件中的已下载更新**

在 `static/js/datahandle/authorDetail.js` 第 147 行，将：
```javascript
    document.getElementById("authorDownloaded").textContent = downloaded;
```
改为：
```javascript
    // 已下载显示 X/Y 格式：需要同时获取当前类型的总数
    var catEntry = _catalogData.find(function(c) { return c.username === username; });
    if (catEntry) {
      var isReplay = _currentVideoType === 'live_replay';
      var typeTotal = isReplay ? (catEntry.replay_count || 0) : (catEntry.short_video_count || 0);
      var typeDownloaded = isReplay ? (catEntry.replay_downloaded || 0) : (catEntry.short_video_downloaded || 0);
      document.getElementById("authorDownloaded").textContent = typeDownloaded + '/' + typeTotal;
    }
```

- [ ] **Step 4: Commit**

```bash
git add static/js/component/videoListRender.js static/js/component/reactiveRenderer.js static/js/datahandle/authorDetail.js
git commit -m "feat(author-detail): change downloaded stat to X/Y format in all update paths"
```

---

### Task 5: 在进度条更新时机调用 `updateAuthorGlobalProgress()`

**Files:**
- Modify: `static/js/datahandle/authorDetail.js:468-473` (loadAuthorDetail)
- Modify: `static/js/datahandle/authorDetail.js:63` (switchVideoType 回调)
- Modify: `static/js/component/reactiveRenderer.js:328-341` (_updateAllStats)

- [ ] **Step 1: 在 `loadAuthorDetail()` 完成后调用 `updateAuthorGlobalProgress()`**

在 `static/js/datahandle/authorDetail.js` 第 473 行（`updateAuthorStatsByType(...)` 调用之后），添加：

```javascript
  // 更新全局进度条
  if (typeof updateAuthorGlobalProgress === 'function') {
    updateAuthorGlobalProgress();
  }
```

同样，在第 516 行（增量同步后 `updateAuthorStatsByType(typeData.stats)` 之后），也添加同样的调用。

- [ ] **Step 2: 在 `switchVideoType()` 完成后调用 `updateAuthorGlobalProgress()`**

在 `static/js/component/videoListRender.js` 第 63 行（`updateAuthorStatsByType(data.stats)` 之后），添加：

```javascript
        // 更新全局进度条
        if (typeof updateAuthorGlobalProgress === 'function') {
          updateAuthorGlobalProgress();
        }
```

- [ ] **Step 3: 在 `ReactiveRenderer._updateAllStats()` 中调用 `updateAuthorGlobalProgress()`**

在 `static/js/component/reactiveRenderer.js` 第 340 行（`this._updateAuthorCardStats(username, stats);` 之后），添加：

```javascript
    // 更新全局进度条
    if (typeof updateAuthorGlobalProgress === 'function') {
      updateAuthorGlobalProgress();
    }
```

- [ ] **Step 4: Commit**

```bash
git add static/js/datahandle/authorDetail.js static/js/component/videoListRender.js static/js/component/reactiveRenderer.js
git commit -m "feat(author-detail): call updateAuthorGlobalProgress() at all stat update points"
```

---

### Task 6: 增强下载弹窗数量显示

**Files:**
- Modify: `static/js/component/dialog.js:73-170`

- [ ] **Step 1: 修改 `showDownloadRangeDialog()` 弹窗标题显示作者名**

当前 `showDownloadRangeDialog()` 已在选项中显示 `X 个待下载`（第 92 行 `option-desc`），但弹窗标题（第 116 行）只显示"下载全部待下载视频"，未显示作者名。

将第 116 行：
```javascript
	      <div class="dialog-title">下载全部待下载视频</div>
```
改为：
```javascript
	      <div class="dialog-title">下载全部待下载视频 — ${esc(nickname)}</div>
```

- [ ] **Step 2: Commit**

```bash
git add static/js/component/dialog.js
git commit -m "feat(author-detail): show author name in download range dialog title"
```

---

### Task 7: 验证 Tab 数量标注已由现有逻辑覆盖

**Files:**
- Modify: `static/js/component/reactiveRenderer.js:358-401` (验证，可能无需修改)

- [ ] **Step 1: 验证 `_updateTabLabels()` 在所有必要时机被调用**

`_updateTabLabels()` 由 `_updateAllStats()` 调用，`_updateAllStats()` 在以下时机触发：
1. `_onVideoStatusChange()` → SSE `videos:status` 事件 ✅
2. `refreshCurrentView()` → `switchVideoType()` 调用 ✅

需要确认 `loadAuthorDetail()` 完成后是否触发 `_updateAllStats()`。检查 `loadAuthorDetail()` 中的调用链：

- `loadAuthorDetail()` → `updateAuthorStatsByType()` → 直接更新 DOM，不经过 `_updateAllStats()`
- `loadAuthorDetail()` → 增量同步后 → `updateAuthorStatsByType()` → 同上

**结论**：`loadAuthorDetail()` 完成后，`_updateTabLabels()` 不会被自动调用。需要在 `loadAuthorDetail()` 中手动触发一次。

在 `static/js/datahandle/authorDetail.js` 中 `updateAuthorStatsByType(...)` 调用之后（与 Task 5 Step 1 相同位置），添加：

```javascript
  // 触发 Tab 数量标注更新
  if (typeof ReactiveRenderer !== 'undefined' && ReactiveRenderer._updateTabLabels) {
    var stats = State.videos.getStatsByType(username);
    if (stats) ReactiveRenderer._updateTabLabels(stats);
  }
```

- [ ] **Step 2: 验证 Tab HTML 使用 `data-tab` 属性**

检查 `static/index.html` 第 160-163 行，确认 Tab 按钮使用 `data-tab` 属性（`_updateTabLabels()` 通过 `document.querySelectorAll('.video-tab')` 和 `tab.dataset.tab` 查找）：

```html
<button class="video-tab active" data-tab="all" onclick="filterVideos('all')">全部</button>
<button class="video-tab" data-tab="downloading" onclick="filterVideos('downloading')">正在下载</button>
<button class="video-tab" data-tab="downloaded" onclick="filterVideos('downloaded')">已下载</button>
<button class="video-tab" data-tab="pending" onclick="filterVideos('pending')">未下载</button>
```

已确认：4 个 Tab 均有 `data-tab` 属性，与 `_updateTabLabels()` 的 switch 逻辑匹配。无需修改。

- [ ] **Step 3: Commit**

```bash
git add static/js/datahandle/authorDetail.js
git commit -m "fix(author-detail): trigger tab label update after loadAuthorDetail completes"
```

---

### Task 8: 移除诊断日志

**Files:**
- Modify: `static/js/component/authorGridRender.js`

- [ ] **Step 1: 移除 `renderAuthorListView()` 和 `renderAuthorCardView()` 中的诊断日志**

在 `static/js/component/authorGridRender.js` 中，删除以下诊断代码：

1. 第 115-118 行（`renderAuthorListView` 中的 console.log/warn）：
```javascript
  console.log('[renderAuthorListView] _catalogData length:', _catalogData.length);
  if (_catalogData.length > 0) {
    console.log('[renderAuthorListView] 第一个 catalog entry:', _catalogData[0]);
  }
```
和第 123-125 行：
```javascript
    if (!catMap[author.username]) {
      console.warn('[renderAuthorListView] author.username 未匹配到 catalog:', author.username);
    }
```

2. 第 196-199 行（`renderAuthorCardView` 中的 console.log/warn）：
```javascript
  console.log('[renderAuthorCardView] _catalogData length:', _catalogData.length);
  if (_catalogData.length > 0) {
    console.log('[renderAuthorCardView] 第一个 catalog entry:', _catalogData[0]);
  }
```
和第 204-206 行：
```javascript
    if (!catMap[author.username]) {
      console.warn('[renderAuthorCardView] author.username 未匹配到 catalog:', author.username);
    }
```

- [ ] **Step 2: Commit**

```bash
git add static/js/component/authorGridRender.js
git commit -m "chore: remove diagnostic logging from author grid render"
```

---

### Task 9: 手动验证

- [ ] **Step 1: 启动应用，进入作者详情页**

确认：
1. 进度条在统计行下方正确显示
2. "已下载"显示为 `X/Y` 格式（如 `2/3`）
3. 进度条文字显示 `已下载 2/3 个短视频 (67%)`
4. 二级 Tab 显示数量标注（如 `全部 (3)`、`已下载 (2)`）

- [ ] **Step 2: 切换到"直播回放" Tab**

确认：
1. 进度条更新为回放类型的统计
2. "已下载"更新为回放的 `X/Y` 格式
3. Tab 数量同步更新

- [ ] **Step 3: 点击"下载全部待下载"按钮**

确认弹窗标题显示作者名，选项显示各类型待下载数量。

- [ ] **Step 4: 开始下载一个视频**

确认：
1. 进度条 shimmer 动画激活
2. 右侧显示 `● 正在下载 1 个`（呼吸动画）
3. Tab 数量实时变化

- [ ] **Step 5: 下载完成后**

确认：
1. 进度条变为纯绿色
2. 右侧下载指示隐藏
3. "已下载"数字更新
4. Tab 数量更新
