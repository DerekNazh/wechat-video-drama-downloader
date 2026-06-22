# 数据库单元测试设计

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 测试 store.py 与 weixin_client.py API 接口之间的数据交互

**Architecture:** pytest fixture + 内存数据库，每表独立测试文件，CRUD + 幂等性验证

**Tech Stack:** Python, pytest, sqlite3

---

## 目录结构

```
tests/单元测试/数据库/
├── fixture/
│   └── conftest.py              # 共用 fixture
├── 任务进度表/
│   ├── test_创建任务.py
│   ├── test_查询任务.py
│   ├── test_更新任务进度.py
│   ├── test_更新任务状态.py
│   ├── test_删除任务.py
│   ├── test_清空任务.py
│   └── test_幂等性验证.py
├── 作者视频表/
│   ├── test_创建视频.py
│   ├── test_查询视频.py
│   ├── test_删除视频.py
│   ├── test_按作者查询视频.py
│   └── test_幂等性验证.py
├── 作者信息表/
│   ├── test_创建作者.py
│   ├── test_查询作者.py
│   ├── test_更新作者.py
│   ├── test_删除作者.py
│   ├── test_列表查询作者.py
│   └── test_幂等性验证.py
```

---

## 1. conftest.py - 共用 Fixture

**文件:** `tests/单元测试/数据库/fixture/conftest.py`

**功能:**
- 提供内存数据库 fixture
- 提供 mock API 响应数据
- teardown 自动清理

**Fixture 列表:**

| Fixture | 用途 |
|---------|------|
| `db` | 内存数据库实例 (`Database(':memory:')`) |
| `sample_author` | 作者测试数据 |
| `sample_video` | 视频测试数据 |
| `sample_task` | 任务测试数据 |
| `mock_author_api_response` | 模拟 search_authors API 响应 |
| `mock_video_api_response` | 模拟 feed/list API 响应 |

---

## 2. 作者信息表测试

**目录:** `tests/单元测试/数据库/作者信息表/`

| 测试文件 | 测试内容 |
|---------|---------|
| `test_创建作者.py` | 创建作者，验证字段正确存储 |
| `test_查询作者.py` | 按 ID 查询、按 source_author_id 查询 |
| `test_更新作者.py` | 更新作者信息 |
| `test_删除作者.py` | 删除作者 |
| `test_列表查询作者.py` | 列表查询（分页） |
| `test_幂等性验证.py` | 重复创建相同 ID，验证幂等性 |

**数据映射验证:**

| API 字段 | 表字段 |
|---------|--------|
| `contact.username` | `source_author_id` |
| `contact.nickname` | `name` |
| `contact.signature` | `bio` |
| `contact.headUrl` | `avatar_url` |
| `contact.coverImgUrl` | `cover_img_url` |

---

## 3. 作者视频表测试

**目录:** `tests/单元测试/数据库/作者视频表/`

| 测试文件 | 测试内容 |
|---------|---------|
| `test_创建视频.py` | 创建视频，验证字段正确存储 |
| `test_查询视频.py` | 按 video_id 查询 |
| `test_删除视频.py` | 删除视频 |
| `test_按作者查询视频.py` | 按 author_id 列表查询 |
| `test_幂等性验证.py` | 重复创建相同 video_id，验证幂等性 |

**数据映射验证:**

| API 字段 | 表字段 | 转换 |
|---------|--------|------|
| `id` | `video_id` | 直接映射 |
| `objectDesc.description` | `title` | 直接映射 |
| `objectNonceId` | `object_nonce_id` | 直接映射 |
| `media[].url + urlToken` | `url` | 拼接 |
| `media[].spec` | `spec` | 直接映射 |
| `media[].fileSize` | `file_size` | 直接映射 |
| `media[].coverUrl` | `cover_url` | 直接映射 |
| `media[].decodeKey` | `decode_key` | 直接映射 |
| `contact.headUrl` | `author_avatar` | 直接映射 |
| `media[].videoPlayLen` | `duration` | 毫秒→秒 |
| `createtime` | `create_time` | 时间戳→ISO字符串 |

---

## 4. 任务进度表测试

**目录:** `tests/单元测试/数据库/任务进度表/`

| 测试文件 | 测试内容 |
|---------|---------|
| `test_创建任务.py` | 创建任务，验证字段正确存储 |
| `test_查询任务.py` | 按 task_id 查询、按 video_id 查询 |
| `test_更新任务进度.py` | 更新进度（progress, downloaded, speed） |
| `test_更新任务状态.py` | 更新状态（status, error_msg, completed_at） |
| `test_删除任务.py` | 删除任务 |
| `test_清空任务.py` | 清空所有任务 |
| `test_幂等性验证.py` | 重复创建相同 task_id，验证幂等性 |

**状态流转:**
```
pending → running → completed
                  → failed
```

---

## 5. 测试执行

**运行命令:**
```bash
# 运行所有数据库单元测试
pytest tests/单元测试/数据库/ -v

# 运行单个表的测试
pytest tests/单元测试/数据库/作者信息表/ -v

# 运行单个测试文件
pytest tests/单元测试/数据库/任务进度表/test_创建任务.py -v
```

---

## 6. 设计原则

1. **内存数据库** - 使用 `:memory:` 隔离测试，无需清理文件
2. **异常直抛** - 不处理网络异常等复杂情况，直接抛出
3. **幂等性** - 每个测试完成后数据清理，保证测试间独立
4. **Mock API** - 使用固定测试数据，不依赖真实后端

---

**Plan complete.**
