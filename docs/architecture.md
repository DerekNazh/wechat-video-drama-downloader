# 号匣（haoxia）架构蓝图

> 分支：`feature/haoxia` ｜ 状态：蓝图已闭环（2026-10-29）
> 定位：**实现层设计文档**（怎么做）——Spec.md 是决策真相源（为什么这么做），两本对照使用。
> 依据：Spec v1.84 全部已拍板决策 + 蓝图逐项讨论结论。本文件不新增决策，只落代码形态。

## 0. 总览

壳 + FastAPI 单进程。纯上游 API（红狐主 / TikHub 备），零微信客户端、零外部二进制、零系统代理、零 8899/2023/2022 端口。

```
外壳层：pywebview(WebView2) + FastAPI 单端口 + static/ 前端
核心层：adapters(双供应商防腐层) / cache(五层缓存) / downloader(自研下载)
        decrypt(Python ISAAC-64) / db(SQLite WAL) / api(薄路由) / monitor(可观测) / config(Pydantic)
上游层：红狐 redfox.hk（主 ¥0.04 免解密 T+1）｜ TikHub api.tikhub.io（备 ¥0.072 实时）
本地：SQLite(WAL+busy_timeout 5000) + 下载目录 + .env(密钥，不进包)
```

- 数据流①搜索/作者列表：前端 → API → 缓存门面 → 适配层（红狐列表 T+1 → 新作者 total=0 补 TikHub 一次）→ L2 缓存
- 数据流②下载：详情 → 适配层（红狐 videoDownload 直链 ¥0.04 免解密 / TikHub full_url+decode_key）→ L3 缓存直链 → 下载引擎 → L5 字节校验 →（加密源）Python 解密 → 出片

## 1. 适配层契约（core/adapters/）

**能力面抽象**（不 1:1 暴露供应商），`base.py` 定义 7 方法：

| 能力 | 主 | 备 | 备注 |
|---|---|---|---|
| search_works(keyword) | 红狐 searchWork/searchUser ¥0.04 | 无备 | TikHub 搜索域 400 平台侧故障，无备快速报错 |
| list_author_videos(nickname) | 红狐 queryWorkList ¥0.04（T+1） | TikHub fetch_user_videos ¥0.072（实时） | 新作者 total=0 补备一次；空确认 7 天免补 |
| get_video_detail(share_url) | 红狐 videoDownload/sph ¥0.04 免解密 | TikHub fetch_video_detail ¥0.072（要解密） | export_id 配 object_nonce_id |
| get_author_profile(ref) | TikHub 独有 | 无备 | 认证/粉丝/统计 |
| get_comments(ref) | TikHub 独有（懒触发 7 天默认 1 页） | 无备 | |
| get_collections(ref) | TikHub 独有（合集列表同 L2 快照） | 无备 | |
| get_live_history(ref) | TikHub 独有 | 无备 | 直播回放 |

统一 Result 含 cost_currency/cost_amount/used_provider。每次调用记 api_usage（供应商/端点/cost/duration_ms）。

**转备/熔断**（router.py 内部，唯一碰网络处）：
- 连接失败/5xx → 转备 1 次；429 → 指数退避不转备；401/402 → 转备；400 → 按端点判断；读超时 → 不转备不重试（防双计费）
- 连续失败 ≥3 → 供应商级熔断 60s；`fallback_enabled` 开关
- 边界纪律：扁平结构，不加泛型工厂/插件注册表/自动 schema 校验/配置驱动多态

**关键实现**：`adapters/router.py` 失败分类处置 + `adapters/base.py` 抽象 + `adapters/redfox.py` + `adapters/tikhub.py`。

## 2. 缓存层（core/cache/）

统一载体 **SQLite**（单机、重启不丢=省钱关键）、统一门面 `get_or_fetch(key, ttl, fetch_fn)`：

| 层 | 能力 | key | TTL | 说明 |
|---|---|---|---|---|
| L1 链接解析 | 分享链接 → 作者映射 | 链接 hash / nickname | 1 年复查期 | 重名冲突标记 |
| L2 作者列表 | author_id → 列表快照 | author_id | 120min（48h 硬上限） | 含合集列表同取同存；空确认标记 7 天免补 |
| L3 视频直链 | video_id → 直链 | video_id | 配置化 7 天起步（观察实验定死） | 直播回放走 media 短窗口 4h；TikHub keep cache_url 24h 免费重取 |
| L4 搜索 | keyword → 结果 | keyword 归一化 | 有结果 24h / 无结果 1h | |
| L5 文件校验 | task_id → 字节基准 | task_id | 永久 | 下载完成写入 |

- 降级策略：**stale-if-error**（拉取失败用过期缓存兜底 + 标记"X 小时前"）
- cache 不感知供应商，只加 hit/miss 标记；成本由适配层记 usage
- 载体：统一 SQLite（不引入内存层，YAGNI）

## 3. DB 层（core/db/）

**以 Spec 为唯一真相源，照抄不改名、不新增、不删表**：

| 类别 | 表 |
|---|---|
| 主业务 | authors（含 cover_updated_at）/ author_videos / download_tasks / task_log / resume_states / video_comments（v1.60） |
| 缓存 | channel_alias（L1）/ author_list_snapshot（L2，含合集）/ search_cache（L4）；L3 无新表 |
| 成本 | api_usage（supplier + duration_ms 列，阶段一即建）；supplier_cost（阶段二网关侧） |
| 不建 | card 表（柠檬为真相源） |

- 大整数：id 类字段（id/object_id/object_nonce_id/export_id/topic_id/live_id/comment_id/uid/decode_key）一律 TEXT（禁 INTEGER），缓存键字符串原样
- WAL + busy_timeout(5000) + check_same_thread=False 在 base.py 建库时配好
- DAO 三件：author_dao / video_dao / task_dao，写入口统一走 DAO
- schema_version：meta 表存版本号，结构变更走 ALTER 补丁，不引 Alembic
- 缓存逻辑"存储无关"接口化（阶段二上移网关零返工）
- **旧数据不迁移**：号匣新库从零（旧项目数据全属中间态）

## 4. 下载引擎（core/downloader/）

**8 态状态机**：pending → downloading ⇄ paused → verifying →（decrypting）→ done；failed / cancelled 为终态。
- 每次状态迁移立即落库；崩溃后启动扫描非终态自动恢复（downloading/verifying/decrypting 续传，pending 重新入队）
- 两条链路：红狐免解密（无 decrypting）/ TikHub 加密源（verifying 后 decrypting）
- 内容类型（普通视频/直播回放）由 author_videos 类型字段区分，任务表不关心

**行业标准 9 条**（全部采纳）：
1. 失败保留断点（failed 可续传），取消清理文件（cancelled 终态）
2. 无数据超时 idle timeout 30s（无新字节 → 判死重试）
3. 边下边取直链（不批量预取，防取消白扣 ¥0.04×N）
4. 磁盘空间预检（Content-Length × 1.2，不足提前失败）
5. done 后重下语义（文件在跳过；文件被删重建）
6. decrypting 进度（已解密字节/总字节，复用进度组件）
7. 重试入口：failed → pending（续传）/ cancelled → pending（全新）
8. `.part` 临时文件 + 原子 rename（同盘原子操作）
9. 断点续传带 `If-Range: etag`（etag 变 → 全量重下）

- 并发：DOWNLOAD_CONCURRENCY=3（config）；重试=内部循环（状态不变，连接失败/429/5xx 指数退避 2s→4s→8s+jitter ≤3 次；读超时/400 不重试）
- L5 校验：下载开始取响应头 Content-Length/Content-Range 为基准（字节权威），verifying 对比实际写入

## 5. 解密模块（core/decrypt/）

- 算法：ISAAC-64 密钥流 + 128KB 分块 XOR（Spec §B；本地爬虫会话已有实现 + _e2e_verify 实测成功，抽模块不改算法）
- 接口：`decrypt_file(src_path, dst_path, decode_key, progress_cb)`，流式处理（分块读→解→写），进度接 decrypting 状态
- 解密后快速验证：输出文件头魔数（MP4 = `ftyp isom`），失败按解密失败处理
- **4 出口闭环**：done（成功）/ failed（终态，密文保留供排查，不重试）/ cancelled（用户取消，清理解密临时文件）/ 崩溃恢复回 decrypting（密文在则直接重解，不重新下载）
- 并发 = DECRYPT_CONCURRENCY=1（CPU 密集串行）；产物先写 `.part` 再原子 rename
- 解密失败不重试（确定性操作，重试无益——与下载的网络重试区分）

## 6. API 路由层（core/api/）

**薄路由层（接线板不是业务层）**：
- 按资源分组（APIRouter）：`/api/authors` / `/api/videos` / `/api/tasks` / `/api/live` / `/api/status`
- 路由只做：参数校验 → 调缓存门面/适配层 → 返回统一 Result；业务逻辑全在下层
- 前端 38 接口**不变**（Spec §A 契约锁死，换源不换接口）——分组是后端组织方式
- `/api/status`：状态卡片只读端点（供应商健康/生效链路/熔断/今日调用与成本聚合），monitor 收集、status 暴露

## 7. 可观测（core/monitor/）

**日志三档埋点清单**：
- ERROR（必打）：适配层每次调用失败（供应商/端点/错误码/耗时）、熔断开启、下载 failed（原因）、解密失败（含魔数校验失败）
- WARN：转备触发、stale 兜底、429 退避、total=0 补拉、上游结构异常（解析防御降级成功）
- INFO：每次 API 调用（api_usage）、任务状态迁移、缓存 hit/miss

**纪律**：
- try/catch 三件套：捕获异常必须 记 error 日志 + 上报 monitor（状态/熔断计数）+ 走降级/失败路径；禁止空 catch
- 熔断台账：内存态（Circuit Breaker Closed/Open/Half-open，重启清零），不落库
- 日志落盘：RotatingFileHandler（5MB×5）+ console，LOG_DIR 默认用户数据目录
- 阶段一不做成本报表视图（v1.49 阶段二网关侧），api_usage 落库 + 状态卡片轻量聚合内部可看

## 8. 配置（config/settings.py）

Pydantic Settings，前缀 `HAOXIA_`，三级读取（系统环境变量 → .env → 默认值）。18 键全集：

| 组 | 键 | 默认 |
|---|---|---|
| 密钥 | REDFOX_API_KEY / TIKHUB_KEY | 空（.env 本地两行） |
| 超时 | CONNECT_TIMEOUT / REDFOX_READ_TIMEOUT / TIKHUB_READ_TIMEOUT | 5s / 30s / 90s |
| 熔断 | CIRCUIT_BREAK_THRESHOLD / CIRCUIT_BREAK_COOLDOWN / FALLBACK_ENABLED | 3 / 60s / true |
| 缓存 TTL | CHANNEL_ALIAS_TTL_DAYS(365) / AUTHOR_LIST_TTL_MIN(120) / SEARCH_TTL_HOURS(24) / SEARCH_EMPTY_TTL_HOURS(1) / VIDEO_LINK_TTL_DAYS(7) / LIVE_LINK_TTL_HOURS(4) | 见左 |
| 下载 | DOWNLOAD_CONCURRENCY(3) / DECRYPT_CONCURRENCY(1) / IDLE_TIMEOUT_SEC(30) | 见左 |
| 运行时 | HAOXIA_PORT / LOG_LEVEL / DOWNLOAD_DIR | 单端口 / INFO / 用户目录 |

- `.env.example` 首启生成（v1.84 ⑥），不含真实 key
- 密钥纪律：明文不进对话、不进包、不进 Spec

## 9. 前端对接（static/）

- **删**（旧链路 UI）：微信诊断分支、res_download 面板、8899/2023/2022 端口状态 UI、微信依赖提示
- **留**：搜索/浏览/下载/任务管理/播放器/封面头像/作者列表
- **改**：数据面板数据源（后端路由背后换到适配层+缓存），前端 fetch URL 不变
- **加**：状态卡片（供应商健康/生效链路/熔断）、封面加载失败占位图+重试≤3 次、空状态文案（total=0 三态）
- **不加**：任何收费/计费元素（阶段一验收判据）
- 回归：L1 功能回归 10 项必做；`scripts_check_frontend.py` 门禁保留（防内联 onclick/innerHTML 回退）

## 10. 本地 API 安全（高优先级，必做）

桌面应用本地服务三件套：
1. FastAPI 只绑 **127.0.0.1**（不暴露局域网）
2. **随机鉴权 token**：启动生成 → pywebview 注入前端 → 每个请求校验 `X-Auth-Token` 头（Jupyter/VS Code 本地 server 同款）
3. **校验 Host/Origin**（防 DNS rebinding）

不做的后果：本机任何程序/恶意网页可调 API——恶意刷直链烧上游钱（每触发 ¥0.04-0.072）、读作者数据、改任务状态；阶段二接卡密后恶意消耗用户点数。

## 11. 单实例 + 优雅退出（高优先级，必做）

- 单实例：启动创建命名 Mutex（Windows，名=号匣）；已存在 → 提示"号匣已在运行"退出
- 优雅退出：关闭事件 → 全部下载/解密任务落 interrupted → 收线程池 → 退出；下次启动复用崩溃恢复路径自动续传

不做的后果：双开 = SQLite 锁冲突/库损坏风险 + 同一视频重复调直链 API 双扣费 + 状态互相覆盖；直接杀进程 = 每次退出都当崩溃、日志全 error、丢最后进度。

## 12. key 失效提示（做）

适配层 401/402 → monitor 记录 → 状态卡片显示"红狐 key 失效" + 前端一次性横幅（不弹窗打断）。不做 = key 过期后一直走贵的备不自知，误报 bug 浪费排查时间。

## 13. 实施顺序（拆票依据）

按依赖拓扑：**config → adapters/db → cache → downloader → decrypt → api → monitor → 前端删改 → L1 回归 10 项**。
- 阶段一验收：不打开微信即可 搜索→浏览→下载 全链路 + api_usage 落库 + 界面零收费元素
- 阶段二在其上叠加：卡密 + 星尘点数 + 网关（数据获取路由被网关替代，接口形态不变，前端零改动；本地能力路由保留）
