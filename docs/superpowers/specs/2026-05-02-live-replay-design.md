# 直播回放功能设计

## 背景

当前下载器仅支持短视频下载。Go 后端的直播回放接口（`/api/channels/live/replay/list`）和 Python 客户端方法（`WechatVideoAPIClient.get_author_replays()`）已实现但未集成到主业务流程。本次变更将直播回放功能完整接入，使短视频和直播回放并重。

## 决策记录

| 问题 | 决策 |
|------|------|
| 用户需求定位 | 短视频和直播回放两者并重 |
| 搜索添加作者时 | 同时拉取短视频+直播回放 |
| 视频列表展示 | 分 Tab 显示（短视频 / 直播回放） |
| 选中下载 | 统一操作，跨 Tab 选择后统一下载 |
| 下载全部待下载 | 统一按钮，弹窗让用户选类型（全部/仅短视频/仅回放） |
| 一键监控 | 同时监控短视频+直播回放 |
| 作者卡片统计 | 分开显示（5 短视频 · 3 回放 · 8 已下载） |
| 数据层方案 | 方案 A：video_type 字段，同一张表存储 |

## 数据库变更

### author_videos 表

新增字段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| video_type | TEXT | 'short_video' | "short_video" 或 "live_replay" |

### download_tasks 表

新增字段：

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| video_type | TEXT | 'short_video' | 从关联的 author_video 继承类型 |

### 数据模型

`AuthorVideo` 和 `DownloadTask` 数据类各新增 `video_type: str = "short_video"` 属性。

### 迁移策略

应用启动时检查 `video_type` 字段是否存在，不存在则执行 `ALTER TABLE`。新增字段 `DEFAULT 'short_video'`，SQLite 自动为已有行填充默认值，无需额外回填脚本。

## 后端变更

### VideoService

`add_author_latest_videos()` 内部变更：
- 原来只调用 `_fetch_author_videos_from_backend(username)` 拉取短视频
- 现在同时调用 `_fetch_author_replays_from_backend(username)` 拉取直播回放
- 两个列表合并后统一去重入库，各自标记 `video_type`

新增方法 `_fetch_author_replays_from_backend(username)`：
- 调用已有的 `WechatVideoAPIClient.get_author_replays()`
- 结构与 `_fetch_author_videos_from_backend()` 一致
- 解析回放对象时设置 `video_type="live_replay"`

### API 路由变更

不新增路由，扩展现有路由参数和返回值：

| 路由 | 变更 | 说明 |
|------|------|------|
| GET /api/video/list | 新增 query 参数 `video_type` | 可选 "short_video"/"live_replay"，不传则返回全部 |
| GET /api/video/stats | 返回值增加按类型统计 | 新增 `short_video_count` / `replay_count` 字段 |
| POST /api/task/create | 自动继承 video_type | 从 author_video 读取 video_type 写入 task |
| POST /api/task/download-all | 新增 body 参数 `video_type` | 可选 "all"/"short_video"/"live_replay"，默认 "all" |
| GET /api/author/list | 返回值增加按类型统计 | 每个作者增加 `short_video_count` / `replay_count` |

### MonitorService

无需改动。`_monitor_loop()` 调用 `VideoService.add_author_latest_videos()`，该方法内部已同时拉取两种类型。

### SSE 事件

`task_progress` 事件新增 `video_type` 字段，前端可根据类型在不同 Tab 下显示进度。

## 前端变更

### 首页 — 作者卡片

统计数分开显示：
- 原来：`12 个视频 · 8 已下载`
- 变更后：`5 短视频 · 3 回放 · 8 已下载`
- 使用不同颜色标签区分：短视频蓝色，回放橙色

### 作者详情页 — Tab 结构

采用两级 Tab 结构：
- **一级 Tab**：短视频 | 直播回放（切换视频类型）
- **二级 Tab**：全部 | 正在下载 | 已下载 | 未下载（筛选下载状态）

作者头部统计也分开显示：`5 短视频 · 3 回放 · 6 已下载`

### 下载全部待下载 — 弹窗选择

点击"下载全部待下载"按钮后弹出选择弹窗，三个选项：
1. 全部下载（短视频 + 直播回放，N 个）
2. 仅短视频（M 个待下载）
3. 仅直播回放（K 个待下载）

弹窗显示各类待下载数量，用户选择后点击"开始下载"。

### 选中下载 — 跨 Tab 选择

选择栏显示分类统计：
- `已选 4 个` + `2 短视频` + `2 回放` 标签
- 用户可在不同 Tab 下选择视频，统一点下载

### 搜索页 — 添加作者

搜索结果卡片增加提示：`添加后将同步短视频 + 直播回放`

### 前端文件改动清单

| 文件 | 改动 |
|------|------|
| authorGridRender.js | 卡片统计数分开显示 |
| videoListRender.js | 一级 Tab（短视频/回放）+ 二级 Tab 筛选 |
| videoSelect.js | 选择栏增加分类统计 |
| authorDetail.js | 下载全部弹窗 + 统计数更新 |
| videoOps.js | 下载请求带 video_type 参数 |
| api/video.js | API 调用增加 video_type 参数 |
| api/author.js | 作者列表返回类型统计 |
| state/tables/videos.js | 状态表增加 video_type 字段 |
| state/tables/authors.js | 作者状态增加类型统计 |
| dialog.js | 新增下载范围选择弹窗 |
| index.html | 标题改为"视频号控制台"，Tab 结构调整 |

## 不需要改动的部分

- WechatVideoAPIClient（`get_author_replays()` 已实现）
- Go 后端（直播回放接口已就绪）
- 设置页
- 导入功能（CSV/Excel/腾讯文档）
- 日志面板
- 播放功能
- 状态栏

## 视频时长获取策略

### 问题

微信接口返回两个时长字段：
- `media[].videoPlayLen`：对短视频准确，对直播回放不准确（只返回几秒而非几小时）
- `media[].spec[0].durationMs`：对短视频和直播回放都准确

### 实测数据（来自 Bug修复报告_2026-04-27.md）

| 字段 | 短视频 | 直播回放 |
|------|--------|----------|
| videoPlayLen | 180000ms = 3分钟 ✓ | 6552ms = 6.5秒 ❌ |
| spec[0].durationMs | 180000ms = 3分钟 ✓ | 6553041ms = 1.82小时 ✓ |
| fileSize | 17MB ✓ | 3986MB ✓ |

### 策略

统一使用 `spec[0].durationMs` 获取时长，不再使用 `videoPlayLen`。

优先级：
1. `spec[0].durationMs`（最准确，短视频和直播回放都可靠）
2. `videoPlayLen`（仅当 spec 列表为空时作为 fallback）
3. 0（两个字段都无值时）

### 需要修改的文件

| 文件 | 行号 | 当前 | 改为 |
|------|------|------|------|
| core/service/video.py | 466, 506 | `media.get("videoPlayLen", 0)` → `// 1000` | 优先从 `spec[0].durationMs` 获取 |
| core/service/search.py | 455, 490 | `media.get("videoPlayLen", 0)` → `// 1000` | 优先从 `spec[0].durationMs` 获取 |

### 解析逻辑伪代码

```python
# 获取时长：优先 spec[0].durationMs，fallback videoPlayLen
duration_ms = 0
spec_list = media.get("spec", [])
if spec_list:
    duration_ms = spec_list[0].get("durationMs", 0)
if not duration_ms:
    duration_ms = media.get("videoPlayLen", 0)
duration = duration_ms // 1000 if duration_ms else 0
```

## 数据流

### 搜索添加作者

1. 前端 → POST /api/search/add → SearchService
2. → VideoService.add_author_latest_videos()
3. → 内部同时调用 _fetch_videos(video_type="short_video") + _fetch_replays(video_type="live_replay")
4. → 去重入库 author_videos（带 video_type）
5. → SSE 推送 author_stats 更新

### 浏览视频列表

1. 前端切换 Tab → GET /api/video/list?author_id=x&video_type=short_video
2. → VideoDAO 查询 WHERE video_type = ?
3. → 返回对应类型视频

### 选中下载

1. 前端选中视频 → POST /api/task/create（video_id 列表）
2. → TaskService 从 author_video 读取 video_type → 写入 download_task
3. → Go 后端下载 → WS 进度推送 → SSE task_progress（带 video_type）

### 下载全部待下载

1. 前端弹窗选择 → POST /api/task/download-all（video_type=all|short_video|live_replay）
2. → TaskService 按类型筛选待下载视频 → 批量创建任务

### 一键监控

1. 前端 → POST /api/monitor/start → MonitorService._monitor_loop()
2. → 每轮同步所有作者 → VideoService 内部同时拉取短视频+回放
3. → 收集未下载视频（两种类型）→ 创建下载任务
