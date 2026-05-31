# 任务完成记录功能实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现全局任务完成记录功能，记录视频下载完成事件，提供历史记录 UI

**Architecture:** 后端 SQLite `task_log` 表 + 双触发点写入（WebSocket + HTTP 轮询）+ 7天自动清理；前端 State.logs 表模块 + 状态抽屉历史标签页 + Toast 批量合并

**Tech Stack:** Python/FastAPI (后端), Vanilla JS (前端), SQLite WAL

---

## Task 1: 数据库表定义

**Files:**
- Modify: `core/utils/database/base.py:167-169`

- [ ] **Step 1: 在 `_init_db()` 末尾添加 `task_log` 表**

在 `base.py` 行 167（最后一个 ALTER TABLE）之后、行 169（`logger.info`）之前插入：

```python
        # 任务完成记录表
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS task_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                video_id TEXT NOT NULL,
                author_id TEXT,
                username TEXT,
                title TEXT,
                cover_url TEXT,
                duration INTEGER DEFAULT 0,
                file_size INTEGER DEFAULT 0,
                completed_at TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime'))
            )
        """)
        cursor.execute("""
            CREATE UNIQUE INDEX IF NOT EXISTS idx_task_log_unique 
            ON task_log(video_id, completed_at)
        """)
        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_task_log_video_id 
            ON task_log(video_id)
        """)
```

- [ ] **Step 2: 启动应用验证表创建**

运行应用，检查日志中 `_init_db` 是否成功创建 `task_log` 表。用 SQLite 工具确认表结构。

- [ ] **Step 3: Commit**

```bash
git add core/utils/database/base.py
git commit -m "feat: 添加 task_log 表定义（任务完成记录）"
```

---

## Task 2: 后端写入函数 + DAO 方法

**Files:**
- Modify: `core/utils/database/base.py` (添加代理方法)
- Create: `core/utils/database/crud/log_dao.py` (新建 DAO)

- [ ] **Step 1: 创建 `log_dao.py`**

```python
# core/utils/database/crud/log_dao.py
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


def insert_log(cursor, video_id: str, author_id: str, username: str,
               title: str, cover_url: str, duration: int, file_size: int,
               completed_at: str) -> None:
    cursor.execute("""
        INSERT OR IGNORE INTO task_log 
        (video_id, author_id, username, title, cover_url, duration, file_size, completed_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (video_id, author_id, username, title, cover_url, duration, file_size, completed_at))


def query_logs(cursor, limit: int = 50, offset: int = 0) -> list:
    cursor.execute("""
        SELECT 
            tl.id, tl.video_id, tl.author_id, tl.username,
            COALESCE(a.name, '') as author_name,
            tl.title, tl.cover_url, tl.duration, tl.file_size, tl.completed_at
        FROM task_log tl
        LEFT JOIN authors a ON tl.author_id = a.id
        ORDER BY tl.completed_at DESC
        LIMIT ? OFFSET ?
    """, (limit, offset))
    columns = ['id', 'video_id', 'author_id', 'username', 'author_name',
               'title', 'cover_url', 'duration', 'file_size', 'completed_at']
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


def count_logs(cursor) -> int:
    cursor.execute("SELECT COUNT(*) FROM task_log")
    return cursor.fetchone()[0]


def cleanup_old_logs(cursor, days: int = 7) -> int:
    cursor.execute("""
        DELETE FROM task_log 
        WHERE created_at < datetime('now', ? || ' days', 'localtime')
    """, (str(-days),))
    return cursor.rowcount
```

- [ ] **Step 2: 在 `base.py` Database 类中添加代理方法**

在 `base.py` 的 Database 类中（现有代理方法之后，如 `get_author_video` 之后）添加：

```python
    # ---- 任务完成记录 ----
    def log_task_completion(self, video_id: str, author_id: str = '',
                            username: str = '', title: str = '',
                            cover_url: str = '', duration: int = 0,
                            file_size: int = 0, completed_at: str = '') -> None:
        with self._cursor() as cursor:
            from core.utils.database.crud.log_dao import insert_log
            insert_log(cursor, video_id, author_id, username, title,
                       cover_url, duration, file_size, completed_at or datetime.now().isoformat())

    def get_task_logs(self, limit: int = 50, offset: int = 0) -> list:
        with self._cursor() as cursor:
            from core.utils.database.crud.log_dao import query_logs
            return query_logs(cursor, limit, offset)

    def count_task_logs(self) -> int:
        with self._cursor() as cursor:
            from core.utils.database.crud.log_dao import count_logs
            return count_logs(cursor)

    def cleanup_task_logs(self, days: int = 7) -> int:
        with self._cursor() as cursor:
            from core.utils.database.crud.log_dao import cleanup_old_logs
            return cleanup_old_logs(cursor, days)
```

- [ ] **Step 3: Commit**

```bash
git add core/utils/database/crud/log_dao.py core/utils/database/base.py
git commit -m "feat: 添加 task_log DAO 和 Database 代理方法"
```

---

## Task 3: 后端写入触发点

**Files:**
- Modify: `core/utils/socket_client.py:118-140`
- Modify: `core/service/task.py:149`

- [ ] **Step 1: 在 `socket_client.py` 添加触发**

在 `socket_client.py` 行 138（`emit_task_completed` 调用）之后，添加：

```python
            # 记录任务完成（非阻塞）
            try:
                from core.utils.database import get_database
                _db = get_database()
                _video_rec = _db.get_author_video(video_id)
                _author_id = _video_rec.author_id if _video_rec else ''
                _username = ''
                if _author_id:
                    _author = _db.get_author(_author_id)
                    _username = _author.source_author_id if _author else ''
                _db.log_task_completion(
                    video_id=video_id,
                    author_id=_author_id,
                    username=_username,
                    title=task.get('title', ''),
                    cover_url=_video_rec.cover_url if _video_rec else '',
                    duration=_video_rec.duration if _video_rec else 0,
                    file_size=task.get('total_size', 0),
                )
            except Exception as _le:
                logger.debug(f"[WS] 记录完成日志失败(非致命): {_le}")
```

- [ ] **Step 2: 在 `task.py` 添加触发**

在 `task.py` 行 149（`emit_task_completed` 调用）之后，添加：

```python
            # 记录任务完成（非阻塞）
            try:
                from core.utils.database import get_database
                _db = get_database()
                _video_rec = _db.get_author_video(local_task.video_id)
                _author_id = _video_rec.author_id if _video_rec else ''
                _username = ''
                if _author_id:
                    _author = _db.get_author(_author_id)
                    _username = _author.source_author_id if _author else ''
                _db.log_task_completion(
                    video_id=local_task.video_id,
                    author_id=_author_id,
                    username=_username,
                    title=local_task.title,
                    cover_url=_video_rec.cover_url if _video_rec else '',
                    duration=_video_rec.duration if _video_rec else 0,
                    file_size=local_task.total_size,
                )
            except Exception as _le:
                logger.debug(f"记录完成日志失败(非致命): {_le}")
```

- [ ] **Step 3: Commit**

```bash
git add core/utils/socket_client.py core/service/task.py
git commit -m "feat: 双触发点写入任务完成记录（WebSocket + HTTP 轮询）"
```

---

## Task 4: 后端 API 端点 + 清理调度

**Files:**
- Modify: `core/api/routers/task.py:172+`
- Modify: `core/api/app.py` (添加清理调度)

- [ ] **Step 1: 在 `task.py` 路由文件添加端点**

在 `task.py` 行 172（最后一个路由 `delete_task`）之后添加：

```python
@router.get("/completion-log")
async def get_completion_log(limit: int = 50, offset: int = 0):
    """获取任务完成记录"""
    if limit < 1:
        limit = 50
    if limit > 100:
        limit = 100
    if offset < 0:
        offset = 0
    
    db = get_database()
    items = db.get_task_logs(limit, offset)
    total = db.count_task_logs()
    
    return {"code": 0, "data": {"total": total, "items": items}}
```

确保文件顶部有 `get_database` 导入（检查现有导入，如无则添加）。

- [ ] **Step 2: 在 `app.py` 添加清理调度**

在 FastAPI app 的 lifespan 或 startup 事件中添加清理逻辑。搜索 `app.py` 中的 startup 事件注册位置，添加：

```python
# 启动时清理过期记录
try:
    db = get_database()
    deleted = db.cleanup_task_logs(7)
    if deleted > 0:
        logger.info(f"清理了 {deleted} 条过期任务记录")
except Exception as e:
    logger.warning(f"清理过期记录失败: {e}")
```

对于每小时清理，使用 `asyncio` 后台任务：

```python
import asyncio

async def _periodic_log_cleanup():
    """每小时清理过期任务记录"""
    while True:
        await asyncio.sleep(3600)  # 1 小时
        try:
            db = get_database()
            deleted = db.cleanup_task_logs(7)
            if deleted > 0:
                logger.info(f"定时清理了 {deleted} 条过期任务记录")
        except Exception as e:
            logger.warning(f"定时清理过期记录失败: {e}")

# 在 startup 事件中启动
@app.on_event("startup")
async def startup_event():
    # ... 现有逻辑 ...
    asyncio.create_task(_periodic_log_cleanup())
```

注意：如果 `app.py` 已有 startup 事件处理，在现有逻辑末尾追加 `asyncio.create_task` 调用。

- [ ] **Step 3: Commit**

```bash
git add core/api/routers/task.py core/api/app.py
git commit -m "feat: 添加 /api/task/completion-log 端点 + 定时清理"
```

---

## Task 5: 前端 State.logs 表模块

**Files:**
- Create: `static/js/api/state/tables/logs.js`
- Modify: `static/js/api/state/index.js:34,87`
- Modify: `static/index.html` (添加 script 标签)

- [ ] **Step 1: 创建 `logs.js`**

```javascript
// static/js/api/state/tables/logs.js
// 任务完成记录表

var _logs = [];
var _total = 0;

function _emit(event, data) {
  if (typeof State !== 'undefined' && State.emit) {
    State.emit(event, data);
  }
}

function all() { return _logs; }
function getTotal() { return _total; }

function setLogs(data) {
  _logs = data.items || [];
  _total = data.total || 0;
  _emit('logs:updated', { items: _logs, total: _total });
}

// 暴露到全局
window.State = window.State || {};
window.State.logs = {
  all: all,
  getTotal: getTotal,
  setLogs: setLogs
};
```

- [ ] **Step 2: 在 `index.html` 添加 script 标签**

在 `index.html` 中 `tasks.js` 的 script 标签之后添加：

```html
<script src="/static/js/api/state/tables/logs.js"></script>
```

- [ ] **Step 3: Commit**

```bash
git add static/js/api/state/tables/logs.js static/index.html
git commit -m "feat: 添加 State.logs 表模块"
```

---

## Task 6: 前端 API 调用 + 工具函数

**Files:**
- Modify: `static/js/api/task.js:30+`
- Modify: `static/js/utils/date.js:38+`

- [ ] **Step 1: 在 `task.js` 添加 `fetchCompletionLog`**

在 `task.js` 最后一个函数之后添加：

```javascript
// GET /api/task/completion-log - 获取任务完成记录
async function fetchCompletionLog(limit, offset) {
  limit = limit || 50;
  offset = offset || 0;
  try {
    var res = await fetch('/api/task/completion-log?limit=' + limit + '&offset=' + offset);
    var data = await res.json();
    if (data.code === 0) {
      State.logs.setLogs(data.data);
      if (typeof renderHistoryList === 'function') {
        renderHistoryList();
      }
    }
  } catch (e) {
    console.warn('获取下载记录失败:', e);
  }
}
```

- [ ] **Step 2: 在 `date.js` 添加 `formatRelativeTime`**

在 `date.js` 行 38（`formatDate` 函数结束）之后添加：

```javascript
function formatRelativeTime(isoTime) {
  if (!isoTime) return '';
  var now = Date.now();
  var then = new Date(isoTime).getTime();
  if (isNaN(then)) return '';
  var diff = now - then;
  var seconds = Math.floor(diff / 1000);
  if (seconds < 60) return '刚刚';
  var minutes = Math.floor(seconds / 60);
  if (minutes < 60) return minutes + ' 分钟前';
  var hours = Math.floor(minutes / 60);
  if (hours < 24) return hours + ' 小时前';
  var days = Math.floor(hours / 24);
  if (days < 7) return days + ' 天前';
  return formatDate(isoTime);
}
```

- [ ] **Step 3: Commit**

```bash
git add static/js/api/task.js static/js/utils/date.js
git commit -m "feat: 添加 fetchCompletionLog API + formatRelativeTime 工具函数"
```

---

## Task 7: 前端 SSE 集成 + Toast 批量合并

**Files:**
- Modify: `static/js/datahandle/authorDetail.js:8-89,104-111`
- Modify: `static/js/utils/toast.js` (添加批量合并)

- [ ] **Step 1: 在 SSE `onopen` 中懒加载历史记录**

在 `authorDetail.js` 的 `es.onopen` 函数中，`refreshActiveTasks()` 调用之后添加：

```javascript
  // 懒加载历史记录
  if (State.logs && State.logs.getTotal() === 0) {
    if (typeof fetchCompletionLog === 'function') {
      fetchCompletionLog();
    }
  }
```

- [ ] **Step 2: 在 `task_completed` SSE 事件中刷新历史 + Toast 合并**

在 `authorDetail.js` 的 `handleSSETaskCompleted` 函数末尾（return 之前）添加：

```javascript
  // 刷新历史记录
  if (State.logs && State.logs.getTotal() > 0) {
    if (typeof fetchCompletionLog === 'function') {
      fetchCompletionLog(8);
    }
  }
  
  // Toast 批量合并
  var _username = State.videos.getAuthorByVideoId(data.video_id);
  var _video = _username ? State.videos.get(_username, data.video_id) : null;
  var _title = _video ? _video.title : '';
  if (typeof showTaskCompletionToast === 'function') {
    showTaskCompletionToast(_title);
  }
```

- [ ] **Step 3: 在 `toast.js` 添加 Toast 批量合并**

在 `static/js/utils/toast.js` 的 `showToast` 函数之后添加：

```javascript
// 任务完成 Toast 批量合并（300ms 防抖）
var _completionToastTimer = null;
var _completionToastCount = 0;

function showTaskCompletionToast(videoTitle) {
  _completionToastCount++;
  
  if (_completionToastTimer) {
    clearTimeout(_completionToastTimer);
  }
  
  _completionToastTimer = setTimeout(function() {
    if (_completionToastCount === 1) {
      showToast({ type: 'success', title: '下载完成', message: videoTitle });
    } else {
      showToast({ type: 'success', title: '下载完成', message: _completionToastCount + ' 个视频下载完成' });
    }
    _completionToastCount = 0;
    _completionToastTimer = null;
  }, 300);
}
```

- [ ] **Step 4: Commit**

```bash
git add static/js/datahandle/authorDetail.js static/js/utils/toast.js
git commit -m "feat: SSE 集成历史记录刷新 + Toast 批量合并"
```

---

## Task 8: 前端历史面板 UI

**Files:**
- Create: `static/js/component/historyPanel.js`
- Modify: `static/index.html:87+` (添加标签页 HTML)
- Modify: `static/css/styles.css` (添加样式)

- [ ] **Step 1: 创建 `historyPanel.js`**

```javascript
// static/js/component/historyPanel.js
// 历史面板组件

var _historyTabActive = false;

function switchDrawerTab(tab) {
  var statusContent = document.getElementById('drawerStatusContent');
  var historyContent = document.getElementById('drawerHistoryContent');
  var tabStatus = document.getElementById('drawerTabStatus');
  var tabHistory = document.getElementById('drawerTabHistory');
  
  if (!statusContent || !historyContent) return;
  
  if (tab === 'history') {
    _historyTabActive = true;
    statusContent.style.display = 'none';
    historyContent.style.display = 'block';
    if (tabStatus) tabStatus.classList.remove('active');
    if (tabHistory) tabHistory.classList.add('active');
    // 切换到历史时刷新
    if (typeof fetchCompletionLog === 'function') {
      fetchCompletionLog(8);
    }
  } else {
    _historyTabActive = false;
    statusContent.style.display = 'block';
    historyContent.style.display = 'none';
    if (tabStatus) tabStatus.classList.add('active');
    if (tabHistory) tabHistory.classList.remove('active');
  }
}

function renderHistoryList() {
  var container = document.getElementById('historyList');
  if (!container) return;
  
  var items = (State.logs && State.logs.all()) || [];
  
  if (items.length === 0) {
    container.innerHTML = '<div class="history-empty">暂无下载记录</div>';
    return;
  }
  
  container.innerHTML = items.map(function(item) {
    var authorName = escapeHtml(item.author_name) || '未知作者';
    var title = escapeHtml(item.title) || '';
    var time = (typeof formatRelativeTime === 'function') ? formatRelativeTime(item.completed_at) : '';
    var size = (typeof formatFileSize === 'function') ? formatFileSize(item.file_size) : '';
    var coverUrl = item.cover_url || '';
    var username = item.username || '';
    var clickHandler = username 
      ? 'loadAuthorDetail(\'' + username.replace(/'/g, "\\'") + '\')' 
      : 'showToast({type:\'warning\',title:\'提示\',message:\'作者已移除\'})';
    
    return '<div class="history-item" onclick="' + clickHandler + '">' +
      '<img class="history-cover" src="' + coverUrl + '" alt="' + title + '" onerror="this.style.display=\'none\'">' +
      '<div class="history-info">' +
        '<div class="history-title">' + title + '</div>' +
        '<div class="history-meta">' +
          '<span class="history-author">' + authorName + '</span>' +
          '<span class="history-sep">·</span>' +
          '<span class="history-time">' + time + '</span>' +
          '<span class="history-sep">·</span>' +
          '<span class="history-size">' + size + '</span>' +
        '</div>' +
      '</div>' +
    '</div>';
  }).join('');
}
```

- [ ] **Step 2: 在 `index.html` 状态抽屉中添加标签页**

在 `index.html` 的 `status-drawer-body` 内，`status-detail` div 之后添加标签页结构：

```html
<!-- 抽屉标签页 -->
<div class="drawer-tabs">
  <button class="drawer-tab active" id="drawerTabStatus" onclick="switchDrawerTab('status')">状态</button>
  <button class="drawer-tab" id="drawerTabHistory" onclick="switchDrawerTab('history')">历史</button>
</div>
<!-- 状态内容（现有 status-detail）保持不变，添加 id -->
<!-- 在现有 status-detail 的 div 上添加 id="drawerStatusContent" -->
<!-- 历史内容 -->
<div class="drawer-tab-content" id="drawerHistoryContent" style="display:none">
  <div class="history-panel">
    <div id="historyList">
      <div class="history-empty">暂无下载记录</div>
    </div>
  </div>
</div>
```

同时给现有的 `status-detail` div 添加 `id="drawerStatusContent"`。

在 `index.html` 的 script 标签区域添加：
```html
<script src="/static/js/component/historyPanel.js"></script>
```

- [ ] **Step 3: 在 `styles.css` 添加样式**

```css
/* 抽屉标签页 */
.drawer-tabs {
  display: flex;
  gap: 0;
  border-bottom: 1px solid var(--border-color, rgba(0,0,0,0.08));
  margin-bottom: 8px;
}

.drawer-tab {
  flex: 1;
  padding: 6px 12px;
  border: none;
  background: transparent;
  color: var(--text-tertiary);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  border-bottom: 2px solid transparent;
  transition: all 0.15s ease;
}

.drawer-tab:hover {
  color: var(--text-secondary);
}

.drawer-tab.active {
  color: var(--text-primary);
  border-bottom-color: var(--primary, #4f46e5);
}

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

- [ ] **Step 4: Commit**

```bash
git add static/js/component/historyPanel.js static/index.html static/css/styles.css
git commit -m "feat: 添加历史面板 UI（标签页 + 列表 + 样式）"
```

---

## Task 9: 端到端验证

**Files:** 无新文件

- [ ] **Step 1: 启动应用，验证后端**

1. 启动 Go 服务 + Python 后端
2. 检查 `task_log` 表是否创建成功
3. 下载一个视频，检查 `task_log` 表中是否出现记录
4. 访问 `GET /api/task/completion-log`，确认返回数据格式正确

- [ ] **Step 2: 验证前端**

1. 打开浏览器，确认状态抽屉显示"状态"和"历史"标签
2. 点击"历史"标签，确认切换到历史面板
3. 下载视频完成后，确认历史列表更新
4. 确认 Toast 显示"下载完成"（单个）或"N 个视频下载完成"（批量）
5. 点击历史记录项，确认跳转到对应作者页面

- [ ] **Step 3: 验证边界情况**

1. 作者删除后，历史记录仍显示（作者名为空）
2. 无记录时显示"暂无下载记录"
3. 网络异常时历史面板不崩溃

- [ ] **Step 4: Commit（如有修复）**

```bash
git add -A
git commit -m "fix: 端到端验证修复"
```
