# 微信号视频短剧下载器 v1.0.0

> 集成视频号监控下载 + 短剧嗅探下载的一体化工具

## 功能

- **视频号监控**：实时监控微信视频号，自动下载视频
- **短剧嗅探**：通过代理拦截短剧视频资源，批量下载
- **系统代理管理**：内置代理开关，一键开启/关闭
- **多任务管理**：支持多个作者/视频同时下载

## 技术栈

- 后端：Python FastAPI + Uvicorn
- 前端：原生 JS（视频号） + Vue3 + Arco Design（短剧）
- GUI：pywebview (WebView2)
- 代理：res_download(8899) → weixin_download(2023) 链式转发
- 打包：PyInstaller

## 目录结构

```
├── gui.py                    # GUI 入口
├── main.py                   # CLI 入口
├── build.py                  # 打包脚本
├── core/
│   ├── api/                  # FastAPI 路由
│   │   ├── app.py            # 应用启动/关闭
│   │   └── routers/          # API 路由（视频、作者、搜索、代理等）
│   ├── service/              # 业务逻辑
│   ├── utils/                # 工具类（socket、数据库、事件总线）
│   └── monitor/              # 监控模块
├── config/
│   ├── settings.py           # 配置管理
│   └── .env.example          # 环境变量模板
├── static/
│   ├── index.html            # 视频号前端
│   ├── js/                   # 视频号前端 JS
│   ├── css/                  # 视频号前端 CSS
│   └── sniff/                # 短剧前端（Vue3 构建产物）
├── weixin_exe/               # weixin_download 运行时（exe + config + global.js）
├── res_download/             # res_download 运行时（exe）
├── skills/                   # 开发流程文档
│   ├── CICD/SKILL.md         # 发布流程
│   └── frontend_modify/SKILL.md  # 前端修改流程
└── docs/                     # 项目文档
```

## 快速开始

### 1. 环境准备

```bash
# 创建虚拟环境
python -m venv .venv

# 激活虚拟环境
.venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置

```bash
# 复制环境变量模板
copy config\.env.example config\.env

# 编辑 .env 修改配置（端口、下载目录等）
```

### 3. 启动

```bash
# GUI 模式
python gui.py

# 或 CLI 模式（仅后端 API）
python main.py
```

### 4. 使用流程

1. 启动后进入主界面，有两个 Tab：**视频号** 和 **短剧下载**
2. 视频号：添加作者 → 开始监控 → 自动下载
3. 短剧：在设置中**开启系统代理** → 浏览器访问短剧页面 → 资源自动嗅探 → 点击下载

## 打包发布

```bash
# 更新版本号
python build.py --version x.y.z

# 打包（产物在 dist/ 下）
python build.py
```

详见 [skills/CICD/SKILL.md](skills/CICD/SKILL.md)

## 前端开发

### 视频号前端

直接修改 `static/js/` 下的文件，刷新浏览器即可。

### 短剧前端

1. 修改 `pac版本/frontend/src/` 下的 Vue3 组件
2. `cd pac版本/frontend && npm run build`
3. 将 `dist/` 整体覆盖到 `static/sniff/`

详见 [skills/frontend_modify/SKILL.md](skills/frontend_modify/SKILL.md)

## 代理链路

```
微信/浏览器 → 系统代理(8899) → res_download → 匹配规则(短视频资源) → 直接下载
                                        ↓ 不匹配
                                   UpstreamProxy(2023) → weixin_download → 微信拦截
```

## 许可证

私有项目，未经授权禁止使用
