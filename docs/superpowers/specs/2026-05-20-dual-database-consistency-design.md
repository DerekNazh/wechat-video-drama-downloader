# 双数据库强一致性架构设计

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 app.db 和 gopeed.db 双数据库的强一致性，通过补偿事务、事件驱动、定期清理等机制保证数据一致性。

**Architecture:** 补偿事务模式（Saga）处理双写，事件总线协调组件状态，WebSocket + HTTP 轮询双保险保证进度同步，启动时 + 定期后台组合清理孤立任务。

**Tech Stack:** Python 3.8+, FastAPI, SQLite, WebSocket, threading

---

## 一、背景与约束

### 核心约束

Go 后端 (`wx_video_download.exe`) 是**不可修改源码的第三方软件**：
- 无法扩展 gopeed.db 结构（无法添加 `video_id`、`author_id` 等业务字段）
- 无法修改其 API 行为
- 无法控制其数据持久化策略

### 当前问题

| 问题 | 描述 | 影响 |
|------|------|------|
| 双写时序问题 | 先写 Go 后写 App，App 失败导致孤立任务 | 并发窗口被占用 |
| 监控器阻塞 | Go 断开后监控器卡在等待循环 | 无法创建新任务 |
| 损坏文件残留 | 下载中断留下损坏 .mp4 文件 | 重新下载追加到损坏数据 |
| 进度过时 | WebSocket 断连时进度不更新 | 用户看到旧状态 |
| 孤立任务累积 | 运行中异常导致两边不一致 | 数据不一致 |

---

## 二、设计决策汇总

| # | 问题 | 决策 |
|---|------|------|
| 1 | 双写策略 | 补偿事务模式（Saga）— App 失败自动回滚 Go |
| 2 | 监控器联动 | 事件驱动 + WebSocket 重连恢复 |
| 3 | 损坏文件处理 | 启动时清理 + 任务前检查 |
| 4 | 进度同步 | WebSocket + HTTP 轮询双保险 |
| 5 | 孤立任务清理 | 启动时全量 + 定期后台（10分钟） |
| 6 | 回滚重试 | 立即重试 3 次，间隔 1 秒 |

---

## 三、架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                        Python App (FastAPI)                      │
│                                                                  │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              app.db (主数据库 - 持久化)                   │   │
│  │  authors | author_videos | download_tasks                │   │
│  └─────────────────────────────────────────────────────────┘   │
│                              ▲                                   │
│                              │ 补偿事务 + 定期对账               │
│                              │                                   │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │              gopeed.db (Go 后端数据库)                    │   │
│  │  tasks (不可修改结构)                                     │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                  │
│  Go 后端 (wx_video_download.exe) - 不可修改源码                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 四、核心组件设计

### 4.1 补偿事务管理器 (CompensationTransactionManager)

**职责：** 封装所有双写操作，保证 Go 和 App 数据库的一致性

**接口设计：**

```python
class CompensationTransactionManager:
    """补偿事务管理器 - 处理双写操作的一致性"""

    def __init__(self, go_client: WeixinClient, file_validator: FileValidator):
        self._go_client = go_client
        self._file_validator = file_validator

    def create_task_with_compensation(self, video_id: str) -> dict:
        """
        创建下载任务（带补偿）

        流程：
        1. 文件校验器检查目标文件是否存在，存在则删除
        2. 调用 Go API 创建任务 → 获取 task_id
        3. 写入 app.db.download_tasks
        4. 步骤 3 失败 → 回滚 Go 任务（重试 3 次）

        返回：
          成功: {"success": True, "task_id": "..."}
          失败: {"success": False, "error": "..."}
        """

    def delete_task_with_compensation(self, task_id: str) -> dict:
        """
        删除下载任务（带补偿）

        流程：
        1. 调用 Go API 删除任务
        2. 删除 app.db.download_tasks 记录
        3. 步骤 2 失败 → 记录日志等待定期清理

        注意：删除操作不需要回滚 Go，因为 Go 任务已删除是期望状态
        """

    def _rollback_go_task(self, task_id: str, operation: str) -> bool:
        """
        回滚 Go 任务

        参数：
          task_id: Go 任务 ID
          operation: 操作类型（"create" / "delete"）

        重试策略：
          最多 3 次，间隔 1 秒
          失败后记录日志，等待定期清理

        返回：
          True: 回滚成功
          False: 回滚失败（已记录日志）
        """
```

**状态流转：**

```
创建任务：
  [开始] → 文件检查 → Go 创建 → App 写入 → [成功]
                          ↓ 失败
                    回滚 Go → [成功/失败]
                          ↓ 失败
                    重试 3 次 → [成功/失败]
                          ↓ 失败
                    记录日志 → 等待定期清理

删除任务：
  [开始] → Go 删除 → App 删除 → [成功]
                    ↓ 失败
              记录日志 → 等待定期清理（App 有孤立记录）
```

---

### 4.2 事件总线 (EventBus)

**职责：** 管理 Go 后端连接状态，通知监控器等组件

**接口设计：**

```python
class EventBus:
    """事件总线 - 管理 Go 后端连接状态"""

    # 事件类型
    GO_CONNECTED = "go_connected"        # Go 后端已连接
    GO_DISCONNECTED = "go_disconnected"  # Go 后端已断开

    def __init__(self):
        self._listeners: Dict[str, List[Callable]] = {}
        self._go_online: bool = False  # Go 后端状态

    def subscribe(self, event: str, callback: Callable):
        """订阅事件"""

    def unsubscribe(self, event: str, callback: Callable):
        """取消订阅"""

    def emit(self, event: str, data: dict = None):
        """发布事件"""

    @property
    def go_online(self) -> bool:
        """获取 Go 后端状态"""
        return self._go_online

    def set_go_online(self, online: bool):
        """设置 Go 后端状态并发布事件"""
        if self._go_online != online:
            self._go_online = online
            event = self.GO_CONNECTED if online else self.GO_DISCONNECTED
            self.emit(event)
```

**事件触发时机：**

| 事件 | 触发源 | 触发条件 |
|------|--------|----------|
| `GO_CONNECTED` | WebSocket 监听器 | WebSocket 连接成功 + HTTP API 可用 |
| `GO_DISCONNECTED` | WebSocket 监听器 | WebSocket 断开 或 HTTP API 超时 |

---

### 4.3 进度同步器 (ProgressSynchronizer)

**职责：** 保证进度数据的实时性和可靠性

**接口设计：**

```python
class ProgressSynchronizer:
    """进度同步器 - WebSocket + HTTP 轮询双保险"""

    def __init__(self, event_bus: EventBus, go_client: WeixinClient):
        self._event_bus = event_bus
        self._go_client = go_client
        self._ws_connected = False
        self._poll_thread = None

        # 订阅连接状态
        event_bus.subscribe(EventBus.GO_CONNECTED, self._on_ws_connected)
        event_bus.subscribe(EventBus.GO_DISCONNECTED, self._on_ws_disconnected)

    def _on_ws_connected(self):
        """WebSocket 连接 → 停止 HTTP 轮询"""
        self._ws_connected = True
        if self._poll_thread:
            self._poll_thread.stop()
            self._poll_thread = None
        logger.info("[进度同步] WebSocket 连接，停止轮询")

    def _on_ws_disconnected(self):
        """WebSocket 断开 → 启动 HTTP 轮询"""
        self._ws_connected = False
        if not self._poll_thread:
            self._poll_thread = PollThread(self._poll_progress, interval=5)
            self._poll_thread.start()
        logger.warning("[进度同步] WebSocket 断开，启动轮询")

    def _poll_progress(self):
        """HTTP 轮询进度（每 5 秒）"""
        tasks = db.get_active_download_tasks()
        for task in tasks:
            try:
                progress = self._go_client.get_task_progress(task.task_id)
                if progress:
                    db.update_task_progress(task.task_id, progress)
            except Exception as e:
                logger.warning(f"[轮询] 任务 {task.task_id} 进度获取失败: {e}")

    def on_ws_message(self, message: dict):
        """WebSocket 推送处理（实时）"""
        if not self._ws_connected:
            return
        task = message.get("data", {}).get("task")
        if task:
            db.update_task_progress(task["id"], task)
```

**状态切换流程：**

```
正常状态：
  WebSocket 连接 → _ws_connected = True
  → 推送消息直接写入 app.db
  → HTTP 轮询线程停止

异常状态：
  WebSocket 断开 → _ws_connected = False
  → 启动 HTTP 轮询线程（5秒间隔）
  → 轮询写入 app.db

恢复状态：
  WebSocket 重连 → _ws_connected = True
  → 停止 HTTP 轮询线程
  → 恢复推送模式
```

---

### 4.4 文件校验器 (FileValidator)

**职责：** 检测并清理损坏的视频文件

**接口设计：**

```python
class FileValidator:
    """文件校验器 - 检测并清理损坏文件"""

    def validate_on_startup(self):
        """
        启动时校验

        检查范围：
        1. is_downloaded=1 但文件不存在 → 重置状态
        2. progress < 100% 且文件存在 → 删除损坏文件，重置状态

        已有 reconcile_orphaned_downloads() 扩展：
        - 原只检查 is_downloaded=1
        - 新增检查未完成的损坏文件
        """
        videos = db.list_all_videos()
        for video in videos:
            path = video.download_path

            # 情况 1：标记已下载但文件丢失
            if video.is_downloaded == 1 and not os.path.isfile(path):
                db.reset_video_downloaded(video.video_id)
                logger.warning(f"[校验] 视频文件丢失: {video.video_id}")

            # 情况 2：未完成但有残留文件（损坏）
            if video.is_downloaded == 0 and video.progress > 0 and os.path.isfile(path):
                os.remove(path)
                db.reset_video_progress(video.video_id)
                logger.warning(f"[校验] 删除损坏文件: {path}")

    def check_before_create_task(self, video_id: str) -> bool:
        """
        创建任务前检查

        流程：
        1. 获取视频信息，计算目标路径
        2. 文件存在 → 删除（因为 Go 会追加写入）
        3. 返回 True 表示可以创建任务

        返回：
          True: 可以创建任务
          False: 检查失败，不应创建
        """
        video = db.get_author_video(video_id)
        if not video:
            return False

        # 计算目标路径（与 Go 后端命名规则一致）
        path = self._calculate_target_path(video)

        if os.path.isfile(path):
            logger.warning(f"[任务前检查] 删除已存在文件: {path}")
            os.remove(path)

        return True

    def _calculate_target_path(self, video: AuthorVideo) -> str:
        """计算目标文件路径（模拟 Go 后端命名）"""
        # 格式: {download_dir}/{date}_{title}_{spec}.mp4
        filename = f"{video.publish_date}_{video.title}_{video.spec}.mp4"
        return os.path.join(settings.download_dir, filename)
```

**调用时机：**

| 函数 | 调用时机 | 调用位置 |
|------|----------|----------|
| `validate_on_startup()` | App 启动时 | `core/api/app.py` 启动流程 |
| `check_before_create_task()` | 创建任务前 | `CompensationTransactionManager.create_task_with_compensation()` |

---

### 4.5 孤立任务清理器 (OrphanTaskCleaner)

**职责：** 清理 Go 和 App 数据库中的不一致任务记录

**接口设计：**

```python
class OrphanTaskCleaner:
    """孤立任务清理器 - 保证双数据库任务一致性"""

    def __init__(self, go_client: WeixinClient, interval: int = 600):
        """
        参数：
          go_client: Go 后端 API 客户端
          interval: 定期清理间隔（秒），默认 600 秒（10 分钟）
        """
        self._go_client = go_client
        self._interval = interval
        self._running = False
        self._thread = None

    def cleanup_on_startup(self):
        """
        启动时全量清理

        流程：
        1. 获取 Go 端所有任务列表
        2. 获取 App 端所有活跃任务
        3. 对比差异：
           - App 有但 Go 无 → 删除 App 记录
           - Go 有但 App 无 → 删除 Go 任务（孤立任务）
        """
        logger.info("[清理器] 启动时全量清理开始")

        # 获取两边任务列表
        go_tasks = self._go_client.get_task_list()
        go_task_ids = {t["id"] for t in go_tasks}

        app_tasks = db.get_all_download_tasks()
        app_task_ids = {t.task_id for t in app_tasks}

        # App 有但 Go 无 → 删除 App 记录
        orphan_in_app = app_task_ids - go_task_ids
        for task_id in orphan_in_app:
            db.delete_download_task(task_id)
            logger.warning(f"[清理器] 删除 App 孤立记录: {task_id}")

        # Go 有但 App 无 → 删除 Go 任务
        orphan_in_go = go_task_ids - app_task_ids
        for task_id in orphan_in_go:
            self._go_client.delete_task(task_id)
            logger.warning(f"[清理器] 删除 Go 孤立任务: {task_id}")

        logger.info(f"[清理器] 启动清理完成: App 删除 {len(orphan_in_app)}, Go 删除 {len(orphan_in_go)}")

    def start_periodic_cleanup(self):
        """启动定期后台清理"""
        self._running = True
        self._thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self._thread.start()
        logger.info(f"[清理器] 定期清理已启动，间隔 {self._interval} 秒")

    def stop(self):
        """停止定期清理"""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        logger.info("[清理器] 定期清理已停止")

    def _cleanup_loop(self):
        """定期清理循环"""
        while self._running:
            time.sleep(self._interval)
            if not self._running:
                break
            self._incremental_cleanup()

    def _incremental_cleanup(self):
        """
        增量清理（只检查活跃任务）

        流程：
        1. 获取 App 端活跃任务（status=pending/running）
        2. 逐个检查 Go 端是否存在
        3. Go 不存在 → 删除 App 记录
        """
        app_active_tasks = db.get_active_download_tasks()

        for task in app_active_tasks:
            try:
                go_task = self._go_client.get_task_progress(task.task_id)
                if not go_task:
                    # Go 端不存在，删除 App 记录
                    db.delete_download_task(task.task_id)
                    logger.warning(f"[清理器] 增量清理: {task.task_id}")
            except Exception as e:
                logger.warning(f"[清理器] 检查任务失败: {task.task_id}, {e}")
```

**调用时机：**

| 函数 | 调用时机 | 调用位置 |
|------|----------|----------|
| `cleanup_on_startup()` | App 启动时 | `core/api/app.py` 启动流程 |
| `start_periodic_cleanup()` | App 启动后 | `core/api/app.py` 启动流程 |
| `stop()` | App 关闭时 | `core/api/app.py` 关闭流程 |

---

## 五、整体架构集成

### 组件依赖关系

```
┌─────────────────────────────────────────────────────────────────┐
│                          EventBus                                │
│                    (连接状态事件中心)                             │
└─────────────────────────────────────────────────────────────────┘
         │                    │                    │
         ▼                    ▼                    ▼
┌─────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Monitor   │    │ProgressSynchronizer│   │ WebSocket监听器 │
│   (监控器)   │    │   (进度同步器)      │   │ (socket_client) │
└─────────────┘    └─────────────────┘    └─────────────────┘
         │                    │
         │                    │
         ▼                    ▼
┌─────────────────────────────────────────────────────────────────┐
│              CompensationTransactionManager                      │
│                    (补偿事务管理器)                               │
│                                                                  │
│  依赖：FileValidator.check_before_create_task()                 │
└─────────────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────┐
│              OrphanTaskCleaner                                   │
│              (孤立任务清理器)                                      │
└─────────────────────────────────────────────────────────────────┘
```

### 启动流程

```python
# core/api/app.py

def startup():
    # 1. 创建事件总线（最先）
    event_bus = EventBus()

    # 2. 文件校验器 - 启动时校验
    file_validator = FileValidator()
    file_validator.validate_on_startup()

    # 3. 孤立任务清理器 - 启动时清理
    orphan_cleaner = OrphanTaskCleaner(go_client)
    orphan_cleaner.cleanup_on_startup()

    # 4. 启动 Go 后端
    go_service.start()

    # 5. 启动 WebSocket 监听器（发布连接事件）
    socket_client.start(event_bus)

    # 6. 启动进度同步器
    progress_sync = ProgressSynchronizer(event_bus, go_client)

    # 7. 启动监控器（订阅连接事件）
    monitor = Monitor(event_bus)
    monitor.start()

    # 8. 启动定期清理
    orphan_cleaner.start_periodic_cleanup()
```

### 关闭流程

```python
def shutdown():
    # 1. 停止监控器
    monitor.stop()

    # 2. 停止定期清理
    orphan_cleaner.stop()

    # 3. 停止 WebSocket
    socket_client.stop()

    # 4. 停止 Go 后端
    go_service.stop()
```

---

## 六、监控器改造

监控器需要订阅事件总线，在 Go 离线时暂停，恢复时继续：

```python
class Monitor:
    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus
        self._paused = False

        # 订阅事件
        event_bus.subscribe(EventBus.GO_DISCONNECTED, self._on_go_offline)
        event_bus.subscribe(EventBus.GO_CONNECTED, self._on_go_online)

    def _on_go_offline(self):
        """Go 离线 → 暂停监控"""
        self._paused = True
        logger.warning("[监控器] Go 后端离线，暂停监控")

    def _on_go_online(self):
        """Go 恢复 → 恢复监控"""
        self._paused = False
        logger.info("[监控器] Go 后端恢复，继续监控")

    def _monitor_loop(self):
        while self._running:
            if self._paused:
                time.sleep(5)  # 暂停时等待
                continue
            # 正常监控逻辑...
```

---

## 七、文件改动清单

| 文件 | 改动类型 | 说明 |
|------|----------|------|
| `core/utils/event_bus.py` | 新建 | 事件总线组件 |
| `core/utils/compensation_manager.py` | 新建 | 补偿事务管理器 |
| `core/utils/progress_synchronizer.py` | 新建 | 进度同步器 |
| `core/utils/file_validator.py` | 新建 | 文件校验器 |
| `core/utils/orphan_cleaner.py` | 新建 | 孤立任务清理器 |
| `core/api/app.py` | 修改 | 集成启动/关闭流程 |
| `core/monitor/monitor.py` | 修改 | 订阅事件总线，支持暂停/恢复 |
| `core/utils/socket_client.py` | 修改 | 发布连接事件到事件总线 |
| `core/service/task.py` | 修改 | 使用补偿事务管理器 |

---

## 八、测试要点

1. **补偿事务测试**
   - Go 创建成功，App 写入失败 → 验证回滚
   - 回滚失败 → 验证重试 3 次
   - 3 次失败 → 验证日志记录

2. **事件总线测试**
   - WebSocket 断开 → 验证 `GO_DISCONNECTED` 事件
   - WebSocket 重连 → 验证 `GO_CONNECTED` 事件
   - 监控器暂停/恢复 → 验证不创建新任务

3. **进度同步测试**
   - WebSocket 正常 → 验证实时推送
   - WebSocket 断开 → 验证 HTTP 轮询启动
   - WebSocket 恢复 → 验证轮询停止

4. **文件校验测试**
   - 启动时有损坏文件 → 验证删除
   - 创建任务时文件存在 → 验证删除

5. **孤立清理测试**
   - 启动时有孤立任务 → 验证清理
   - 运行 10 分钟 → 验证定期清理执行
