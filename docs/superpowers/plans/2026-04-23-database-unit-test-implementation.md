# 数据库单元测试实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现数据库单元测试，覆盖 store.py 三张表的 CRUD + 幂等性验证

**Architecture:** pytest fixture + 内存数据库 (:memory:)，每表独立测试文件，独立执行

**Tech Stack:** Python, pytest, sqlite3

---

### Task 1: 创建 fixture 共用配置

**Files:**
- Create: `tests/单元测试/数据库/fixture/__init__.py`
- Create: `tests/单元测试/数据库/fixture/conftest.py`

- [ ] **Step 1: 创建 fixture 目录和 __init__.py**

```python
# tests/单元测试/数据库/fixture/__init__.py
"""数据库单元测试 fixture"""
```

- [ ] **Step 2: 创建 conftest.py**

```python
"""数据库单元测试共用的 pytest fixture"""
import pytest
import sys
from pathlib import Path

# 添加项目根目录到 sys.path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from core.service.store import Database, Author, AuthorVideo, DownloadTask
from datetime import datetime


@pytest.fixture
def db():
    """内存数据库实例，每次测试独立"""
    database = Database(":memory:")
    yield database
    # teardown: 测试完成后自动清理
    database.clear_download_tasks()


@pytest.fixture
def sample_author():
    """作者测试数据"""
    return Author(
        id="author_test_001",
        source_author_id="test_user@finder",
        name="测试作者",
        tag=None,
        bio="这是简介",
        avatar_url="https://wx.qlogo.cn/test.jpg",
        cover_img_url="https://wx.qlogo.cn/cover.jpg",
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
    )


@pytest.fixture
def sample_video():
    """视频测试数据"""
    return AuthorVideo(
        video_id="video_test_001",
        author_id="author_test_001",
        title="测试视频标题",
        object_nonce_id="nonce_12345",
        url="https://finder.video.qq.com/test?urlToken=xxx",
        spec="xW30",
        file_size=50000000,
        cover_url="https://finder.video.qq.com/cover.jpg",
        decode_key=12345,
        author_avatar="https://wx.qlogo.cn/test.jpg",
        duration=120,
        create_time="2025-10-20T22:31:40",
    )


@pytest.fixture
def sample_task():
    """任务测试数据"""
    return DownloadTask(
        task_id="task_test_001",
        video_id="video_test_001",
        url="https://finder.video.qq.com/test",
        title="测试视频",
        filename="测试视频",
        spec="xW30",
        suffix=".mp4",
        key=0,
        status="pending",
        progress=0,
        downloaded=0,
        total_size=0,
        speed=0,
        error_msg="",
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
        completed_at=None,
    )
```

- [ ] **Step 3: 验证 fixture**

Run: `pytest tests/单元测试/数据库/fixture/conftest.py -v --collect-only`
Expected: 收集到 4 个 fixture (db, sample_author, sample_video, sample_task)

---

### Task 2: 作者信息表测试

**Files:**
- Create: `tests/单元测试/数据库/作者信息表/__init__.py`
- Create: `tests/单元测试/数据库/作者信息表/test_创建作者.py`
- Create: `tests/单元测���/数据库/作者信息表/test_查询作者.py`
- Create: `tests/单元测试/数据库/作者信息表/test_更新作者.py`
- Create: `tests/单元测试/数据库/作者信息表/test_删除作者.py`
- Create: `tests/单元测试/数据库/作者信息表/test_列表查询作者.py`
- Create: `tests/单元测试/数据库/作者信息表/test_幂等性验证.py`

- [ ] **Step 1: 创建作者信息表目录和 __init__.py**

```python
# tests/单元测试/数据库/作者信息表/__init__.py
"""Author 表单元测试"""
```

- [ ] **Step 2: test_创建作者.py**

```python
"""创建作者测试"""
import pytest


def test_create_author(db, sample_author):
    """T1: 创建作者，验证字段正确存储"""
    result = db.create_author(sample_author)
    assert result is True

    # 查询验证
    author = db.get_author(sample_author.id)
    assert author is not None
    assert author.name == sample_author.name
    assert author.source_author_id == sample_author.source_author_id
    assert author.bio == sample_author.bio
    assert author.avatar_url == sample_author.avatar_url
```

- [ ] **Step 3: test_查询作者.py**

```python
"""查询作者测试"""
import pytest


def test_get_author_by_id(db, sample_author):
    """T1: 按 ID 查询作者"""
    db.create_author(sample_author)

    author = db.get_author(sample_author.id)
    assert author is not None
    assert author.id == sample_author.id


def test_get_author_by_source_id(db, sample_author):
    """T2: 按 source_author_id 查询作者"""
    db.create_author(sample_author)

    author = db.get_author_by_source_id(sample_author.source_author_id)
    assert author is not None
    assert author.source_author_id == sample_author.source_author_id
```

- [ ] **Step 4: test_更新作者.py**

```python
"""更新作者测试"""
import pytest
from datetime import datetime


def test_update_author(db, sample_author):
    """T1: 更新作者信息"""
    db.create_author(sample_author)

    # 更新
    sample_author.bio = "新的简介"
    sample_author.updated_at = datetime.now().isoformat()
    result = db.update_author(sample_author)
    assert result is True

    # 验证
    author = db.get_author(sample_author.id)
    assert author.bio == "新的简介"
```

- [ ] **Step 5: test_删除作者.py**

```python
"""删除作者测试"""
import pytest


def test_delete_author(db, sample_author):
    """T1: 删除作者"""
    db.create_author(sample_author)

    result = db.delete_author(sample_author.id)
    assert result is True

    # 验证已删除
    author = db.get_author(sample_author.id)
    assert author is None
```

- [ ] **Step 6: test_列表查询作者.py**

```python
"""列表查询作者测试"""
import pytest
from datetime import datetime


def test_list_authors(db, sample_author):
    """T1: 列表查询（分页）"""
    # 创建多个作者
    for i in range(3):
        author = Author(
            id=f"author_{i}",
            source_author_id=f"test_{i}@finder",
            name=f"作者{i}",
            tag=None,
            bio="简介",
            avatar_url="https://test.jpg",
            cover_img_url=None,
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
        )
        db.create_author(author)

    # 列表查询
    authors = db.list_authors(limit=10)
    assert len(authors) >= 3
```

- [ ] **Step 7: test_幂等性验证.py**

```python
"""幂等性验证测试"""
import pytest
from datetime import datetime


def test_create_author_idempotent(db, sample_author):
    """T1: 重复创建相同 ID，验证幂等性"""
    # 第一次创建
    result1 = db.create_author(sample_author)
    assert result1 is True

    # 第二次创建相同 ID
    result2 = db.create_author(sample_author)
    assert result2 is False  # 返回 False 表示已存在

    # 验证数据唯一
    authors = db.list_authors()
    assert len(authors) == 1
```

- [ ] **Step 8: 运行作者信息表测试**

Run: `pytest tests/单元测试/数据库/作者信息表/ -v`
Expected: 7 tests passed

---

### Task 3: 作者视频表测试

**Files:**
- Create: `tests/单元测试/数据库/作者视频表/__init__.py`
- Create: `tests/单元测试/数据库/作者视频表/test_创建视频.py`
- Create: `tests/单元测试/数据库/作者视频表/test_查询视频.py`
- Create: `tests/单元测试/数据库/作者视频表/test_删除视频.py`
- Create: `tests/单元测试/数据库/作者视频表/test_按作者查询视频.py`
- Create: `tests/单元测试/数据库/作者视频表/test_幂等性验证.py`

- [ ] **Step 1: 创建作者视频表目录和 __init__.py**

```python
# tests/单元测试/数据库/作者视频表/__init__.py
"""AuthorVideo 表单元测试"""
```

- [ ] **Step 2: test_创建视频.py**

```python
"""创建视频测试"""
import pytest


def test_create_video(db, sample_video):
    """T1: 创建视频，验证字段正确存储"""
    # 先创建作者（外键依赖）
    from datetime import datetime
    from core.service.store import Author
    author = Author(
        id=sample_video.author_id,
        source_author_id="test@finder",
        name="测试作者",
        tag=None,
        bio="简介",
        avatar_url="https://test.jpg",
        cover_img_url=None,
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
    )
    db.create_author(author)

    result = db.create_author_video(sample_video)
    assert result is True

    # 查询验证
    video = db.get_author_video(sample_video.video_id)
    assert video is not None
    assert video.title == sample_video.title
    assert video.url == sample_video.url
    assert video.spec == sample_video.spec
```

- [ ] **Step 3: test_查询视频.py**

```python
"""查询视频测试"""
import pytest
from datetime import datetime
from core.service.store import Author


def test_get_video(db, sample_video):
    """T1: 按 video_id 查询"""
    # 先创建作者
    author = Author(
        id=sample_video.author_id,
        source_author_id="test@finder",
        name="测试作者",
        tag=None,
        bio="简介",
        avatar_url="https://test.jpg",
        cover_img_url=None,
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
    )
    db.create_author(author)
    db.create_author_video(sample_video)

    video = db.get_author_video(sample_video.video_id)
    assert video is not None
    assert video.video_id == sample_video.video_id
```

- [ ] **Step 4: test_删除视频.py**

```python
"""删除视频测试"""
import pytest
from datetime import datetime
from core.service.store import Author


def test_delete_video(db, sample_video):
    """T1: 删除视频"""
    # 先创建作者
    author = Author(
        id=sample_video.author_id,
        source_author_id="test@finder",
        name="测试作者",
        tag=None,
        bio="简介",
        avatar_url="https://test.jpg",
        cover_img_url=None,
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
    )
    db.create_author(author)
    db.create_author_video(sample_video)

    result = db.delete_author_video(sample_video.video_id)
    assert result is True

    # 验证已删除
    video = db.get_author_video(sample_video.video_id)
    assert video is None
```

- [ ] **Step 5: test_按作者查询视频.py**

```python
"""按作者查询视频测试"""
import pytest
from datetime import datetime
from core.service.store import Author


def test_list_videos_by_author(db, sample_video):
    """T1: 按 author_id 列表查询"""
    # 先创建作者
    author = Author(
        id=sample_video.author_id,
        source_author_id="test@finder",
        name="测试作者",
        tag=None,
        bio="简介",
        avatar_url="https://test.jpg",
        cover_img_url=None,
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
    )
    db.create_author(author)

    # 创建多个视频
    for i in range(3):
        video = AuthorVideo(
            video_id=f"video_{i}",
            author_id=sample_video.author_id,
            title=f"视频{i}",
            object_nonce_id=f"nonce_{i}",
            url=f"https://test{i}.mp4",
            spec="xW30",
            file_size=10000000,
            cover_url="https://cover.jpg",
            decode_key=i,
            author_avatar="https://avatar.jpg",
            duration=60,
            create_time="2025-10-20T22:31:40",
        )
        db.create_author_video(video)

    # 按作者查询
    videos = db.list_author_videos(sample_video.author_id)
    assert len(videos) >= 3
```

- [ ] **Step 6: test_幂等性验证.py**

```python
"""幂等性验证测试"""
import pytest
from datetime import datetime
from core.service.store import Author


def test_create_video_idempotent(db, sample_video):
    """T1: 重复创建相同 video_id，验证幂等性"""
    # 先创建作者
    author = Author(
        id=sample_video.author_id,
        source_author_id="test@finder",
        name="测试作者",
        tag=None,
        bio="简介",
        avatar_url="https://test.jpg",
        cover_img_url=None,
        created_at=datetime.now().isoformat(),
        updated_at=datetime.now().isoformat(),
    )
    db.create_author(author)

    # 第一次创建
    result1 = db.create_author_video(sample_video)
    assert result1 is True

    # 第二次创建相同 video_id
    result2 = db.create_author_video(sample_video)
    assert result2 is False

    # 验证数据唯一
    videos = db.list_author_videos(sample_video.author_id)
    assert len(videos) == 1
```

- [ ] **Step 7: 运行作者视频表测试**

Run: `pytest tests/单元测试/数据库/作者视频表/ -v`
Expected: 5 tests passed

---

### Task 4: 任务进度表测试

**Files:**
- Create: `tests/单元测试/数据库/任务进度表/__init__.py`
- Create: `tests/单元测试/数据库/任务进度表/test_创建任务.py`
- Create: `tests/单元测试/数据库/任务进度表/test_查询任务.py`
- Create: `tests/单元测试/数据库/任务进度表/test_更新任务进度.py`
- Create: `tests/单元测试/数据库/任务进度表/test_更新任务状态.py`
- Create: `tests/单元测试/数据库/任务进度表/test_删除任务.py`
- Create: `tests/单元测试/数据库/任务进度表/test_清空任务.py`
- Create: `tests/单元测试/数据库/任务进度表/test_幂等性验证.py`

- [ ] **Step 1: 创建任务进度表目录和 __init__.py**

```python
# tests/单元测试/数据库/任务进度表/__init__.py
"""DownloadTask 表单元测试"""
```

- [ ] **Step 2: test_创建任务.py**

```python
"""创建任务测试"""
import pytest


def test_create_task(db, sample_task):
    """T1: 创建任务，验证字段正确存储"""
    result = db.create_download_task(sample_task)
    assert result is True

    # 查询验证
    task = db.get_download_task(sample_task.task_id)
    assert task is not None
    assert task.title == sample_task.title
    assert task.status == "pending"
    assert task.progress == 0
```

- [ ] **Step 3: test_查询任务.py**

```python
"""查询任务测试"""
import pytest


def test_get_task_by_id(db, sample_task):
    """T1: 按 task_id 查询"""
    db.create_download_task(sample_task)

    task = db.get_download_task(sample_task.task_id)
    assert task is not None
    assert task.task_id == sample_task.task_id


def test_get_task_by_video_id(db, sample_task):
    """T2: 按 video_id 查询"""
    db.create_download_task(sample_task)

    task = db.get_download_task_by_video_id(sample_task.video_id)
    assert task is not None
    assert task.video_id == sample_task.video_id
```

- [ ] **Step 4: test_更新任务进度.py**

```python
"""更新任务进度测试"""
import pytest


def test_update_task_progress(db, sample_task):
    """T1: 更新进度（progress, downloaded, speed）"""
    db.create_download_task(sample_task)

    result = db.update_download_task_progress(
        sample_task.task_id,
        progress=50,
        downloaded=5000000,
        total_size=10000000,
        speed=1234567,
        status="running"
    )
    assert result is True

    # 验证
    task = db.get_download_task(sample_task.task_id)
    assert task.progress == 50
    assert task.downloaded == 5000000
    assert task.speed == 1234567
    assert task.status == "running"
```

- [ ] **Step 5: test_更新任务状态.py**

```python
"""更新任务状态测试"""
import pytest
from datetime import datetime


def test_update_task_status(db, sample_task):
    """T1: 更新状态（status, error_msg, completed_at）"""
    db.create_download_task(sample_task)
    db.update_download_task_progress(
        sample_task.task_id,
        progress=100,
        downloaded=10000000,
        total_size=10000000,
        speed=0,
        status="running"
    )

    # 更新为完成状态
    result = db.update_download_task_status(
        sample_task.task_id,
        status="completed",
        completed_at=datetime.now().isoformat()
    )
    assert result is True

    # 验证
    task = db.get_download_task(sample_task.task_id)
    assert task.status == "completed"
    assert task.completed_at is not None


def test_update_task_status_failed(db, sample_task):
    """T2: 更新为失败状态"""
    db.create_download_task(sample_task)

    result = db.update_download_task_status(
        sample_task.task_id,
        status="failed",
        error_msg="下载失败"
    )
    assert result is True

    # 验证
    task = db.get_download_task(sample_task.task_id)
    assert task.status == "failed"
    assert task.error_msg == "下载失败"
```

- [ ] **Step 6: test_删除任务.py**

```python
"""删除任务测试"""
import pytest


def test_delete_task(db, sample_task):
    """T1: 删除任务"""
    db.create_download_task(sample_task)

    result = db.delete_download_task(sample_task.task_id)
    assert result is True

    # 验证已删除
    task = db.get_download_task(sample_task.task_id)
    assert task is None
```

- [ ] **Step 7: test_清空任务.py**

```python
"""清空任务测试"""
import pytest
from datetime import datetime


def test_clear_tasks(db):
    """T1: 清空所有任务"""
    # 创建多个任务
    for i in range(3):
        task = DownloadTask(
            task_id=f"task_{i}",
            video_id=f"video_{i}",
            url=f"https://test{i}.mp4",
            title=f"视频{i}",
            filename=f"视频{i}",
            spec="xW30",
            suffix=".mp4",
            key=0,
            status="pending",
            progress=0,
            downloaded=0,
            total_size=0,
            speed=0,
            error_msg="",
            created_at=datetime.now().isoformat(),
            updated_at=datetime.now().isoformat(),
            completed_at=None,
        )
        db.create_download_task(task)

    # 清空
    result = db.clear_download_tasks()
    assert result is True

    # 验证
    tasks = db.list_download_tasks()
    assert len(tasks) == 0
```

- [ ] **Step 8: test_幂等性验证.py**

```python
"""幂等性验证测试"""
import pytest


def test_create_task_idempotent(db, sample_task):
    """T1: 重复创建相同 task_id，验证幂等性"""
    # 第一次创建
    result1 = db.create_download_task(sample_task)
    assert result1 is True

    # 第二次创建相同 task_id
    result2 = db.create_download_task(sample_task)
    assert result2 is False

    # 验证数据唯一
    tasks = db.list_download_tasks()
    assert len(tasks) == 1
```

- [ ] **Step 9: 运行任务进度表测试**

Run: `pytest tests/单元测试/数据库/任务进度表/ -v`
Expected: 7 tests passed

---

### Task 5: 运行全部测试

- [ ] **Step 1: 运行全部数据库单元测试**

Run: `pytest tests/单元测试/数据库/ -v --ignore=tests/单元测试/数据库/fixture/`
Expected: 19 tests passed (7 + 5 + 7)

---

**Plan complete.**