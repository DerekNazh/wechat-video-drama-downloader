# 全局进度条设计

## 目标

在作者详情页头部统计行下方增加全局进度条，让用户一眼了解当前作者的下载完成度，无需逐个查看视频状态。

## 位置

作者详情页头部，紧邻统计行（`3 短视频 · 0 回放 · 2 已下载`）下方。

## 布局

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

## 视觉规范

### 进度条

- 高度：8px，圆角 4px
- 已完成部分：渐变色 `var(--accent)` → `var(--success)`
- 未完成部分：`rgba(255,255,255,0.08)` 背景
- 下载进行中时：进度条上方有微弱光泽动画（shimmer），1.5s 循环
- 全部完成时：进度条变为纯 `var(--success)` 色

### 文字信息

- 左侧：`已下载 X/Y 个[类型] (Z%)`
  - `[类型]` 根据当前选中的视频类型 Tab 动态切换（"短视频" 或 "直播回放"）
  - Z% = 下载完成百分比，取整
- 右侧：`● 正在下载 N 个`
  - 仅在有当前类型的下载任务时显示
  - 圆点带呼吸动画（opacity 0.5 → 1，1.5s 循环）
  - 无下载任务时隐藏

### 状态变化

| 状态 | 进度条 | 右侧指示 |
|------|--------|----------|
| 无下载任务 | 静态，显示当前完成比例 | 隐藏 |
| 有下载任务 | shimmer 动画 | `● 正在下载 N 个`（呼吸动画） |
| 全部完成 | 纯绿色 | 隐藏 |

## 数据来源

### 统计数据

从 `_catalogData` 获取当前作者的分类统计：

- `short_video_count` / `short_video_downloaded`：短视频总数/已下载数
- `replay_count` / `replay_downloaded`：回放总数/已下载数

根据当前选中的视频类型 Tab（`_currentVideoType`）选择对应字段。

### 正在下载数

从 `_activeTasks` 过滤：当前作者 + 当前类型的正在下载任务数量。

## 更新时机

1. **进入作者详情页时**：`loadAuthorDetail()` 初始化进度条
2. **SSE 推送**：`tasks:update` / `tasks:complete` / `tasks:cancel` 时更新
3. **切换视频类型 Tab**：短视频 ↔ 直播回放时重新计算
4. **视频状态变化**：`videos:status` 事件触发时更新

## HTML 结构

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

## CSS 关键样式

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
  background: rgba(255, 255, 255, 0.08);
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
  background: linear-gradient(90deg, transparent, rgba(255,255,255,0.15), transparent);
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

## JS 更新逻辑

新增函数 `updateAuthorGlobalProgress()`，在以下位置调用：

1. `loadAuthorDetail()` 完成后
2. `ReactiveRenderer._updateHeaderStats()` 中
3. 视频类型 Tab 切换时

```javascript
// 辅助函数：获取当前作者+当前类型的正在下载数量
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

function updateAuthorGlobalProgress() {
  var cat = _catalogData.find(function(c) {
    return c.username === _currentAuthor.username;
  });
  if (!cat) return;

  var isReplay = _currentVideoType === 'live_replay';
  var total = isReplay ? cat.replay_count : cat.short_video_count;
  var downloaded = isReplay ? cat.replay_downloaded : cat.short_video_downloaded;
  var percent = total > 0 ? Math.round((downloaded / total) * 100) : 0;

  // 进度条
  var fill = document.getElementById('authorProgressFill');
  if (fill) {
    fill.style.width = percent + '%';
    fill.classList.toggle('complete', percent === 100);
  }

  // shimmer 动画
  var shimmer = document.getElementById('authorProgressShimmer');
  var downloadingCount = getDownloadingCountForCurrentType();
  if (shimmer) {
    shimmer.classList.toggle('active', downloadingCount > 0);
  }

  // 文字
  var text = document.getElementById('authorProgressText');
  var typeName = isReplay ? '直播回放' : '短视频';
  if (text) {
    text.textContent = '已下载 ' + downloaded + '/' + total + ' 个' + typeName + ' (' + percent + '%)';
  }

  // 下载指示
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

## 测试要点

1. 进入作者详情页时进度条正确显示
2. 切换短视频/直播回放 Tab 时进度条更新
3. 下载进行中时 shimmer 动画激活
4. 下载完成后进度条变为纯绿色
5. 无下载任务时右侧指示隐藏
6. SSE 推送更新时进度条实时刷新
