# 号匣 Pro（商业版）微信视频号下载器

> 商业版=纯 API 中间商：数据源=红狐（RedFoxHub 主）/ TikHub（备）双供应商，本地零外部二进制、零微信客户端依赖。
> 与 wechat-downloader 分支（本地版/号匣·免费）为两个独立产品线：本分支仅覆盖视频号，短剧嗅探不在本版本范围。

## 产品定位（v1.84 定名对齐，2026-10-30 用户拍板）

- **商业版（号匣 Pro，本分支 master/feature-haoxia）**：TikHub/红狐 API 转发 + 积分计费，纯中间商赚差价，无本地 Go/解密依赖；
- **本地版（号匣，wechat-downloader 分支）**：本地解密+嗅探零成本免费版——详见该分支翻写规格 `docs/翻写规格-wx_channels.md`。

## 功能

- **跨号搜索**：关键词搜作者 / 搜作品（红狐 searchUsers/search_works 主）
- **作者管理**：添加/批量添加作者、作品列表（分页）、作者合集（合集列表+合集内视频，TikHub 专属）、直播回放列表、作者主页资料/认证信息
- **分享链接直下**：贴短链（`weixin.qq.com/sph/xxx`）→ 一步解析作者+视频 → 直接下载（红狐 `videoDownload/sph` 直链免解密，¥0.04；TikHub share_url 兜底）
- **下载**：自研直链 HTTP 下载模块（full_url 直链 + 浏览器 UA + Range 断点续传），免解密直下优先、TikHub decode_key 本地 ISAAC-64 解密兜底
- **商业化**：卡密激活（16 位→绑定设备→兑换点数）、点数扣费（1 操作=1 点）、一卡一机绑定、自助解绑（限 2 次）、route_rate 定价表、对账报表、防滥用（单卡并发≤5+全局 QPS）、柠檬后台对接

## 技术栈

- 后端：Python FastAPI + Uvicorn
- 前端：原生 JS
- GUI：pywebview (WebView2)
- 依赖管理：uv（`pyproject.toml` + `uv.lock`，统一入口 `uv run python`，requires-python≥3.13）
- 数据源：红狐（主）/ TikHub（备）双供应商互备（同功能红狐优先、失败自动切换）
- 下载：自研直链下载模块（替代旧 wx_video_download / gopeed / 2022 端口）
- 打包：PyInstaller（onedir，关 UPX）

## 目录结构

```
├── gui.py                    # GUI 入口
├── main.py                   # CLI 入口
├── build.py                  # 打包脚本
├── Spec.md                   # 产品规格（唯一真相源）
├── VERSION                   # 版本号单一事实源
├── core/
│   ├── api/                  # FastAPI 路由
│   ├── service/              # 业务逻辑（author/search/video/task/player…）
│   ├── downloader/           # 自研直链下载模块
│   ├── adapters/             # 数据源适配（redfox_client 主 / tikhub_client 备）
│   ├── monitor/              # 监控模块（低频轮询：打开界面即同步 + 标星每天 2 次）
│   ├── db/ cache/ config/ cli/ updater/ utils/
├── config/
│   ├── settings.py           # 配置管理
│   └── .env.example          # 环境变量模板（首启生成，.env 永不进包）
├── static/                   # 前端（index.html + js/ + css/）
├── scripts/                  # 工具脚本
├── skills/                   # 开发流程文档（CICD / frontend_modify）
└── tests/
```

## 快速开始

### 1. 环境准备（uv，v1.84 统一入口）

```bash
uv sync          # 按 uv.lock 重建 .venv（阿里云镜像）
```

### 2. 配置

```bash
# 首次启动自动生成 .env（模板 config\.env.example），填入：
# REDFOX_API_KEY / TIKHUB_KEY / 服务端口 / 下载目录
```

### 3. 启动

```bash
uv run python gui.py     # GUI 模式
# 或
uv run python main.py    # CLI 模式（仅后端 API）
```

### 4. 使用流程

1. 主界面为单视频号 Tab（无短剧嗅探 Tab）
2. 关键词搜作者 → 添加 → 作品列表（红狐直链）→ 直链下载
3. 或直接贴分享链接 → 解析作者+视频 → 下载
4. 下载前置检测 = TikHub/红狐连通 + 余额检查（不再依赖微信客户端）

## 数据链路（双供应商互备）

```
用户操作 → 后端 FastAPI → 红狐 API（主，¥0.04/次，直链免解密）
                          ↓ 失效自动切换
                        TikHub API（备，$0.01/次，full_url+decode_key 本地解密）
```

- 微信通道已移除（v0.8 拍板）：不存在"切回微信"，不存在系统代理/8899/2023 代理链路
- 合规：红狐=正规付费数据 API（对外商业化主数据源）；TikHub=抓取类（仅内部备用链路，UI 明示"抓取类数据仅限个人调研/内部分析"）

## 打包发布

```bash
# 更新版本号（VERSION 单一事实源）
uv run python build.py --version x.y.z

# 打包（产物在 dist/ 下）
uv run python build.py
```

详见 [skills/CICD/SKILL.md](skills/CICD/SKILL.md)

## 前端开发

直接修改 `static/js/` 下的文件，刷新浏览器即可。
详见 [skills/frontend_modify/SKILL.md](skills/frontend_modify/SKILL.md)

## 许可证

私有项目，未经授权禁止使用
