# 任务完成记录功能设计文档

> **版本**: 1.0
> **日期**: 2026-05-31
> **状态**: 待实施

## 1. 概述

### 1.1 目标

实现全局任务完成记录功能，记录每一个视频下载完成事件，为用户提供下载历史追踪能力。

### 1.2 范围

- **记录范围**: 仅记录视频下载完成事件（`task_completed`）
- **不记录**: 任务创建、暂停、失败、取消等状态变化
- **全局性**: 不限于当前作者/页面，所有完成记录统一存储

### 1.3 核心约束

1. **非阻塞**: 记录写入失败不影响下载流程
2. **轻量**: 最小化存储和性能开销
3. **渐进增强**: 功能可选，不影响核心下载功能

---

## 2. 后端设计

### 2.1 数据存储

**表结构**:

```sql
CREATE TABLE IF NOT EXISTS task_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    author_id TEXT,
    title TEXT,
    cover_url TEXT,
    duration INTEGER DEFAULT 0,
    file_size INTEGER DEFAULT 0,
    completed_at TEXT NOT NULL,  -- ISO 8601 格式
    created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
);

-- 唯一约束：同一视频同一完成时间只记录一次
CREATE UNIQUE INDEX IF NOT EXISTS idx_task_log_unique 
    ON task_log(video_id, completed_at);

-- 反向查询索引
CREATE INDEX IF NOT EXISTS idx_task_log_video_id 
    ON task_log(video_id);
```

**字段说明**:

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | INTEGER | 自增主键 |
| `video_id` | TEXT | 视频唯一标识 |
| `author_id` | TEXT | 作者ID（可为空，处理作者删除场景） |
| `title` | TEXT | 视频标题 |
| `cover_url` | TEXT | 封面URL |
| `duration` | INTEGER | 视频时长（秒） |
| `file_size` | INTEGER | 文件大小（字节） |
| `completed_at` | TEXT | 任务完成时间（ISO 8601） |
| `created_at` | TEXT | 记录创建时间 |

### 2.2 写入触发点

**触发位置 1**: `core/monitor/socket_client.py:133`（WebSocket 推送完成）

`video_info` 来源：从 `task` 对象中提取，task 对象在 `socket_client.py` 中已包含 `video_id`、`title`、`cover_url`、`duration`、`file_size` 等字段。`author_id` 从当前监控的作者上下文获取。

```python
# 在 task_completed 事件处理后
try:
    _log_task_completion(task)
except Exception as e:
    logger.warning(f"记录任务完成失败: {e}")
```

**触发位置 2**: `core/service/task.py:149`（HTTP 轮询完成）

`video_info` 来源：`task` 对象本身已包含所需字段，无需额外查询。

```python
# 在状态更新为 completed/done 后
try:
    _log_task_completion(task)
except Exception as e:
    logger.warning(f"记录任务完成失败: {e}")
```

**写入函数**:

```python
def _log_task_completion(task: dict) -> None:
    """记录任务完成（非阻塞）"""
    with get_connection() as conn:
        conn.execute("""
            INSERT OR IGNORE INTO task_log 
            (video_id, author_id, title, cover_url, duration, file_size, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            task.get('video_id'),
            task.get('author_id', ''),
            task.get('title', ''),
            task.get('cover_url', ''),
            task.get('duration', 0),
            task.get('file_size', 0),
            datetime.now().isoformat()
        ))
```

### 2.3 清理策略

**触发时机**:
- 应用启动时执行一次
- 每小时检查一次（使用 `asyncio` 后台任务，启动后延迟 1 小时执行首次检查，之后每 1 小时执行一次）

**清理规则**:
- 保留最近 7 天的记录
- 超过 7 天的记录自动删除

```python
def _cleanup_old_logs() -> None:
    """清理过期记录"""
    with get_connection() as conn:
        conn.execute("""
            DELETE FROM task_log 
            WHERE created_at < datetime('now', '-7 days', 'localtime')
        """)
```

### 2.4 API 接口

**端点**: `GET /api/task/completion-log`

**参数**:

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `limit` | int | 50 | 返回条数上限（最大 100） |
| `offset` | int | 0 | 分页偏移 |

**响应**:

```json
{
  "code": 0,
  "data": {
    "total": 156,
    "items": [
      {
        "id": 1,
        "video_id": "xxx",
        "author_id": "author_xxx",
        "author_name": "作者名",
        "title": "视频标题",
        "cover_url": "https://...",
        "duration": 120,
        "file_size": 10485760,
        "completed_at": "2026-05-31T10:30:00"
      }
    ]
  }
}
```

**SQL 查询**:

```sql
SELECT 
    tl.id, tl.video_id, tl.author_id, 
    COALESCE(av.author_name, '') as author_name,
    tl.title, tl.cover_url, tl.duration, tl.file_size, tl.completed_at
FROM task_log tl
LEFT JOIN author_videos av ON tl.author_id = av.author_id
ORDER BY tl.completed_at DESC
LIMIT ? OFFSET ?
```

**注意**: 不依赖认证状态，未登录用户也可查看历史记录。

---

## 3. 前端设计

### 3.1 入口位置

**位置**: 底部状态抽屉右侧，新增"历史"标签页

```
┌─────────────────────────────────────────┐
│ [状态] [历史]                            │  ← 标签切换
├─────────────────────────────────────────┤
│ ● 服务在线                               │
│ ● 微信已连接                             │  ← 状态页（现有）
│ ○ 监控已停止                             │
│ 今日新增 12 已下载 8                      │
└─────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────┐
│ [状态] [历史]                            │
├─────────────────────────────────────────┤
│ ┌─────┐ 视频标题                         │
│ │封面 │ 作者名 · 2分钟前 · 15MB          │  ← 历史页（新增）
│ └─────┘                                  │
│ ┌─────┐ 另一个视频                       │
│ │封面 │ 作者名 · 1小时前 · 28MB          │
│ └─────┘                                  │
└─────────────────────────────────────────┘
```

### 3.2 交互设计

**标签切换**:
- 点击"历史"标签切换到历史记录视图
- 标签状态持久化（模块变量存储，刷新后保持）
- 默认显示"状态"标签

**历史列表**:
- 最多显示 8 条记录
- 按完成时间倒序排列
- 显示封面缩略图（48x48px，圆角 4px）
- 显示视频标题（单行，溢出省略）
- 显示作者名、相对时间、文件大小

**相对时间格式**:
- < 1 分钟: "刚刚"
- < 1 小时: "N 分钟前"
- < 24 小时: "N 小时前"
- < 7 天: "N 天前"

**点击行为**:
- 点击历史记录项 → 跳转到对应作者页面（如果作者存在）
- 作者已删除 → 显示 toast 提示"作者已移除"

**空状态**:
- 无记录时显示"暂无下载记录"

### 3.3 Toast 批量合并

**场景**: 批量下载完成时，避免连续弹出多个 toast

**策略**:
- 300ms 防抖窗口
- 窗口内多个 `task_completed` 事件合并为一个 toast
- 合并后显示"N 个视频下载完成"

**实现**:

```javascript
// static/js/component/toast.js
let _completionToastTimer = null;
let _completionCount = 0;

function showTaskCompletionToast(videoTitle) {
  _completionCount++;
  
  if (_completionToastTimer) {
    clearTimeout(_completionToastTimer);
  }
  
  _completionToastTimer = setTimeout(function() {
    if (_completionCount === 1) {
      showToast({ type: 'success', title: '下载完成', message: videoTitle });
    } else {
      showToast({ type: 'success', title: '下载完成', message: `${_completionCount} 个视频下载完成` });
    }
    _completionCount = 0;
    _completionToastTimer = null;
  }, 300);
}
```

### 3.4 数据流

**初始化**:
- SSE `onopen` 时懒加载 `State.logs`
- 与 `refreshActiveTasks()` 并行执行

```javascript
// static/js/datahandle/authorDetail.js
es.onopen = function() {
  // 现有逻辑...
  refreshActiveTasks();
  
  // 新增：懒加载历史记录
  if (!State.logs) {
    State.logs = { items: [], total: 0 };
    fetchCompletionLog();
  }
};
```

**实时更新**:
- 复用现有 `task_completed` SSE 事件
- 前端收到事件后，调用 `/api/task/completion-log?limit=8` 刷新列表

```javascript
// static/js/datahandle/authorDetail.js
case 'task_completed':
  // 现有逻辑...
  
  // 新增：刷新历史记录
  if (State.logs) {
    fetchCompletionLog(8);
  }
  
  // Toast 合并
  showTaskCompletionToast(e.data.title);
  break;
```

**API 调用**:

```javascript
// static/js/api/task.js
async function fetchCompletionLog(limit = 50, offset = 0) {
  const res = await fetch(`/api/task/completion-log?limit=${limit}&offset=${offset}`);
  const data = await res.json();
  if (data.code === 0) {
    State.logs = {
      items: data.data.items,
      total: data.data.total
    };
    renderHistoryList();
  }
}
```

### 3.5 渲染

**组件位置**: `static/js/component/historyPanel.js`（新文件）

**渲染函数**:

```javascript
function renderHistoryList() {
  const container = document.getElementById('historyList');
  if (!container) return;
  
  const items = State.logs?.items || [];
  
  if (items.length === 0) {
    container.innerHTML = '<div class="history-empty">暂无下载记录</div>';
    return;
  }
  
  container.innerHTML = items.map(item => `
    <div class="history-item" data-author-id="${item.author_id}" onclick="navigateToAuthor('${item.author_id}')">
      <img class="history-cover" src="${item.cover_url || ''}" alt="${item.title}">
      <div class="history-info">
        <div class="history-title">${escapeHtml(item.title)}</div>
        <div class="history-meta">
          <span class="history-author">${escapeHtml(item.author_name) || '未知作者'}</span>
          <span class="history-sep">·</span>
          <span class="history-time">${formatRelativeTime(item.completed_at)}</span>
          <span class="history-sep">·</span>
          <span class="history-size">${formatFileSize(item.file_size)}</span>
        </div>
      </div>
    </div>
  `).join('');
}
```

### 3.6 样式

**文件**: `static/css/styles.css`

```css
/* 历史面板 */
.history-panel {
  padding: 8px;
  max-height: 300px;
  overflow-y: auto;
}

.history-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px;
  border-radius: 6px;
  cursor: pointer;
  transition: background-color 0.15s ease;
}

.history-item:hover {
  background: rgba(0, 0, 0, 0.04);
}

.history-cover {
  width: 48px;
  height: 48px;
  border-radius: 4px;
  object-fit: cover;
  flex-shrink: 0;
  background: var(--bg-secondary);
}

.history-info {
  flex: 1;
  min-width: 0;
}

.history-title {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.history-meta {
  font-size: 11px;
  color: var(--text-tertiary);
  margin-top: 4px;
}

.history-author {
  max-width: 80px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: inline-block;
  vertical-align: bottom;
}

.history-sep {
  margin: 0 4px;
  opacity: 0.5;
}

.history-empty {
  text-align: center;
  padding: 24px;
  color: var(--text-tertiary);
  font-size: 13px;
}
```

---

## 4. 文件改动清单

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `core/db/schema.py` | 修改 | 添加 `task_log` 表定义 |
| `core/monitor/socket_client.py` | 修改 | 添加完成记录写入调用 |
| `core/service/task.py` | 修改 | 添加完成记录写入调用 + 清理调度 |
| `core/api/routers/task.py` | 修改 | 添加 `/api/task/completion-log` 端点 |
| `static/js/api/task.js` | 修改 | 添加 `fetchCompletionLog()` |
| `static/js/component/historyPanel.js` | 新建 | 历史面板渲染组件 |
| `static/js/component/toast.js` | 修改 | 添加 Toast 批量合并逻辑 |
| `static/js/datahandle/authorDetail.js` | 修改 | SSE 事件处理 + State.logs 初始化 |
| `static/js/api/state/index.js` | 修改 | 添加 `State.logs` 定义 |
| `static/index.html` | 修改 | 添加历史标签页 HTML 结构 |
| `static/css/styles.css` | 修改 | 添加历史面板样式 |

---

## 5. 风险评估

| 风险 | 等级 | 缓解措施 |
|------|------|----------|
| 写入失败影响下载 | 低 | try/except 包裹，仅 log warning |
| 数据库膨胀 | 低 | 7 天自动清理 + UNIQUE 约束去重 |
| 作者删除后引用失效 | 低 | LEFT JOIN + 空字符串 fallback |
| SSE 断连时记录不同步 | 低 | 下次连接时自动刷新 |
| 并发写入冲突 | 低 | INSERT OR IGNORE + UNIQUE 约束 |

---

## 6. 验收标准

1. **功能验收**:
   - [ ] 视频下载完成后，历史记录中出现对应条目
   - [ ] 批量下载完成时，显示合并后的 Toast
   - [ ] 点击历史记录可跳转到对应作者页面
   - [ ] 超过 7 天的记录自动清理

2. **性能验收**:
   - [ ] 历史记录加载时间 < 200ms
   - [ ] 写入操作不阻塞下载流程
   - [ ] 数据库文件大小增长可控（< 1MB/天）

3. **边界验收**:
   - [ ] 作者删除后，历史记录仍可显示（作者名为空）
   - [ ] 无记录时显示空状态提示
   - [ ] 网络异常时优雅降级（不显示历史面板）

---

## 7. 后续扩展（不在本次范围）

- [ ] 支持按作者筛选历史记录
- [ ] 支持搜索历史记录
- [ ] 支持导出下载历史
- [ ] 支持统计图表（每日下载量趋势）
