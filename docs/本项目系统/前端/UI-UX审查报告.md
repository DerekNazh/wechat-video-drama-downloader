# 视频号监控台 UI/UX 审查报告

> 审查日期: 2026-05-26
> 设计系统: Windows 11 Fluent Design (Light Only)
> 技术栈: Vanilla JS + CSS Custom Properties + HTML5

---

## 一、严重问题 (Critical)

### 1.1 不存在的 CSS 变量引用

多处代码使用 `var(--text-primary)`，但 `:root` 中定义的是 `--text`（无 `--text-primary`）。

**影响**: 浏览器回退到 inherited 值，行为不可预测。

**受影响位置**:
- `.home-search-input`
- `.import-card-title`
- `.tencent-doc-form input`
- 其他多处

**修复方案**: 统一为 `var(--text)` 或在 `:root` 中补充 `--text-primary: var(--text)` 别名。

### 1.2 `.btn-danger` 未使用设计变量

`background: #dc3545` 硬编码，与 `--danger: #D13438` 不一致。`border-radius: 6px` 绕过了 `--radius` (8px)。

**影响**: 风格不统一，危险操作按钮颜色与设计系统脱节。

**修复方案**:
```css
.btn-danger {
  background: var(--danger);
  border-radius: var(--radius);
}
```

### 1.3 作者网格无响应式列数

`grid-template-columns: repeat(3, 1fr)` 在 600px 以下仍为 3 列，卡片极度挤压。

**影响**: 小屏用户体验极差，卡片内容被压扁。

**修复方案**: 添加响应式断点:
```css
@media (max-width: 900px) {
  .author-grid { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 600px) {
  .author-grid { grid-template-columns: 1fr; }
}
```

### 1.4 无暗色模式

所有 CSS 变量硬编码为亮色值，无 `prefers-color-scheme: dark` 适配。

**影响**: 夜间使用时眼睛疲劳，不符合当前主流应用期望。

**修复方案**: 添加 `prefers-color-scheme: dark` 变量覆盖，或在设置页提供手动切换。

---

## 二、中等问题 (Medium)

### 2.1 基础按钮缺少 hover 过渡

`.btn-primary` / `.btn-secondary` hover 时背景色突变，无过渡动画。`.btn-monitor` 有 transition 但基础按钮没有。

**修复方案**:
```css
.btn-primary, .btn-secondary {
  transition: background var(--transition), box-shadow var(--transition);
}
```

### 2.2 import-card hover 颜色硬编码

CSV `#4784ff`、Excel `#1d8a5e`、腾讯文档 `#e8862a` 未定义为变量，与设计系统脱节。

**修复方案**: 在 `:root` 中定义品牌色变量:
```css
--brand-csv: #4784ff;
--brand-excel: #1d8a5e;
--brand-tencent: #e8862a;
```

### 2.3 字号粒度过细，缺乏阶梯体系

从 9px 到 48px 共约 20+ 种不同字号，缺乏系统化的字号阶梯。

**当前字号分布** (不完全统计):
- 9px, 10px, 11px, 12px, 13px, 14px, 15px, 16px, 18px, 20px, 24px, 32px, 48px

**修复方案**: 定义字号阶梯变量:
```css
--text-xs: 10px;
--text-sm: 12px;
--text-base: 14px;
--text-lg: 16px;
--text-xl: 20px;
--text-2xl: 24px;
--text-hero: 32px;
```

### 2.4 loading-logo 图片尺寸过大

`width: 550px; height: 200px`，在小屏会溢出。

**修复方案**:
```css
.loading-logo img {
  max-width: 100%;
  width: min(550px, 80vw);
  height: auto;
}
```

### 2.5 按钮圆角不一致

- `.btn-danger`: 6px
- `.btn-primary`: `var(--radius)` = 8px
- `.author-progress-bar`: 4px
- `.tencent-doc-form input`: 12px

**修复方案**: 全部统一使用 `var(--radius)` 或 `var(--radius-sm)` / `var(--radius-lg)`。

---

## 三、轻微问题 (Minor)

### 3.1 交错动画仅覆盖前 10 项

`.author-list-item:nth-child(n+11)` 统一 250ms delay，大量数据时无渐入效果。

**修复方案**: 使用 JS 动态计算 delay，或限制为前 20 项。

### 3.2 `color-mix()` 兼容性

`.video-type-tab:hover` 使用 `color-mix(in srgb, ...)`，旧 Edge 不支持。Win11 环境下可接受，但非 Win11 环境可能有问题。

### 3.3 无 `prefers-reduced-motion` 支持

大量动画（badge-in、row-in、shimmer、breathe、pulse-bar、progress-shine）无 `prefers-reduced-motion` 回退。

**修复方案**:
```css
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after {
    animation-duration: 0.01ms !important;
    animation-iteration-count: 1 !important;
    transition-duration: 0.01ms !important;
  }
}
```

### 3.4 无 `:focus-visible` 样式

当前只有 `:focus` 样式（鼠标点击也显示 focus ring），应改用 `:focus-visible` 让键盘导航才显示。

---

## 四、设计系统改进建议

### 4.1 推荐配色方案 (基于 ui-ux-pro-max 分析)

当前 Win11 Light 配色较保守，建议增加暗色模式支持:

**Light (当前)**:
| 变量 | 当前值 | 建议 |
|------|--------|------|
| --bg | #F3F3F3 | 保持 |
| --surface | #FFFFFF | 保持 |
| --accent | #0078D4 | 保持 (Win11 蓝) |

**Dark (新增)**:
| 变量 | 值 | 说明 |
|------|-----|------|
| --bg | #0F0F23 | 深蓝黑 |
| --surface | #1A1A2E | 卡片背景 |
| --text | #F8FAFC | 高对比白 |
| --text-secondary | #94A3B8 | 次文本灰 |
| --accent | #0078D4 | 保持蓝色 |
| --border | #2A2A3E | 深色边框 |

### 4.2 推荐字体方案

当前依赖系统字体 `'Segoe UI Variable'`，Win11 上效果好但其他平台退化严重。

**建议**: 引入 Fira Sans 作为跨平台回退:
```css
@import url('https://fonts.googleapis.com/css2?family=Fira+Sans:wght@300;400;500;600;700&display=swap');

body {
  font-family: 'Fira Sans', 'Segoe UI Variable', 'Segoe UI', system-ui, sans-serif;
}
```

Fira Sans 风格: dashboard、数据、精确，适合监控台场景。

### 4.3 间距体系建议

当前间距随意使用 (4px, 6px, 8px, 12px, 16px, 24px 等)，建议定义阶梯:

```css
--space-1: 4px;
--space-2: 8px;
--space-3: 12px;
--space-4: 16px;
--space-5: 24px;
--space-6: 32px;
--space-8: 48px;
```

### 4.4 Z-Index 体系建议

当前 z-index 使用混乱 (1, 2, 5, 10, 100, 200, 1000, 2000)。

**建议定义**:
```css
--z-base: 1;
--z-dropdown: 10;
--z-sticky: 50;
--z-overlay: 100;
--z-modal: 200;
--z-toast: 500;
--z-loading: 1000;
```

---

## 五、交互体验改进建议

### 5.1 下载进度框

**行模式**: 已优化为紧凑设计 (min-width 120px, 4px 进度条)

**网格模式**: 已优化为底部渐变覆盖设计

**建议**: 增加进度完成时的微动画 (scale pulse)，让用户感知"完成"。

### 5.2 视图模式独立性

已实现作者列表和视频列表视图模式独立，各自保存到 localStorage。

### 5.3 Tab 数量标注

已移除，保持简洁。

### 5.4 视频规格选择

已修改为优先压缩规格 (xWT111)，迫不得已才用 original。

---

## 六、优先级排序

| 优先级 | 问题 | 工作量 | 影响 |
|--------|------|--------|------|
| P0 | 不存在的 CSS 变量 | 小 | 视觉异常 |
| P0 | `.btn-danger` 未用设计变量 | 小 | 风格不统一 |
| P1 | 作者网格响应式 | 小 | 小屏崩溃 |
| P1 | 基础按钮缺少 transition | 小 | 交互卡顿感 |
| P1 | `prefers-reduced-motion` | 小 | 无障碍合规 |
| P2 | 暗色模式 | 大 | 夜间体验 |
| P2 | 字号阶梯体系 | 中 | 设计一致性 |
| P2 | 间距体系 | 中 | 设计一致性 |
| P2 | z-index 体系 | 小 | 代码可维护性 |
| P3 | 字体方案 | 中 | 跨平台体验 |
| P3 | import-card 品牌色变量 | 小 | 代码可维护性 |
| P3 | `:focus-visible` | 小 | 无障碍优化 |