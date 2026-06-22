# 前端视频功能单元测试设计

## 概述

使用 jsdom 测试前端视频相关功能，包括：
1. 删除视频
2. 获取某个作者所有视频
3. 获取所有作者所有视频

## 文件结构

```
tests/单元测试/前端/video/
├── 删除视频.js                    # 删除视频测试
├── 获取某个作者所有视频.js         # 获取单个作者视频测试
├── 获取所有作者所有视频.js         # 获取所有作者视频测试
└── fixture/
    └── mockApi.js                 # Mock fetch + 测试数据
```

---

## Fixture 设计

### 测试数据

```javascript
// fixture/mockApi.js

// 单个测试作者
const TEST_AUTHOR = {
  username: 'test_author_001',
  nickname: '测试作者'
};

// 第二个测试作者（用于测试所有作者场景）
const TEST_AUTHOR_2 = {
  username: 'test_author_002',
  nickname: '测试作者2'
};

// 单个作者的视频列表（20个视频，全部待下载状态）
const TEST_VIDEOS_AUTHOR_1 = {};
for (let i = 1; i <= 20; i++) {
  TEST_VIDEOS_AUTHOR_1[`video_001_${i}`] = {
    id: `video_001_${i}`,
    title: `测试视频${i}`,
    downloaded: false,
    createtime: 1713945600 + i * 3600,
    duration: 120,
    size: 10485760,
    cover_url: `https://example.com/cover${i}.jpg`
  };
}

// 第二个作者的视频列表（15个视频，全部待下载状态）
const TEST_VIDEOS_AUTHOR_2 = {};
for (let i = 1; i <= 15; i++) {
  TEST_VIDEOS_AUTHOR_2[`video_002_${i}`] = {
    id: `video_002_${i}`,
    title: `测试作者2视频${i}`,
    downloaded: false,
    createtime: 1713859200 + i * 3600,
    duration: 180,
    size: 20971520,
    cover_url: `https://example.com/author2_cover${i}.jpg`
  };
}

// 单个作者视频数据
const TEST_AUTHOR_VIDEOS_DATA_SINGLE = {
  [TEST_AUTHOR.username]: {
    videos: TEST_VIDEOS_AUTHOR_1
  }
};

// 所有作者视频数据
const TEST_AUTHOR_VIDEOS_DATA_ALL = {
  [TEST_AUTHOR.username]: {
    videos: TEST_VIDEOS_AUTHOR_1
  },
  [TEST_AUTHOR_2.username]: {
    videos: TEST_VIDEOS_AUTHOR_2
  }
};

// Mock fetch 返回单个作者视频数据
function mockFetchAuthorVideosSingle() {
  global.fetch = jest.fn(() =>
    Promise.resolve({
      json: () => Promise.resolve({ authors: TEST_AUTHOR_VIDEOS_DATA_SINGLE })
    })
  );
}

// Mock fetch 返回所有作者视频数据
function mockFetchAuthorVideosAll() {
  global.fetch = jest.fn(() =>
    Promise.resolve({
      json: () => Promise.resolve({ authors: TEST_AUTHOR_VIDEOS_DATA_ALL })
    })
  );
}

// Mock fetch 返回删除成功响应
function mockFetchDeleteSuccess() {
  global.fetch = jest.fn(() =>
    Promise.resolve({
      json: () => Promise.resolve({ success: true, count: 1 })
    })
  );
}

module.exports = {
  TEST_AUTHOR,
  TEST_AUTHOR_2,
  TEST_VIDEOS_AUTHOR_1,
  TEST_VIDEOS_AUTHOR_2,
  TEST_AUTHOR_VIDEOS_DATA_SINGLE,
  TEST_AUTHOR_VIDEOS_DATA_ALL,
  mockFetchAuthorVideosSingle,
  mockFetchAuthorVideosAll,
  mockFetchDeleteSuccess
};
```

---

## 测试1：删除视频

### 验收标准

删除视频后，前端元素中没有这个视频。

### 测试用例

**用例：删除成功后，视频元素从 DOM 中移除**

**准备阶段**
1. 使用 jsdom 创建最小 DOM 结构（包含视频列表容器）
2. 设置全局状态 `_currentAuthor`、`_authorVideosData`
3. 创建视频行 DOM 元素 `<div class="video-row" data-id="video_001_1">`
4. Mock `fetch` 返回成功响应

**执行阶段**
- 调用 `doDeleteSelected(['video_001_1'], false)`

**验证阶段**
- 等待异步操作完成（动画延迟约 300ms）
- 断言 `document.querySelector('.video-row[data-id="video_001_1"]')` 为 `null`

---

## 测试2：获取某个作者所有视频

### 验收标准

1. 数据列表有 N 个视频，DOM 元素显示 N 个视频
2. 所有视频都处于"待下载"状态（`downloaded: false`）

### 测试用例

**用例：获取单个作者的20个视频，DOM 显示20个视频且全部待下载**

**准备阶段**
1. 使用 jsdom 创建 DOM 结构（包含视频列表容器 `#videoList`）
2. 设置全局状态 `_currentAuthor = TEST_AUTHOR`
3. Mock `fetch` 返回单个作者视频数据（20个视频）

**执行阶段**
- 调用 `renderVideoList(Object.values(TEST_VIDEOS_AUTHOR_1))`

**验证阶段**
- 断言 `document.querySelectorAll('.video-row')` 长度为 20
- 断言所有 `.video-status-badge` 元素都有 `pending` 类
- 断言所有 `.video-status-badge` 文本内容为 "待下载"

---

## 测试3：获取所有作者所有视频

### 验收标准

1. 所有作者的视频总数 = DOM 元素显示的视频总数
2. 所有视频都处于"待下载"状态

### 测试用例

**用例：获取所有作者的35个视频（20+15），DOM 显示35个视频且全部待下载**

**准备阶段**
1. 使用 jsdom 创建 DOM 结构（包含视频列表容器 `#videoList`）
2. Mock `fetch` 返回所有作者视频数据（作者1: 20个，作者2: 15个）

**执行阶段**
- 调用 `refreshAuthors()` 或直接渲染所有视频

**验证阶段**
- 断言 `document.querySelectorAll('.video-row')` 长度为 35（20 + 15）
- 断言所有 `.video-status-badge` 元素都有 `pending` 类
- 断言所有 `.video-status-badge` 文本内容为 "待下载"

---

## 依赖

- `jest` + `jest-environment-jsdom`
- 从 `app.js` 提取或复制相关函数到可测试模块：
  - `doDeleteSelected`
  - `renderVideoList`
  - `refreshAuthors`

## 注意事项

- 删除操作有 250ms 动画延迟，测试需使用 `jest.useFakeTimers()` 或适当等待
- 需要注入全局状态 `_currentAuthor` 和 `_authorVideosData`
- 视频状态在 DOM 中表现为 `<span class="video-status-badge pending">待下载</span>`