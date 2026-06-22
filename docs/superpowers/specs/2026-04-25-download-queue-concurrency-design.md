# 一键监控下载队列并发控制

## Context

一键监控启动后，`_monitor_loop` 会为所有未下载视频一次性创建下载任务。作者多时（10+）可能同时创建 50+ 个任务。Go 后端处理不了这么多并发任务，导致：
- Python 端创建的任务 Go 后端不认识
- `get_downloading_tasks()` 对 N 个任务发 N 次 HTTP 到 Go 后端
- 前端轮询卡住，UI 无响应

**治本方案**：Python 端控制并发，同一时刻最多 N 个活跃任务。

## 方案：滑动窗口队列

`_monitor_loop` 中维护一个滑动窗口：

```
while 监控运行中:
    同步作者最新视频
    收集所有未下载视频（按作者 created_at 降序 + 视频 create_time 降序）

    循环：
        计算当前活跃任务数（pending + running）
        if 活跃数 >= max_concurrent:
            等待 5 秒，重新检查
            continue

        取下一个未下载视频
        if 没有: break  # 全部已创建或已下载
        创建下载任务

    # 本轮所有视频已处理或窗口已满，等待有任务完成
    等待有空位或所有任务完成
```

## 配置

- 默认值：`max_concurrent = 5`
- 存储位置：`config/.env` → `MAX_CONCURRENT=5`
- 前端设置页可配置（1-20）
- `config/settings.py` 新增 `max_concurrent` 属性
- `GET /api/service/config` 返回该值
- `POST /api/service/config` 保存该值（新增端点）

## 改动文件

### 1. `core/monitor/monitor.py` — 滑动窗口逻辑

`_monitor_loop` 方法重写任务创建部分：

```python
# 当前代码（一次性创建所有任务）:
for video in all_undownloaded:
    task_service.create_download_task(video.video_id)

# 改为滑动窗口:
max_concurrent = self._max_concurrent
task_index = 0
while _monitor_running and task_index < len(all_undownloaded):
    active = task_service.get_downloading_tasks()
    active_count = len([t for t in active if t.get("status") in ("pending", "running")])

    if active_count >= max_concurrent:
        self._wait_or_stop(5)
        continue

    video = all_undownloaded[task_index]
    task_service.create_download_task(video.video_id)
    task_index += 1
```

`_max_concurrent` 默认改为 5，从 settings 读取初始值。

### 2. `config/settings.py` — 新增配置项

`SettingsManager` 加 `max_concurrent` 属性，从 `.env` 读取 `MAX_CONCURRENT`，默认 5。

### 3. `config/.env` — 新增

```
MAX_CONCURRENT=5
```

### 4. `core/api/routers/base_service.py` — 配置接口

`GET /api/service/config` 返回增加 `max_concurrent` 字段。

新增 `POST /api/service/config` 端点：接收 `{max_concurrent: N}`，写入 `.env` 文件，更新 `settings` 实例。

### 5. `static/index.html` — 设置页 UI

在现有设置项下方加一行"最大并发下载数"，数字输入框，范围 1-20。

### 6. `static/js/component/settings.js` — 前端读写

`loadSettings()` 读取 `max_concurrent` 填入输入框。
`saveSettings()` 将值通过 `POST /api/service/config` 保存。

## 不改的

- Go 后端 — 零改动
- `TaskService` — 不动
- SSE / 事件总线 — 不动
- 其他前端页面 — 不动

## 附加优化：返回作者列表时异步刷新

### 问题

从作者视频详情页点"返回"时，`loadAllDataFromBackend()` 同步调 `GET /api/video/all` 全量拉数据，
监控运行中时后端响应慢，导致页面卡住。

### 改法

`authorDetail.js` 中返回按钮回调：改为先切回作者列表页，再异步刷新数据。
用户立刻看到旧数据（缓存），数据到了之后无缝更新。

### 改动文件

- `static/js/component/authorDetail.js` — 返回回调改为异步
- `static/js/app.js` — `refreshAuthorsIncremental()` 轻量刷新（只拉统计，不拉全部视频）

### 验证

1. 监控运行中 → 进入作者详情 → 点返回 → 页面秒切不卡
2. 返回后统计数字在 1-2 秒内更新

## 验证

1. 启动一键监控，默认最多同时 5 个任务
2. 前端设置页改为 3，重启监控，最多 3 个
3. 改为 10，重启监控，最多 10 个
4. 50 个视频时不会卡顿
5. 从作者详情页返回不卡顿
