# 错误状态追踪与前端展示设计文档

## 概述

本文档描述下载任务错误状态的完整数据流，以及前端如何展示失败状态和错误信息。

---

## 1. 当前问题分析

### 1.1 错误信息数据流断裂点

```
Go 后端 → socket_client.py → task.py → database → SSE → 前端
   ✅          ✅               ❌         ✅        ✅      ❌
```

| 环节 | 当前状态 | 问题 |
|------|----------|------|
| Go 后端返回 | ✅ 正常 | 返回 `error` 字段（可能为空字符串） |
| socket_client.py | ✅ 正常 | 已提取 `error_msg` 到标准化数据 |
| task.py | ❌ 断裂 | 调用 `update_download_task_status` 时未传递 `error_msg` |
| database | ✅ 支持 | `download_task` 表有 `error_msg` 字段，DAO 支持写入 |
| SSE 转发 | ✅ 正常 | 已转发 `error_msg` 到前端 |
| 前端展示 | ❌ 缺失 | 无错误状态 UI，无错误信息展示 |

### 1.2 根本原因

1. **后端未持久化错误信息**: `core/service/task.py` 第 225 行调用 `update_download_task_status` 时未传递 `error_msg` 参数
2. **前端无错误状态展示**: `videoListRender.js` 的 `updateSingleVideoError()` 仅恢复为"待下载"，不显示错误原因
3. **CSS 缺少错误样式**: `styles.css` 无 `.error` 或 `.failed` 徽章样式

---

## 2. 数据流修复方案

### 2.1 后端修复：持久化错误信息

**文件**: `core/service/task.py`

**修改位置**: `_handle_task_progress` 函数中调用 `update_download_task_status` 处

**修改内容**:

```python
# 修改前（约第 225 行）
self.db.update_download_task_status(
    task_id=task_id,
    status=status
)

# 修改后
self.db.update_download_task_status(
    task_id=task_id,
    status=status,
    error_msg=normalized.get("error_msg", "") if status == "error" else None
)
```

**说明**:
- 仅当 `status == "error"` 时传递 `error_msg`
- 其他状态传递 `None`，避免覆盖历史错误信息

### 2.2 SSE 转发：已实现

**文件**: `core/api/routers/sse.py`

**当前状态**: ✅ 已在 `_transform_task_progress` 中转发 `error_msg`

```python
return json.dumps({
    "id": task_id,
    "video_id": video_id,
    "status": status,
    "downloaded": payload.get("downloaded", 0),
    "speed": payload.get("speed", 0),
    "total_size": payload.get("total_size", 0),
    "download_path": download_path,
    "error_msg": payload.get("error_msg", ""),  # ✅ 已实现
}, ensure_ascii=False)
```

### 2.3 socket_client 标准化：已实现

**文件**: `core/utils/socket_client.py`

**当前状态**: ✅ 已在 `_normalize_task` 中提取 `error_msg`

```python
normalized = {
    "id": task.get("id"),
    "video_id": video_id,
    "status": task.get("status"),
    ...
    "error_msg": task.get("error", ""),  # ✅ 已实现
}
```

---

## 3. 前端展示方案

### 3.1 错误状态徽章样式

**文件**: `static/css/styles.css`

**新增样式**:

```css
/* 错误状态徽章 */
.video-status-badge.error {
    background-color: #fee2e2;
    color: #dc2626;
    border: 1px solid #fecaca;
}

.video-status-badge.error:hover {
    background-color: #fecaca;
}

/* 错误信息提示框 */
.video-error-tooltip {
    position: absolute;
    background: #1f2937;
    color: #f9fafb;
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 12px;
    max-width: 300px;
    z-index: 1000;
    box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
    margin-top: 4px;
}
```

### 3.2 错误状态 UI 更新

**文件**: `static/js/component/videoListRender.js`

**修改函数**: `updateSingleVideoError(videoId)`

**修改内容**:

```javascript
/**
 * 更新视频行为错误状态
 * @param {string} videoId - 视频 ID
 * @param {string} errorMsg - 错误信息（可选）
 */
function updateSingleVideoError(videoId, errorMsg) {
    var row = document.querySelector('.video-row[data-id="' + videoId + '"]');
    if (!row) return;

    var badge = row.querySelector('.video-status-badge');
    if (!badge) return;

    // 切换为错误状态
    badge.className = 'video-status-badge error';
    badge.textContent = '下载失败';

    // 存储错误信息到 data 属性
    if (errorMsg) {
        badge.setAttribute('data-error', errorMsg);

        // 添加 hover 提示
        badge.setAttribute('title', '点击查看错误详情');
        badge.style.cursor = 'pointer';

        // 移除旧的事件监听器（避免重复）
        badge.removeEventListener('click', _showErrorTooltip);

        // 添加点击事件显示错误详情
        badge.addEventListener('click', function(e) {
            e.stopPropagation();
            _showErrorTooltip(badge, errorMsg);
        });
    }

    // 移除进度条（如果存在）
    var progressBar = row.querySelector('.video-progress-bar');
    if (progressBar) {
        progressBar.remove();
    }
}

/**
 * 显示错误信息提示框
 * @param {HTMLElement} badge - 徽章元素
 * @param {string} errorMsg - 错误信息
 */
function _showErrorTooltip(badge, errorMsg) {
    // 移除已存在的提示框
    var existingTooltip = document.querySelector('.video-error-tooltip');
    if (existingTooltip) {
        existingTooltip.remove();
    }

    // 创建提示框
    var tooltip = document.createElement('div');
    tooltip.className = 'video-error-tooltip';
    tooltip.textContent = errorMsg || '下载失败，请重试';

    // 定位到徽章下方
    var rect = badge.getBoundingClientRect();
    tooltip.style.position = 'fixed';
    tooltip.style.left = rect.left + 'px';
    tooltip.style.top = (rect.bottom + 4) + 'px';

    document.body.appendChild(tooltip);

    // 点击其他区域关闭
    setTimeout(function() {
        document.addEventListener('click', function closeTooltip(e) {
            if (!tooltip.contains(e.target) && e.target !== badge) {
                tooltip.remove();
                document.removeEventListener('click', closeTooltip);
            }
        });
    }, 10);
}
```

### 3.3 SSE 进度处理更新

**文件**: `static/js/datahandle/authorDetail.js`

**修改函数**: `handleSSETaskProgress(data)`

**修改位置**: `status === 'error'` 分支

**修改内容**:

```javascript
// 修改前
if (status === 'done' || status === 'error') {
    _activeTasks = _activeTasks.filter(t => t.id !== taskId);

    if (status === 'done') {
        // ... 已下载处理
    } else {
        // 错误状态：恢复为"待下载"
        updateSingleVideoError(videoId);
    }
    // ...
}

// 修改后
if (status === 'done' || status === 'error') {
    _activeTasks = _activeTasks.filter(t => t.id !== taskId);

    if (status === 'done') {
        // ... 已下载处理
    } else {
        // 错误状态：显示错误信息
        var errorMsg = data.error_msg || '下载失败，请重试';
        console.error('[SSE][数据层] 任务错误: videoId=%s, errorMsg=%s', videoId, errorMsg);
        updateSingleVideoError(videoId, errorMsg);
    }
    // ...
}
```

---

## 4. 数据库字段说明

### 4.1 download_task 表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER | 主键 |
| task_id | TEXT | Go 后端任务 ID |
| video_id | TEXT | 视频 ID |
| status | TEXT | 任务状态：pending, running, done, error |
| error_msg | TEXT | 错误信息（仅 status=error 时有值） |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

### 4.2 DAO 方法

**文件**: `core/utils/database/crud/task_dao.py`

**方法**: `update_status(task_id, status, error_msg=None)`

```python
def update_status(self, task_id: str, status: str, error_msg: str = None) -> bool:
    """更新任务状态

    Args:
        task_id: 任务 ID
        status: 新状态
        error_msg: 错误信息（可选）

    Returns:
        是否更新成功
    """
```

---

## 5. 错误信息来源

### 5.1 Go 后端返回的错误

Go 后端在任务失败时返回 `error` 字段：

```json
{
  "type": "event",
  "data": {
    "task": {
      "id": "task_xxx",
      "status": "error",
      "error": "文件名包含非法字符",
      ...
    }
  }
}
```

### 5.2 常见错误类型

| 错误信息 | 原因 | 解决方案 |
|----------|------|----------|
| 文件名包含非法字符 | 标题包含 `\n\r\t` 等 | 已修复 `safe_title` 正则 |
| URL 已存在 | 任务重复 | 提示用户该视频已下载 |
| 网络超时 | 下载过程中断 | 自动重试或提示用户 |
| 存储空间不足 | 磁盘满 | 提示用户清理空间 |

---

## 6. 实现清单

### 6.1 后端修改

- [ ] `core/service/task.py`: 传递 `error_msg` 到 `update_download_task_status`

### 6.2 前端修改

- [ ] `static/css/styles.css`: 添加 `.error` 徽章样式和错误提示框样式
- [ ] `static/js/component/videoListRender.js`: 修改 `updateSingleVideoError()` 支持错误信息展示
- [ ] `static/js/datahandle/authorDetail.js`: 修改 `handleSSETaskProgress()` 传递错误信息

### 6.3 测试验证

- [ ] 模拟错误状态，验证数据库写入 `error_msg`
- [ ] 验证 SSE 转发 `error_msg`
- [ ] 验证前端显示错误徽章和提示框
- [ ] 验证点击错误徽章显示详细信息

---

## 7. 调试日志

### 7.1 后端日志

```
[socket_client] 标准化任务: id=task_xxx, status=error, error_msg="文件名包含非法字符"
[task] 更新任务状态: task_id=task_xxx, status=error, error_msg="文件名包含非法字符"
[SSE] task_progress: id=task_xxx, video_id=xxx, status=error, error_msg="文件名包含非法字符"
```

### 7.2 前端日志

```
[SSE][数据层] 任务错误: videoId=xxx, errorMsg=文件名包含非法字符
[SSE][渲染层] 更新视频行错误状态: id=xxx, error=文件名包含非法字符
```

---

## 8. 注意事项

1. **错误信息持久化**: 仅在 `status == "error"` 时写入，避免覆盖历史错误
2. **前端兼容性**: 旧版本前端不显示错误信息，但不影响功能
3. **用户体验**: 错误信息应简洁明了，避免技术术语
4. **国际化**: 未来支持多语言时，错误信息需要翻译
