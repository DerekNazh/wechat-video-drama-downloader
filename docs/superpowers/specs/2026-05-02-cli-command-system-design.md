# AI-Callable CLI 命令系统设计

## 目标

为视频下载器构建一个 AI 可调用的 CLI 命令行系统，让 AI 通过子进程调用 `python -m core.cli <资源> <动作> [选项]` 完成所有软件操作，包括短视频和直播回放的统一管理。

## 架构

- **框架**: Typer（基于类型注解，与项目 Pydantic 生态契合）
- **调用方式**: AI 通过 subprocess 调用 CLI 命令
- **输出格式**: 默认 JSON（AI 解析），`--pretty` 切换为人类可读表格
- **调用路径**: 直接调用 `core/service/` 下的 Service 类，不走 HTTP API
- **视频类型**: 所有涉及视频的命令统一支持 `--type short_video|live_replay|all`

## 目录结构

```
core/cli/
├── __init__.py          # Typer app 实例 + main 回调
├── __main__.py          # python -m core.cli 支持
├── author.py            # author 子命令组
├── video.py             # video 子命令组
├── task.py              # task 子命令组
├── service.py           # service 子命令组
├── output.py            # 输出格式化（JSON/表格）
└── ctx.py               # 共享上下文（数据库初始化、Service 实例）
```

## 上下文初始化 (ctx.py)

CLI 命令执行前需要初始化数据库连接和 Service 实例：

1. 调用 `core.utils.database.db.init()` 初始化数据库
2. 实例化各 Service 类（AuthorService, VideoService, TaskService, SearchService）
3. 通过 Typer `callback` 在每条命令执行前自动调用初始化
4. 需要微信在线的操作（搜索、同步、下载）通过 `core.utils.base_servier.WechatVideoService` 检查状态

## 命令详细设计

### author 子命令

| 命令 | 参数 | 说明 | Service 调用 |
|------|------|------|-------------|
| `author list` | `--type all\|short_video\|live_replay`, `--pretty` | 列出作者，含短视频/回放统计 | AuthorService.list_with_stats() |
| `author get` | `--id AUTHOR_ID` | 获取作者详情+视频统计 | AuthorService.get() + VideoService.list_by_author() |
| `author search` | `--keyword KEYWORD` | 搜索作者（需微信在线） | SearchService.search_authors() |
| `author add` | `--keyword KEYWORD` | 搜索并添加作者+视频 | SearchService.add_author_by_keyword() |
| `author sync` | `--id AUTHOR_ID` | 同步作者最新视频 | VideoService.add_author_latest_videos() |
| `author delete` | `--id AUTHOR_ID`, `--force` | 删除作者及所有视频文件 | AuthorService.delete() |

### video 子命令

| 命令 | 参数 | 说明 | Service 调用 |
|------|------|------|-------------|
| `video list` | `--author-id`, `--type all\|short_video\|live_replay`, `--status downloaded\|pending`, `--page 1`, `--page-size 20` | 列出视频 | VideoService.list() |
| `video get` | `--id VIDEO_ID` | 获取视频详情 | VideoService.get() |
| `video download` | `--ids ID1,ID2,...` | 下载指定视频 | TaskService.batch_create() |
| `video download-all` | `--type all\|short_video\|live_replay`, `--author-id` | 下载所有待下载视频 | TaskService.download_all() |
| `video delete` | `--ids ID1,ID2,...` | 删除视频 | VideoService.batch_delete() |
| `video stats` | 无 | 全局视频统计（按类型/状态） | VideoService.stats() |

### task 子命令

| 命令 | 参数 | 说明 | Service 调用 |
|------|------|------|-------------|
| `task list` | `--status running\|pending\|completed\|failed` | 列出任务 | TaskService.list() |
| `task cancel` | `--id TASK_ID` | 取消任务 | TaskService.cancel() |
| `task cancel-all` | 无 | 取消所有任务 | TaskService.cancel_all() |
| `task progress` | `--id TASK_ID` | 查看任务进度 | TaskService.get() |

### service 子命令

| 命令 | 参数 | 说明 | Service 调用 |
|------|------|------|-------------|
| `service status` | 无 | Go后端+微信连接状态 | WechatVideoService.is_running() + wechat_status check |
| `service start` | 无 | 启动Go后端 | WechatVideoService.start() |
| `service stop` | 无 | 停止Go后端 | WechatVideoService.stop() |
| `service restart` | 无 | 重启Go后端 | WechatVideoService.restart() |
| `service config` | `--key KEY`, `--value VALUE` | 查看/修改配置 | 直接读写 config |
| `service monitor start` | 无 | 启动监控 | MonitorService.start() |
| `service monitor stop` | 无 | 停止监控 | MonitorService.stop() |
| `service monitor status` | 无 | 监控状态 | MonitorService.status() |
| `service logs` | `--lines 50` | 查看最近N条日志 | 日志文件读取 |

## 输出格式

### JSON 输出（默认）

所有命令默认输出 JSON，结构统一：

```json
{
  "code": 0,
  "message": "success",
  "data": { ... }
}
```

错误时：

```json
{
  "code": 1,
  "message": "作者不存在",
  "data": null
}
```

### 表格输出（--pretty）

`--pretty` 选项切换为人类可读的表格格式，使用 `rich` 库渲染。

### author list 示例

```json
{
  "code": 0,
  "data": [
    {
      "id": "a1b2c3",
      "name": "作者名",
      "username": "wxid_xxx",
      "short_video": {"total": 10, "downloaded": 8},
      "live_replay": {"total": 3, "downloaded": 1}
    }
  ]
}
```

### video list 示例

```json
{
  "code": 0,
  "data": {
    "items": [
      {
        "id": "v1",
        "title": "视频标题",
        "video_type": "short_video",
        "downloaded": true,
        "file_size": 12345678,
        "duration": 120,
        "create_time": "2026-05-01T12:00:00"
      }
    ],
    "total": 100,
    "page": 1,
    "page_size": 20
  }
}
```

### service status 示例

```json
{
  "code": 0,
  "data": {
    "go_backend_running": true,
    "wechat_connected": true,
    "monitor_running": false,
    "active_tasks": 2,
    "today_downloaded": 5
  }
}
```

## 视频类型统一处理

所有涉及视频的命令通过 `--type` 参数统一筛选：

- `--type short_video`：仅短视频
- `--type live_replay`：仅直播回放
- `--type all`（默认）：全部类型

此参数影响：
- `author list`：统计数字按类型过滤
- `video list`：返回视频按类型过滤
- `video download-all`：只下载指定类型的待下载视频
- `video stats`：统计按类型分组

## 错误处理

- 参数缺失/无效：Typer 自动生成帮助信息，退出码 2
- 微信未连接：返回 `{"code": 1, "message": "微信未连接，请先启动微信客户端"}`，退出码 1
- Go 后端未运行：返回 `{"code": 1, "message": "Go后端未运行"}`，退出码 1
- 数据库错误：返回 `{"code": 1, "message": "数据库错误: ..."}`，退出码 1
- 操作成功：退出码 0

## 依赖

- `typer[all]`：CLI 框架（含 rich 依赖）
- 项目现有依赖：fastapi, pydantic, httpx, requests

## AI 调用约定

AI 调用 CLI 时遵循以下约定：

1. 不使用 `--pretty`，始终使用 JSON 输出
2. 批量 ID 用逗号分隔：`--ids id1,id2,id3`
3. 先调用 `service status` 确认服务状态，再执行操作
4. 下载前先调用 `video list --status pending` 确认待下载视频
5. 所有命令通过 `python -m core.cli` 调用
