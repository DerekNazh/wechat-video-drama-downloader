# 场景F：增量同步 + 自动下载测试设计

## 目标

验证一键监控运行时，作者发布了新视频，监控能自动完成完整链路：
云端同步 → 增量入库 → 发现新视频 → 创建任务 → 下载完成

## 四个环节 × 第一性原理拆解

### 环节1：何时去云端比较

每轮 `_monitor_loop` 开头（第181行）调 `add_all_authors_latest_videos()`。

| 编号 | 验收点 | 校验方式 |
|------|--------|----------|
| 23a | 监控每轮循环**开头**就调云端同步（不是末尾、不是只调一次） | 第二轮循环开始后，确认 `_fetch_author_videos_from_backend` 被再次调用 |
| 23b | 遍历所有作者，每个作者都调一次（不遗漏） | mock 记录调用时的 author_id，确认 DB 中所有作者都被覆盖 |

### 环节2：云端数据→DB入库（增量对比逻辑）

`add_author_latest_videos` 内部：调 `_fetch_author_videos_from_backend` 拿云端列表 → 跟 DB 对比（video_id 去重）→ 新的 `create_author_video` 入库。

| 编号 | 验收点 | 校验方式 |
|------|--------|----------|
| 24a | 已有 video_id 不重复入库 | 首轮2个视频入DB，第二轮云端返回7个（含原来2个），原有2个的 added=0 |
| 24b | 新 video_id 正确入库 | 第二轮 added=5，DB 总视频数=7 |
| 24c | 入库字段完整（下载必需字段非空） | 新视频的 url、decode_key、spec、object_nonce_id 非空 |
| 24d | 新视频 is_downloaded 初始值为 0 | 入库后立即查询，确认 is_downloaded==0（不是误标为1） |

### 环节3：监控扫描到新视频

同一轮 `_monitor_loop` 内，同步完后紧接着 `list_author_videos` 扫描 `is_downloaded=0`。

| 编号 | 验收点 | 校验方式 |
|------|--------|----------|
| 25a | 同一轮循环内，同步完→扫描→创建任务是连续的 | 不需要独立断言，25b隐含验证 |
| 25b | 新视频被扫描到并创建了下载任务 | 新视频的 task 记录存在，task_count=5 |
| 25c | 已下载视频（is_downloaded=1）不被重复创建任务 | 原有2个视频的任务数不增加，无重复 task_id |

### 环节4：下载完成校验

滑动窗口创建任务 → Go 后端下载 → `get_task_progress` 轮询 → `update_video_downloaded` 标记完成。

| 编号 | 验收点 | 校验方式 |
|------|--------|----------|
| 26a | 磁盘文件真实存在 | os.path.isfile(download_path)==True 且文件大小 > 0 |
| 26b | DB is_downloaded=1 | 查询确认 |
| 26c | DB download_path 非空且路径存在 | download_path 非空字符串，os.path.exists==True |
| 26d | 任务状态 done + completed_at 非空 | task.status in ("done","completed")，completed_at is not None |

## 测试方法

使用真实作者（conftest.py TEST_VIDEOS_DATA 中的作者），确保 Go 后端能识别。

### Mock 策略

Monkeypatch `VideoService._fetch_author_videos_from_backend`：

- **第一轮**（首次同步）：返回 TEST_VIDEOS_DATA 中该作者的原始视频数据（2个视频）
- **第二轮**（模拟新发布）：在原数据基础上追加 5 个新视频（复用已有视频的 url/decode_key，video_id 加前缀区分）

### 新视频构造

从 TEST_VIDEOS_DATA 已有视频复制，修改：
- `video_id`: 加 `new_` 前缀确保唯一
- `create_time`: 设为当天时间（模拟今天发布）
- 其他字段（url, decode_key, spec 等）保持不变，确保 Go 后端能真正下载

## 场景步骤

```
前置：启动 Go 后端 + 微信已连接

场景F-1: 首次同步（验证环节1+2）
  1. 创建1个真实作者到 DB
  2. 启动监控（mock第一轮返回2个视频）
  3. 等待第一轮同步+下载完成
  4. 验收点23a: mock被调用（首轮同步发生）
  5. 验收点24c: DB中2个视频的 url/decode_key 非空
  6. 验收点24d: 2个视频 is_downloaded 初始为0（下载前）
  7. 等待下载完成 → is_downloaded=1

场景F-2: 增量同步（完整链路）
  8. 第一轮下载完毕后，mock切换为返回 2+5=7 个视频
  9. 等待第二轮监控循环开始
  10. 验收点23a: mock被第二次调用（第二轮开头再次同步）
  11. 验收点24a: 原有2个视频 skipped（不重复入库）
  12. 验收点24b: added=5, DB总视频数=7
  13. 验收点24c: 5个新视频的 url/decode_key 非空
  14. 验收点24d: 5个新视频 is_downloaded==0
  15. 验收点25b: 监控创建5个下载任务
  16. 验收点25c: 原有2个视频无新任务（不重复下载）
  17. 等待5个新视频下载完成
  18. 验收点26a: os.path.isfile==True, 文件大小>0
  19. 验收点26b: is_downloaded==1
  20. 验收点26c: download_path 非空
  21. 验收点26d: task status=done, completed_at 非空
```

## 文件修改

在 `tests/集成测试/monitor/一键监控服务启停/一键监控和服务启停.py` 末尾（场景E之后、清理之前）新增场景F。

不修改任何生产代码。
