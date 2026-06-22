# 开屏弹窗模块实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现应用启动时显示打赏/引流弹窗，展示二维码图片

**Architecture:** 基类 QRCodeSource + 子类继承（Local/Http/OSS），前端硬编码标题说明，后端提供图片 URL

**Tech Stack:** Python FastAPI, JavaScript, Win11 Fluent Design

---

## 文件结构

```
core/
├── service/leader.py          # 弹窗业务逻辑
├── api/routers/leader.py      # API 路由
└── utils/qrcode_source.py     # 二维码来源基类+子类

static/
├── leader/2wm.jpg             # 已存在
└── js/component/splash.js     # 前端弹窗组件
```

---

### Task 1: 二维码来源基类与子类

**Files:**
- Create: `core/utils/qrcode_source.py`

- [ ] **Step 1: 创建 QRCodeSource 基类与子类**

```python
"""二维码图片来源 - 支持本地/HTTP/OSS多种来源"""

from abc import ABC, abstractmethod
from pathlib import Path


class QRCodeSource(ABC):
    """二维码图片来源基类"""

    @abstractmethod
    def get_url(self) -> str:
        """获取二维码图片URL（前端可访问）"""
        pass

    @abstractmethod
    def get_type(self) -> str:
        """获取类型标识：local / http / oss"""
        pass


class LocalQRCodeSource(QRCodeSource):
    """本地文件来源"""

    def __init__(self, url: str = "/static/leader/2wm.jpg"):
        self._url = url

    def get_url(self) -> str:
        return self._url

    def get_type(self) -> str:
        return "local"


class HttpQRCodeSource(QRCodeSource):
    """HTTP静态资源来源"""

    def __init__(self, url: str):
        self._url = url

    def get_url(self) -> str:
        return self._url

    def get_type(self) -> str:
        return "http"


class OSSQRCodeSource(QRCodeSource):
    """阿里云OSS来源"""

    def __init__(self, url: str):
        self._url = url

    def get_url(self) -> str:
        return self._url

    def get_type(self) -> str:
        return "oss"


def get_qrcode_source(source_type: str = "local", url: str = None) -> QRCodeSource:
    """工厂函数：根据类型创建对应的来源实例"""
    if source_type == "local":
        return LocalQRCodeSource(url or "/static/leader/2wm.jpg")
    elif source_type == "http":
        return HttpQRCodeSource(url)
    elif source_type == "oss":
        return OSSQRCodeSource(url)
    else:
        return LocalQRCodeSource()
```

- [ ] **Step 2: 提交代码**

```bash
git add core/utils/qrcode_source.py
git commit -m "feat: 添加二维码来源基类与子类（local/http/oss）"
```

---

### Task 2: 弹窗业务逻辑

**Files:**
- Modify: `core/service/leader.py`

- [ ] **Step 1: 实现弹窗配置服务**

```python
"""开屏弹窗业务逻辑"""

from core.utils.qrcode_source import get_qrcode_source


class SplashService:
    """开屏弹窗服务"""

    def __init__(self, source_type: str = "local", url: str = None):
        self._source = get_qrcode_source(source_type, url)

    def get_splash_config(self) -> dict:
        """获取弹窗配置"""
        return {
            "show": True,
            "qrcode_url": self._source.get_url(),
            "source_type": self._source.get_type(),
        }


# 默认实例：使用本地图片
splash_service = SplashService(source_type="local")
```

- [ ] **Step 2: 提交代码**

```bash
git add core/service/leader.py
git commit -m "feat: 添加开屏弹窗服务 SplashService"
```

---

### Task 3: API 路由

**Files:**
- Modify: `core/api/routers/leader.py`

- [ ] **Step 1: 实现弹窗 API**

```python
"""开屏弹窗 API 路由"""

from fastapi import APIRouter

from core.service.leader import splash_service

router = APIRouter(prefix="/api/leader", tags=["leader"])


@router.get("/splash")
def get_splash():
    """获取开屏弹窗配置"""
    config = splash_service.get_splash_config()
    return {"code": 0, "data": config}
```

- [ ] **Step 2: 在 app.py 中注册路由**

在 `core/api/app.py` 中添加：
```python
from core.api.routers import leader
app.include_router(leader.router)
```

- [ ] **Step 3: 提交代码**

```bash
git add core/api/routers/leader.py core/api/app.py
git commit -m "feat: 添加开屏弹窗 API /api/leader/splash"
```

---

### Task 4: 前端弹窗组件

**Files:**
- Create: `static/js/component/splash.js`

- [ ] **Step 1: 实现弹窗组件**

```javascript
// 开屏弹窗组件

/**
 * 显示开屏弹窗
 */
function showSplashDialog(config) {
  if (!config || !config.show) return;

  const overlay = document.createElement('div');
  overlay.className = 'splash-overlay';
  overlay.innerHTML = `
    <div class="splash-dialog">
      <img class="splash-qrcode" src="${config.qrcode_url}" alt="二维码">
      <div class="splash-title">关注公众号</div>
      <div class="splash-desc">扫码关注，获取最新更新与技术分享</div>
      <button class="splash-close" id="splashClose">关闭</button>
    </div>
  `;

  document.body.appendChild(overlay);

  // 点击关闭按钮
  overlay.querySelector('#splashClose').addEventListener('click', () => {
    overlay.remove();
  });

  // 点击遮罩层关闭
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) {
      overlay.remove();
    }
  });
}

/**
 * 加载并显示开屏弹窗
 */
function loadSplash() {
  fetch('/api/leader/splash')
    .then(r => r.json())
    .then(data => {
      if (data.code === 0 && data.data) {
        showSplashDialog(data.data);
      }
    })
    .catch(err => {
      console.error('[Splash] 加载失败:', err);
    });
}
```

- [ ] **Step 2: 提交代码**

```bash
git add static/js/component/splash.js
git commit -m "feat: 添加开屏弹窗前端组件"
```

---

### Task 5: CSS 样式

**Files:**
- Modify: `static/css/styles.css`

- [ ] **Step 1: 添加弹窗样式**

```css
/* =========================================
   Splash Dialog - 开屏弹窗
   ========================================= */

.splash-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.4);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  animation: fadeIn 0.2s ease;
}

@keyframes fadeIn {
  from { opacity: 0; }
  to { opacity: 1; }
}

.splash-dialog {
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(20px);
  border-radius: 12px;
  padding: 32px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.15);
  max-width: 320px;
  animation: slideUp 0.3s ease;
}

@keyframes slideUp {
  from { 
    opacity: 0;
    transform: translateY(20px);
  }
  to { 
    opacity: 1;
    transform: translateY(0);
  }
}

.splash-qrcode {
  width: 200px;
  height: 200px;
  object-fit: contain;
  border-radius: 8px;
}

.splash-title {
  font-size: 18px;
  font-weight: 600;
  color: var(--text);
}

.splash-desc {
  font-size: 14px;
  color: var(--text-secondary);
  text-align: center;
}

.splash-close {
  padding: 10px 32px;
  background: var(--accent);
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
}

.splash-close:hover {
  background: var(--accent-hover);
}
```

- [ ] **Step 2: 提交代码**

```bash
git add static/css/styles.css
git commit -m "feat: 添加开屏弹窗样式（Win11 Fluent Design）"
```

---

### Task 6: 集成到应用启动

**Files:**
- Modify: `static/index.html`
- Modify: `static/js/app.js`

- [ ] **Step 1: 在 index.html 中引入 splash.js**

在 `<head>` 中添加：
```html
<script src="/static/js/component/splash.js"></script>
```

- [ ] **Step 2: 在 app.js 初始化时调用弹窗**

在 `initApp()` 函数末尾添加：
```javascript
// 显示开屏弹窗
loadSplash();
```

- [ ] **Step 3: 提交代码**

```bash
git add static/index.html static/js/app.js
git commit -m "feat: 应用启动时显示开屏弹窗"
```

---

### Task 7: 验证测试

- [ ] **Step 1: 启动应用验证弹窗显示**

```bash
# 启动应用
python gui.py
```

验证点：
- 应用启动时显示弹窗
- 二维码图片正常加载
- 标题和说明文字正确
- 点击关闭按钮可关闭
- 点击遮罩层可关闭

- [ ] **Step 2: 提交验证**

```bash
git add -A
git commit -m "test: 验证开屏弹窗功能正常"
```
