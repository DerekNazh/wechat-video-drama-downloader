# 直播回放功能集成 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将直播回放功能完整集成到下载器，使短视频和直播回放并重，前端分 Tab 展示，后端统一管理。

**Architecture:** 在 author_videos 表加 video_type 字段区分短视频/直播回放，VideoService 同时拉取两种类型，前端一级 Tab 切换类型、二级 Tab 筛选状态，下载全部弹窗让用户选择范围。

**Tech Stack:** Python FastAPI + SQLite + vanilla JS + pywebview

---

## File Structure

### 后端修改
- `core/utils/database/base.py` — 新增 video_type 字段迁移
- `core/utils/database/crud/models.py` — AuthorVideo/DownloadTask 加 video_type 属性
- `core/utils/database/crud/video_dao.py` — CRUD 支持 video_type
- `core/utils/database/crud/task_dao.py` — CRUD 支持 video_type
- `core/utils/database/base.py` (Database 类) — 新增按类型统计方法
- `core/service/video.py` — 同时拉取短视频+回放，修复时长获取
- `core/service/search.py` — 修复时长获取
- `core/api/routers/video.py` — video_type 查询参数 + 类型统计
- `core/api/routers/task.py` — download-all 支持 video_type 筛选
- `core/api/routers/author.py` — 返回按类型统计

### 前端修改
- `static/index.html` — Tab 结构调整 + 标题改"视频号控制台"
- `static/js/component/authorGridRender.js` — 卡片分开统计
- `static/js/component/videoListRender.js` — 一级 Tab + 二级 Tab
- `static/js/component/videoSelect.js` — 选择栏分类统计
- `static/js/datahandle/videoOps.js` — 下载全部弹窗 + 下载请求带 video_type
- `static/js/datahandle/authorDetail.js` — 统计数更新
- `static/js/api/video.js` — API 调用增加 video_type 参数
- `static/js/component/dialog.js` — 新增下载范围选择弹窗

---

### Task 1: 数据库迁移 — video_type 字段

**Files:**
- Modify: `core/utils/database/base.py:78-106`
- Modify: `core/utils/database/crud/models.py:30-48`

- [ ] **Step 1: 在 models.py 中给 AuthorVideo 加 video_type 字段**

在 `AuthorVideo` dataclass 中，`downloaded_at` 之前加：

```python
video_type: str = "short_video"        # "short_video" 或 "live_replay"
```

在 `DownloadTask` dataclass 中，`completed_at` 之前加：

```python
video_type: str = "short_video"        # 从关联的 author_video 继承
```

- [ ] **Step 2: 在 base.py _init_db 中加 ALTER TABLE 迁移**

在 `author_videos` 表的 `downloaded_at` 迁移之后加：

```python
# 升级：添加 video_type 字段
try:
    cursor.execute("ALTER TABLE author_videos ADD COLUMN video_type TEXT DEFAULT 'short_video'")
except sqlite3.OperationalError:
    pass
```

在 `download_tasks` 表的索引之后加：

```python
# 升级：添加 video_type 字段
try:
    cursor.execute("ALTER TABLE download_tasks ADD COLUMN video_type TEXT DEFAULT 'short_video'")
except sqlite3.OperationalError:
    pass
```

- [ ] **Step 3: 验证迁移**

Run: `cd "f:/setup_temp/剪辑合成拆散/监控/总下载器版本" && .venv/Scripts/python -c "from core.utils.database import db; print('OK')"`

- [ ] **Step 4: Commit**

```bash
git add core/utils/database/base.py core/utils/database/crud/models.py
git commit -m "feat: add video_type field to author_videos and download_tasks tables"
```

---

### Task 2: VideoDAO/TaskDAO 支持 video_type

**Files:**
- Modify: `core/utils/database/crud/video_dao.py`
- Modify: `core/utils/database/crud/task_dao.py`
- Modify: `core/utils/database/base.py` (Database 类)

- [ ] **Step 1: 修改 video_dao.py 的 create 方法，写入 video_type**

在 INSERT 语句中加入 `video_type` 列，在 VALUES 中加入 `?`，在参数列表中加入 `video.video_type`。

在 `list_by_author` 方法的 SELECT 中加入 `video_type`，在构建 AuthorVideo 时从 row 中读取 `video_type`。

在 `get_by_id` 方法同样处理。

- [ ] **Step 2: 修改 task_dao.py 的 create 方法，写入 video_type**

在 INSERT 语句中加入 `video_type` 列，在 VALUES 中加入 `?`，在参数列表中加入 `task.video_type`。

在 `get_by_id` 和 `list_all` 方法的 SELECT 中加入 `video_type`，构建 DownloadTask 时从 row 中读取。

- [ ] **Step 3: 在 Database 类中新增按类型统计方法**

在 `base.py` 的 Database 类中，视频操作区域加：

```python
def get_author_video_type_stats(self, author_id: str) -> dict:
    """按 video_type 统计作者视频"""
    with self._cursor() as cursor:
        return self._video_dao.get_type_stats(cursor, author_id)
```

在 `video_dao.py` 中实现 `get_type_stats`：

```python
def get_type_stats(self, cursor, author_id: str) -> dict:
    cursor.execute(
        "SELECT video_type, COUNT(*) as cnt, SUM(CASE WHEN is_downloaded=1 THEN 1 ELSE 0 END) as dl "
        "FROM author_videos WHERE author_id=? GROUP BY video_type",
        (author_id,)
    )
    result = {"short_video_count": 0, "replay_count": 0,
              "short_video_downloaded": 0, "replay_downloaded": 0}
    for row in cursor.fetchall():
        vtype, cnt, dl = row
        if vtype == "live_replay":
            result["replay_count"] = cnt
            result["replay_downloaded"] = dl
        else:
            result["short_video_count"] = cnt
            result["short_video_downloaded"] = dl
    return result
```

- [ ] **Step 4: 验证**

Run: `cd "f:/setup_temp/剪辑合成拆散/监控/总下载器版本" && .venv/Scripts/python -c "from core.utils.database import db; print(db.get_author_video_type_stats('test'))"`

- [ ] **Step 5: Commit**

```bash
git add core/utils/database/crud/video_dao.py core/utils/database/crud/task_dao.py core/utils/database/base.py
git commit -m "feat: DAO support for video_type field and type stats"
```

---

### Task 3: 修复时长获取 — spec[0].durationMs 优先

**Files:**
- Modify: `core/service/video.py:460-508`
- Modify: `core/service/search.py:449-492`

- [ ] **Step 1: 修改 video.py _parse_video_object 的时长获取**

将第 466 行 `video_play_len = media.get("videoPlayLen", 0)` 和第 506 行的 duration 计算替换为：

```python
# 获取时长：优先 spec[0].durationMs，fallback videoPlayLen
duration_ms = 0
spec_list = media.get("spec", [])
if spec_list:
    duration_ms = spec_list[0].get("durationMs", 0)
if not duration_ms:
    duration_ms = media.get("videoPlayLen", 0)
```

返回字典中 `"duration"` 改为：

```python
"duration": duration_ms // 1000 if duration_ms else 0,
```

删除 `video_play_len` 变量。

- [ ] **Step 2: 修改 search.py _parse_video 的时长获取**

同样替换第 455 行和第 490 行，逻辑与 Step 1 完全一致。

- [ ] **Step 3: 验证**

Run: `cd "f:/setup_temp/剪辑合成拆散/监控/总下载器版本" && .venv/Scripts/python -c "from core.service.video import VideoService; print('OK')"`

- [ ] **Step 4: Commit**

```bash
git add core/service/video.py core/service/search.py
git commit -m "fix: use spec[0].durationMs for duration (accurate for live replays)"
```

---

### Task 4: VideoService 同时拉取短视频+直播回放

**Files:**
- Modify: `core/service/video.py:77-187`

- [ ] **Step 1: 新增 _fetch_author_replays_from_backend 方法**

在 `_fetch_author_videos_from_backend` 方法之后加：

```python
def _fetch_author_replays_from_backend(self, source_author_id: str) -> list[dict]:
    """从后端获取作者直播回放列表"""
    if not source_author_id:
        return []

    replays = []
    next_marker = None

    while True:
        try:
            params = {"username": source_author_id, "page_size": 20}
            if next_marker:
                params["next_marker"] = next_marker

            resp = requests.get(
                f"{self.api_base_url}/api/channels/live/replay/list",
                params=params,
                timeout=30
            )
            data = resp.json()

            if data.get("code") != 0:
                logger.warning(f"[_fetch_author_replays] API 返回错误: {data.get('msg')}")
                break

            inner_data = data.get("data", {}).get("data", {})
            object_list = inner_data.get("object", [])

            for obj in object_list:
                video_dict = self._parse_video_object(obj)
                if video_dict:
                    video_dict["video_type"] = "live_replay"
                    replays.append(video_dict)

            next_marker = inner_data.get("lastBuff")
            if not next_marker:
                break

        except Exception as e:
            logger.error(f"[_fetch_author_replays] 请求失败: {e}")
            break

    logger.info(f"[_fetch_author_replays] 获取 {len(replays)} 个直播回放")
    return replays
```

- [ ] **Step 2: 修改 add_author_latest_videos 同时拉取两种类型**

将第 99-104 行替换为：

```python
# 从后端获取视频列表（短视频+直播回放）
try:
    videos_data = self._fetch_author_videos_from_backend(author.source_author_id)
    replays_data = self._fetch_author_replays_from_backend(author.source_author_id)
    # 短视频默认标记类型
    for v in videos_data:
        v.setdefault("video_type", "short_video")
    all_data = videos_data + replays_data
except Exception as e:
    logger.error(f"[add_author_latest_videos] 获取后端视频失败: {e}")
    return result

videos_data = all_data
```

- [ ] **Step 3: 在入库时写入 video_type**

在第 133-149 行创建 AuthorVideo 时加：

```python
video_type=video_dict.get("video_type", "short_video"),
```

- [ ] **Step 4: 验证**

Run: `cd "f:/setup_temp/剪辑合成拆散/监控/总下载器版本" && .venv/Scripts/python -c "from core.service.video import VideoService; print('OK')"`

- [ ] **Step 5: Commit**

```bash
git add core/service/video.py
git commit -m "feat: VideoService fetches both short videos and live replays"
```

---

### Task 5: 后端 API 路由扩展

**Files:**
- Modify: `core/api/routers/video.py`
- Modify: `core/api/routers/task.py`
- Modify: `core/api/routers/author.py`

- [ ] **Step 1: video.py — list 接口加 video_type 参数，stats 加类型统计**

在 `GET /api/video/author/{author_id}` 路由中加 `video_type: Optional[str] = None` 查询参数，查询时按 video_type 过滤。

在返回作者统计时，调用 `db.get_author_video_type_stats()` 返回 `short_video_count` / `replay_count`。

- [ ] **Step 2: task.py — create 时继承 video_type，download-all 加 video_type 筛选**

在 `create_download_task` 创建 DownloadTask 时，从关联的 AuthorVideo 读取 `video_type` 写入 task。

在 `batch-create` 或 `download-all` 路由中加 `video_type` 参数，筛选待下载视频时按类型过滤。

- [ ] **Step 3: author.py — list 返回按类型统计**

在作者列表返回中，每个作者加 `short_video_count` / `replay_count` 字段。

- [ ] **Step 4: 验证**

Run: `cd "f:/setup_temp/剪辑合成拆散/监控/总下载器版本" && .venv/Scripts/python -c "from core.api.app import app; print('OK')"`

- [ ] **Step 5: Commit**

```bash
git add core/api/routers/video.py core/api/routers/task.py core/api/routers/author.py
git commit -m "feat: API routes support video_type parameter and type stats"
```

---

### Task 6: 前端 — 作者卡片分开统计

**Files:**
- Modify: `static/js/component/authorGridRender.js:170-250`

- [ ] **Step 1: 修改 renderAuthorCardView 的统计显示**

将 `.author-stats` 区域从 `总数/已下载/待下载` 改为显示 `短视频数/回放数/已下载`。

在 `catMap` 中读取 `short_video_count` / `replay_count` 字段（后端新增），替换原来的 `total`。

卡片统计 HTML 改为：

```html
<div class="author-stats">
  <div class="stat-item short-video">
    <div class="value">${shortVideoCount}</div>
    <div class="label">短视频</div>
  </div>
  <div class="stat-item replay">
    <div class="value">${replayCount}</div>
    <div class="label">回放</div>
  </div>
  <div class="stat-item downloaded">
    <div class="value">${downloaded}</div>
    <div class="label">已下载</div>
  </div>
</div>
```

- [ ] **Step 2: 同步修改 renderAuthorListView**

列表视图的统计列也改为 `短视频/回放/已下载`。

- [ ] **Step 3: Commit**

```bash
git add static/js/component/authorGridRender.js
git commit -m "feat: author card shows short video and replay counts separately"
```

---

### Task 7: 前端 — 视频列表一级 Tab + 二级 Tab

**Files:**
- Modify: `static/index.html:137-241`
- Modify: `static/js/component/videoListRender.js`

- [ ] **Step 1: 修改 index.html 作者详情页 Tab 结构**

在 `pageAuthor` 的 `author-header` 之后，`video-toolbar` 之前加一级 Tab：

```html
<div class="video-type-tabs">
  <button class="video-type-tab active" data-type="short_video" onclick="switchVideoType('short_video')">短视频</button>
  <button class="video-type-tab" data-type="live_replay" onclick="switchVideoType('live_replay')">直播回放</button>
</div>
```

修改标题 `视频号<em>短视频控制台</em>` 为 `视频号<em>控制台</em>`。

- [ ] **Step 2: 修改 videoListRender.js 支持按类型过滤**

新增全局变量 `_currentVideoType = 'short_video'`。

新增 `switchVideoType(type)` 函数：切换一级 Tab，重新从后端加载对应类型的视频列表，重新渲染。

修改 `renderVideoList` 和 `getFilteredVideos`：在过滤逻辑中加 `video_type` 过滤条件。

- [ ] **Step 3: 修改作者头部统计**

在 `author-stats-row` 中改为：

```html
<span class="stat"><strong id="authorShortVideo">0</strong> 短视频</span>
<span class="stat"><strong id="authorReplay">0</strong> 回放</span>
<span class="stat"><strong id="authorDownloaded">0</strong> 已下载</span>
```

- [ ] **Step 4: Commit**

```bash
git add static/index.html static/js/component/videoListRender.js
git commit -m "feat: video list with type tabs (short video / live replay)"
```

---

### Task 8: 前端 — 下载全部弹窗 + 选择栏分类统计

**Files:**
- Modify: `static/js/datahandle/videoOps.js:153-230`
- Modify: `static/js/component/videoSelect.js`
- Modify: `static/js/component/dialog.js`

- [ ] **Step 1: 修改 downloadAllPending 弹窗，增加类型选择**

将原来的确认弹窗改为三选项弹窗：
- 全部下载（短视频+直播回放）
- 仅短视频
- 仅直播回放

每个选项显示对应待下载数量。用户选择后按类型筛选 pendingIds 传给 `confirmDownloadAllPending`。

- [ ] **Step 2: 在 dialog.js 中新增 showDownloadRangeDialog 函数**

```javascript
function showDownloadRangeDialog(options, onConfirm) {
  // options: { shortVideoPending: 5, replayPending: 3, nickname: "xxx" }
  // 三个选项卡片 + 取消/开始下载按钮
}
```

- [ ] **Step 3: 修改 videoSelect.js 选择栏显示分类统计**

在 `updateSelectionBar` 中，统计已选视频中短视频和回放的数量，显示 `已选 4 个 (2 短视频 + 2 回放)`。

- [ ] **Step 4: Commit**

```bash
git add static/js/datahandle/videoOps.js static/js/component/videoSelect.js static/js/component/dialog.js
git commit -m "feat: download range dialog and selection bar type stats"
```

---

### Task 9: 前端 — API 调用 + 状态同步

**Files:**
- Modify: `static/js/api/video.js`
- Modify: `static/js/datahandle/authorDetail.js`

- [ ] **Step 1: 修改 video.js API 调用加 video_type 参数**

`getAuthorVideos(authorId)` 改为 `getAuthorVideos(authorId, videoType=None)`，有 videoType 时加查询参数。

- [ ] **Step 2: 修改 authorDetail.js 统计数更新**

`updateAuthorStats` 中从后端返回的类型统计数据更新 `authorShortVideo` / `authorReplay` / `authorDownloaded`。

`loadAuthorDetail` 中加载视频时传当前 `_currentVideoType`。

- [ ] **Step 3: Commit**

```bash
git add static/js/api/video.js static/js/datahandle/authorDetail.js
git commit -m "feat: frontend API and state sync for video_type"
```

---

### Task 10: 搜索页提示 + 最终验证

**Files:**
- Modify: `static/js/component/search.js`

- [ ] **Step 1: 搜索结果卡片加提示**

在搜索结果卡片中加提示文字：`添加后将同步短视频 + 直播回放`。

- [ ] **Step 2: 端到端验证**

启动应用，验证：
1. 搜索添加作者 → 同时拉取短视频+回放
2. 作者卡片显示分开统计
3. 详情页一级 Tab 切换短视频/回放
4. 下载全部弹窗显示类型选择
5. 选中下载显示分类统计
6. 一键监控同时监控两种类型

- [ ] **Step 3: Commit**

```bash
git add static/js/component/search.js
git commit -m "feat: search page hint for short video + live replay sync"
```
