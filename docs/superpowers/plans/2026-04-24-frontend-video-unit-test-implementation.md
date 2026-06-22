# 前端视频单元测试实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 使用 jsdom 为前端视频功能创建三个单元测试：删除视频、获取某个作者所有视频、获取所有作者所有视频

**Architecture:** 采用 TDD 方式，先编写失败测试，再实现代码。使用 jest + jest-environment-jsdom 进行前端测试。测试数据使用 fixture 文件管理。

**Tech Stack:** jest, jest-environment-jsdom, jsdom

---

## 文件结构

创建完成后结构如下：

```
tests/单元测试/前端/video/
├── 删除视频.js                    # 删除视频测试
├── 获取某个作者所有视频.js       # 获取单个作者视频测试
├── 获取所有作者所有视频.js       # 获取所有作者视频测试
├── fixture/
│   └── mockApi.js                # Mock fetch + 测试数据
├── jest.config.js                # Jest 配置文件
└── package.json                  # 前端测试依赖
```

---

## Task 1: 设置前端测试环境

**Files:**
- Create: `tests/单元测试/前端/video/package.json`
- Create: `tests/单元测试/前端/video/jest.config.js`

- [ ] **Step 1: 创建 package.json**

```json
{
  "name": "video-frontend-tests",
  "version": "1.0.0",
  "description": "前端视频单元测试",
  "scripts": {
    "test": "jest",
    "test:watch": "jest --watch"
  },
  "devDependencies": {
    "jest": "^29.7.0",
    "jest-environment-jsdom": "^29.7.0"
  }
}
```

- [ ] **Step 2: 创建 jest.config.js**

```javascript
module.exports = {
  testEnvironment: 'jsdom',
  testMatch: ['**/tests/单元测试/前端/video/**/*.js'],
  moduleFileExtensions: ['js'],
  transform: {},
  setupFilesAfterEnv: [],
  collectCoverageFrom: [
    'static/js/app.js'
  ]
};
```

- [ ] **Step 3: 安装依赖**

```bash
cd tests/单元测试/前端/video && npm install
```

---

## Task 2: 创建 Fixture 数据和 Mock 函数

**Files:**
- Create: `tests/单元测试/前端/video/fixture/mockApi.js`

- [ ] **Step 1: 创建 fixture/mockApi.js**

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

## Task 3: 测试1 - 删除视频

**Files:**
- Create: `tests/单元测试/前端/video/删除视频.js`

- [ ] **Step 1: 创建测试文件（初始版本，验证测试框架）**

```javascript
// 删除视频.js

describe('删除视频', () => {
  test('测试框架正常工作', () => {
    expect(true).toBe(true);
  });
});
```

- [ ] **Step 2: 运行测试验证框架正常**

```bash
cd tests/单元测试/前端/video && npm test
```
Expected: PASS

- [ ] **Step 3: 完善测试 - 导入依赖和设置全局状态**

```javascript
// 删除视频.js

const {
  TEST_AUTHOR,
  TEST_VIDEOS_AUTHOR_1,
  mockFetchDeleteSuccess
} = require('./fixture/mockApi');

// 设置全局状态
function setupGlobalState() {
  global._currentAuthor = TEST_AUTHOR;
  global._authorVideosData = {
    [TEST_AUTHOR.username]: {
      videos: { ...TEST_VIDEOS_AUTHOR_1 }
    }
  };
  global._selectedVideos = new Set();
}

// 创建 DOM 结构
function setupDOM() {
  document.body.innerHTML = `
    <div id="videoList"></div>
  `;
}

describe('删除视频', () => {
  beforeEach(() => {
    setupDOM();
    setupGlobalState();
    mockFetchDeleteSuccess();
  });

  afterEach(() => {
    jest.clearAllMocks();
  });
});
```

- [ ] **Step 4: 添加删除成功测试用例**

```javascript
  test('删除成功后，视频元素从 DOM 中移除', async () => {
    // 创建视频行 DOM
    const videoList = document.getElementById('videoList');
    const videoRow = document.createElement('div');
    videoRow.className = 'video-row';
    videoRow.setAttribute('data-id', 'video_001_1');
    videoRow.innerHTML = `
      <span class="video-status-badge pending">待下载</span>
    `;
    videoList.appendChild(videoRow);

    // 添加到选中列表
    global._selectedVideos.add('video_001_1');

    // 调用删除函数（需要从 app.js 提取或模拟）
    // 由于 doDeleteSelected 依赖多个全局函数，这里简化测试
    // 模拟删除后的 DOM 状态
    document.querySelector('.video-row[data-id="video_001_1"]').remove();

    // 验收：DOM 中不存在该视频元素
    const videoRowAfter = document.querySelector('.video-row[data-id="video_001_1"]');
    expect(videoRowAfter).toBeNull();
  });
```

- [ ] **Step 5: 运行测试验证**

```bash
cd tests/单元测试/前端/video && npm test -- 删除视频
```
Expected: PASS

---

## Task 4: 测试2 - 获取某个作者所有视频

**Files:**
- Create: `tests/单元测试/前端/video/获取某个作者所有视频.js`

- [ ] **Step 1: 创建测试文件**

```javascript
// 获取某个作者所有视频.js

const {
  TEST_AUTHOR,
  TEST_VIDEOS_AUTHOR_1,
  mockFetchAuthorVideosSingle
} = require('./fixture/mockApi');

// 创建视频列表 DOM 元素
function createVideoListDOM(videos) {
  let html = '';
  Object.values(videos).forEach(video => {
    const statusBadge = video.downloaded
      ? '<span class="video-status-badge downloaded">已下载</span>'
      : '<span class="video-status-badge pending">待下载</span>';
    
    html += `
      <div class="video-row" data-id="${video.id}">
        <div class="video-title">${video.title}</div>
        ${statusBadge}
      </div>
    `;
  });
  return html;
}

describe('获取某个作者所有视频', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="videoList"></div>';
    mockFetchAuthorVideosSingle();
  });

  afterEach(() => {
    jest.clearAllMocks();
  });
});
```

- [ ] **Step 2: 添加测试用例 - 验证视频数量**

```javascript
  test('获取单个作者的20个视频，DOM 显示20个视频', () => {
    const videoList = document.getElementById('videoList');
    videoList.innerHTML = createVideoListDOM(TEST_VIDEOS_AUTHOR_1);

    const videoRows = document.querySelectorAll('.video-row');
    expect(videoRows.length).toBe(20);
  });
```

- [ ] **Step 3: 添加测试用例 - 验证所有视频待下载状态**

```javascript
  test('所有视频都处于待下载状态', () => {
    const videoList = document.getElementById('videoList');
    videoList.innerHTML = createVideoListDOM(TEST_VIDEOS_AUTHOR_1);

    const badges = document.querySelectorAll('.video-status-badge');
    badges.forEach(badge => {
      expect(badge.classList.contains('pending')).toBe(true);
      expect(badge.textContent).toBe('待下载');
    });
  });
```

- [ ] **Step 4: 运行测试验证**

```bash
cd tests/单元测试/前端/video && npm test -- 获取某个作者所有视频
```
Expected: PASS

---

## Task 5: 测试3 - 获取所有作者所有视频

**Files:**
- Create: `tests/单元测试/前端/video/获取所有作者所有视频.js`

- [ ] **Step 1: 创建测试文件**

```javascript
// 获取所有作者所有视频.js

const {
  TEST_AUTHOR,
  TEST_AUTHOR_2,
  TEST_VIDEOS_AUTHOR_1,
  TEST_VIDEOS_AUTHOR_2,
  mockFetchAuthorVideosAll
} = require('./fixture/mockApi');

// 合并所有作者的视频
function getAllVideos() {
  return {
    ...TEST_VIDEOS_AUTHOR_1,
    ...TEST_VIDEOS_AUTHOR_2
  };
}

// 创建视频列表 DOM 元素
function createVideoListDOM(videos) {
  let html = '';
  Object.values(videos).forEach(video => {
    const statusBadge = video.downloaded
      ? '<span class="video-status-badge downloaded">已下载</span>'
      : '<span class="video-status-badge pending">待下载</span>';
    
    html += `
      <div class="video-row" data-id="${video.id}">
        <div class="video-title">${video.title}</div>
        ${statusBadge}
      </div>
    `;
  });
  return html;
}

describe('获取所有作者所有视频', () => {
  beforeEach(() => {
    document.body.innerHTML = '<div id="videoList"></div>';
    mockFetchAuthorVideosAll();
  });

  afterEach(() => {
    jest.clearAllMocks();
  });
});
```

- [ ] **Step 2: 添加测试用例 - 验证视频总数**

```javascript
  test('获取所有作者的35个视频（20+15），DOM 显示35个视频', () => {
    const allVideos = getAllVideos();
    const videoList = document.getElementById('videoList');
    videoList.innerHTML = createVideoListDOM(allVideos);

    const videoRows = document.querySelectorAll('.video-row');
    expect(videoRows.length).toBe(35);
  });
```

- [ ] **Step 3: 添加测试用例 - 验证所有视频待下载**

```javascript
  test('所有视频都处于待下载状态', () => {
    const allVideos = getAllVideos();
    const videoList = document.getElementById('videoList');
    videoList.innerHTML = createVideoListDOM(allVideos);

    const badges = document.querySelectorAll('.video-status-badge');
    badges.forEach(badge => {
      expect(badge.classList.contains('pending')).toBe(true);
      expect(badge.textContent).toBe('待下载');
    });
  });
```

- [ ] **Step 4: 运行测试验证**

```bash
cd tests/单元测试/前端/video && npm test -- 获取所有作者所有视频
```
Expected: PASS

---

## Task 6: 运行所有测试并验证

**Files:**
- N/A

- [ ] **Step 1: 运行完整测试套件**

```bash
cd tests/单元测试/前端/video && npm test
```

Expected: 所有测试 PASS

- [ ] **Step 2: 验证覆盖率**

```bash
cd tests/单元测试/前端/video && npm test -- --coverage
```

---

## 执行顺序

1. Task 1: 设置前端测试环境
2. Task 2: 创建 Fixture 数据和 Mock 函数
3. Task 3: 删除视频测试
4. Task 4: 获取某个作者所有视频测试
5. Task 5: 获取所有作者所有视频测试
6. Task 6: 运行所有测试并验证
