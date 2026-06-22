# 前端 API 对接方案（精简版）

## Context

前端调用 19 个 API 端点，后端有 14 个已实现的 Set B 接口（URL 和格式不同）。
目标：**尽量改前端适配后端已有接口，后端只新增 1 个端点**，砍掉 poll 大轮询，改为按需加载。

## 核心思路

```
页面加载 → 调 GET /api/video/all 拉全量数据 → 前端做字段映射存 State
    ↓
服务状态 → 独立轻量轮询（10秒），只调 GET /api/service/status
    ↓
用户操作 → 调对应后端接口 → 成功后按需刷新变化的数据
```

## 后端改动（只加 1 个端点）

### task.py 新增 POST /api/task/batch-create

- 请求体: `{"video_ids": ["id1", "id2", ...]}`
- 内部循环调 `TaskService.create_download_task(video_id)`
- 响应: `{"code": 0, "data": {"count": 3}, "msg": ""}`

## 前端改动

### 1. app.js — 去掉 pollOnce，改按需加载

**去掉**:
- `pollOnce()` 的 5 秒循环
- 对 `/api/poll` 的调用

**改为**:
- 页面加载调 `GET /api/video/all` 一次，前端做字段映射
- 服务状态独立轮询 `GET /api/service/status`（10秒）
- 进度轮询保留，改调 `GET /api/task/list`

### 2. 前端字段映射（在 datahandle 层做）

`/api/video/all` 返回:
```json
{
  "code": 0,
  "data": [
    {
      "author": {"id", "source_author_id", "name", "tag", "bio", "avatar_url", ...},
      "videos": [{"video_id", "title", "is_downloaded", "file_size", ...}]
    }
  ]
}
```

前端映射:
- `author.source_author_id` → `username`
- `author.name` → `nickname`
- `author.avatar_url` → `head_url`
- `author.tag` → `profession`
- `author.bio` → `signature`
- `video.video_id` → `id`
- `video.is_downloaded == 1` → `downloaded: true`

### 3. 前端 URL 改动表

| 前端原来调 | 改成调 | 改动说明 |
|---|---|---|
| `GET /api/authors` | `GET /api/video/all` | 前端从 data[] 提取 author 做映射 |
| `GET /api/catalog` | `GET /api/video/all` | 前端自己算 total/downloaded/pending |
| `GET /api/author-videos` | `GET /api/video/all` | 前端组装 {authors: {username: {videos: {...}}}} |
| `POST /api/authors/add` | `POST /api/search/author/add` | 请求体 {keyword: nickname, pages: 1} |
| `POST /api/authors/delete` | `DELETE /api/video/author/{author_id}/all` | 用 author.id（从 State 查） |
| `POST /api/authors/sync-incremental` | `POST /api/video/author/{author_id}/add` | 用 author.id |
| `POST /api/authors/import-csv` | `POST /api/inputer/csv/import` | 前端先保存文件，传 {file_path} |
| `POST /api/authors/import-tencent-doc` | `POST /api/inputer/tencent-doc/import` | 请求体 {doc_url} |
| `GET /api/authors/search?q=` | 直接调 Go: `GET /api/channels/contact/search?keyword=` | 不走 Python 后端 |
| `GET /api/tasks/active` | `GET /api/task/list` | 前端映射 data.list，字段名对齐 |
| `POST /api/task/{id}/cancel` | `POST /api/task/cancel` | 改 body {task_id: id} |
| `POST /api/videos/download` | `POST /api/task/batch-create` | 新端点，传 {video_ids} |
| `POST /api/videos/delete` | `POST /api/video/batch-delete` | 传 {video_ids} |
| `POST /api/open-file` | `POST /api/player/play` | 传 {file_path} 或 {video_id} |

### 4. 缺失函数（新建 utils.js）

- `fetchWithErrorHandling(url, options, actionName)` — 通用 fetch 封装
- `toggleService(event)` — 启动/停止 Go 服务，调 /api/service/start|stop
- `toggleOneClickMonitor()` — 一键监控，调 /api/monitor/start|stop

### 5. 不动的接口

以下后端已有，前端直接用：
- `GET /api/config` — gateway.py 已实现
- `GET /api/logs` — gateway.py 已实现
- `GET /api/cover/{username}/{video_id}` — gateway.py 已实现
- `GET /api/import/failed/{token}` — gateway.py 已实现
- `GET /api/service/status` — base_service.py 已实现
- `POST /api/monitor/start|stop` — monitor.py 已实现

## 涉及文件

| 文件 | 改动 |
|------|------|
| `core/api/routers/task.py` | 加 batch-create 端点 |
| `static/js/app.js` | 去掉 poll，改初始化加载 + 轻量状态轮询 |
| `static/js/datahandle/authorOps.js` | 改 URL（authors/catalog/search/import） |
| `static/js/datahandle/videoOps.js` | 改 URL（download/delete/sync/tasks） |
| `static/js/datahandle/authorDetail.js` | 改 URL（sync-incremental） |
| `static/js/datahandle/progress.js` | 改 URL（tasks/active） |
| `static/js/component/authorDialog.js` | 改 URL（add/delete/author-videos） |
| `static/js/component/utils.js` | 新建，补缺失函数 |
| `static/js/component/search.js` | 改 URL（search 直接调 Go） |
| `static/index.html` | 加 utils.js script 标签 |

## 验证

1. 启动服务，页面加载无 404
2. 作者列表正常渲染
3. 搜索/添加/删除作者可用
4. 下载/取消下载可用
5. 服务状态显示正确
6. 日志面板可用
