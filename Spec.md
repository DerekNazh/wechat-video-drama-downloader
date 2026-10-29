# Spec：号匣（haoxia）微信视频号下载器（红狐主 / TikHub 备双供应商）

> 状态：草稿 · v1.85 · 2026-10-29（v1.84 实施前风险⑤-⑪统一落档；v1.85 Spec 全量审查清零旧文字残留：标题号匣化、阶段一前置条件回填（TikHub 风控解除 v1.60/v1.65 实测可用）、客户端版本号 1.0.0（修正 v1.47 v0.1.0 残留）、fetch_channel_id_to_username 移出×3（v1.80）、熔断归属修正（v1.83 供应商级提前阶段一）、L1 口径（share_url 主路径 v1.78）、L2 红狐主注（v1.39）、"不调 TikHub"→"不调上游"、接口总数统一 38）；此前版本记录：v1.80 400 官方确认；v1.81 前端安全修复落档；v1.82 下载链路三连环·环3收口：L5 校验=Content-Length 字节权威、file_size 降级纯展示；v1.83 实施前风险逐项拍板统一落档：①成本感知转备（供应商级熔断提前阶段一，修正 v1.45）②解析防御五件套 ③红狐 T+1 方案 A+空确认标记+total=0 三态区分（empty_reason 实测）；v1.84 实施前风险⑤-⑪统一落档：⑤开发环境 uv 接管（pyproject/uv.lock/.python-version/scripts_scan_deps.py，15 依赖全量迁移）⑥打包两件套+分支策略（master=旧项目冻结、feature/haoxia=号匣 V1 全新产品：纯 API、零外部二进制、无旧链路、.env.example 首启生成、产物名"号匣"）⑦前端集成回归三层（L1 功能回归 10 项必做）⑧nickname 重名（锚定唯一 ID+配对缓存+TikHub 兜底）⑨SQLite 并发（客户端本地库，WAL+busy_timeout 5000）⑩大整数核查项（全链路 string 已定 v1.42，实施 grep 排查三类值）⑪自动更新替换权限（退出后替换 A3，阶段二升 A2）；客户端 UI 规范遵循暗宇宙设计系统，氛围层+操作区克制；「两阶段交付路线」：阶段一自用版 / 阶段二商业化版）
> 范围：本版本仅覆盖**视频号（数据源=红狐主 / TikHub 备）**；**短剧嗅探不在本版本范围**（另行排期合入）。
> 目的：本文档用于对齐需求与实现边界，供团队探讨迭代。内容基于现状代码统计与知识库《TikHub 供应商契约》《红狐 RedFoxHub 契约》整理。

---

## 两阶段交付路线（v1.39 新增：阶段一自用版 / 阶段二商业化版）

> 决策（2026-10-28 用户拍板）：本版本拆成两个阶段交付。**阶段一不做支付、不做定价，完全满足自用**（公司内部自用，不对外售卖）；**阶段二做商业化**（支付 + 卡密 + 点数计费）。两阶段共享同一核心（双供应商换源 红狐主/TikHub 备 + 本地能力 + 缓存降本），阶段二 = 阶段一 + 商业化收费闭环，不返工核心。

### 1. 软件功能总账（按域统计，Spec v1.38 收敛）

| 域 | 功能明细 | 落点 |
|---|---|---|
| **A 数据获取** | 跨号搜索作者、添加/批量添加作者、作者作品列表（分页）、**作者合集（合集列表 + 合集内视频，v1.54 进本版，TikHub 专属）**、直播回放列表（分页）、视频详情、分享链接解析（share_url，v1.78 主路径）、sph 短号映射（可选辅助，v1.77 降级；fetch_channel_id_to_username v1.80 实测 400 移出）、作者直下（贴链接→列表直出→下载） | 前端 `/api/search/*`、`/api/video/*`、`/api/live/*` 等视频号 38 个接口（换源红狐主/TikHub 备，前端接口不变） |
| **B 本地能力** | 下载引擎（自研直链下载 + **Python 内嵌解密** ISAAC-64/128KB XOR）、SQLite 存储（authors/author_videos/download_tasks/task_log/resume_states）、播放器、头像/封面直链、下载任务管理（进度/状态/速度实时、取消/删除/清空、批量去重） | 本机 Python 后端 + 本地 DB，与数据源无关 |
| **C 监控** | 增量监控（**打开界面即同步 + 标星作者每天 2 次兜底，v1.22**；只拉第一页对比 createtime）、监控器本体 | monitor/* + 前端监控 tab |
| **D 缓存降本** | L1 链接解析（channel_alias，TTL 1 年）、L2 列表快照（author_list_snapshot，120min，48h 硬上限，**含合集列表，v1.55 同取同存同过期**）、L3 链接年龄窗口（decode_key **不长期缓存**/详情 media 短 TTL 4–12h + 下载前安全窗口=实测×0.8 出数前 24h 保守）、L4 搜索缓存（search_cache，有结果 24h/无结果 1h）、L5 下载去重、api_usage 成本计量 | 客户端本地 SQLite（**阶段一，无服务器**，§5①）；网关共享形态=阶段二 |
| **E 旅程优化** | 作者直下入口、微信依赖清理（67 处）、「添加作者→同步入库」旅程移除、批量下载收敛、互动数展示（**v1.59 规格：列表=点赞+评论 2 项、详情=全 5 项、过万缩写、0 值显示**；上游字段接入 exportId/topic/width-height/headUrl，零额外调用）、**作者维度数据展示（v1.60：粉丝/关注/获赞=懒触发 7 天、作品数=本地快照）+ 视频评论展示（懒触发 7 天，默认 1 页）** | 前端减项 + authors/author_videos/新表 video_comments 新增列 |
| **F 商业化** | 卡密激活（16 位卡密→绑定设备→兑换点数）、点数扣费（1 操作=1 点，扣点先于调用）、一卡一机设备绑定、自助解绑（限 2 次）/客服换绑、route_rate 定价表（星尘 SD）、对账报表（api_usage 全量）、防滥用（单卡并发≤5 + 全局 QPS）、柠檬后台对接（规格/批次/发卡/冻结） | 客户端卡密模块 + 网关计费拦截 + 柠檬（香港机） |
| **G 系统运维** | TikHub/红狐连通与余额状态卡片、密钥管理（server-secrets）、**旧库废弃（不迁移：微信版 app.db 仅 6 作者 + 457 条视频元数据，直链已过期，新库从零开始）**、降级路径（**红狐↔TikHub 双供应商互备**，v0.8 微信通道已移除）、合规提示 | 状态卡片/配置/文档 |

### 2. 阶段一：自用版（无支付、无定价，完全满足自用）

**范围**：A + B + C + D + E + G 全部；**F 不做**。

| 类别 | 处置 |
|---|---|
| 数据获取全套（A） | ✅ 保留——搜索/列表/详情/回放/链接解析/直下是自用核心 |
| 本地能力全套（B） | ✅ 保留——下载/解密/存储/播放/任务管理原样 |
| 监控（C） | ✅ 保留——低频增量追更自动拉新 |
| 缓存降本 L1–L5（D） | ✅ 保留——**自用也按次计费，缓存照省**；`api_usage` 仅作内部成本日志（可观测），不做对账报表 |
| 旅程优化（E） | ✅ 保留——直下入口、简化交互、互动数展示 |
| 系统运维（G） | ✅ 保留——密钥/迁移/降级/合规 |
| 卡密/点数/扣费/定价（F） | ❌ 不做——无收费 UI、无计费拦截 |
| 一卡一机/解绑/柠檬对接 | ❌ 不做——自用无防共享需求 |
| 防滥用限流 | ❌ 不做——自用无盗刷场景 |
| 自动更新 | ✅ 保留基础更新机制（§2.6），**不加授权/商业化校验** |

**阶段一验收判据**：不打开微信客户端即可完成「搜索→浏览→下载」全链路；自用成本可观测（api_usage 落库即可，不需对账）；界面无任何收费/计费元素。

### 3. 阶段二：商业化版（支付 + 卡密 + 点数计费）

**范围**：阶段一全部 + **F 全量**。

| 新增 | 说明 |
|---|---|
| 卡密激活模块 | 客户端顶栏「卡密」tab：输入 16 位卡密→绑定设备→兑换点数（照 §4.2 行业标准：入口可达/单输入框/输入体验/精确反馈/状态展示） |
| 柠檬后台对接 | 应用「号匣」（香港库 apps.id=3，2026-10-28 已由 downloader 更名完成，app_id=app_3b7743b66b114c42aa655bb19a61d4f1 不变）→ 4 档规格（1天3/3天10/7天25/30天100 星尘）→ 批次生成 → CSV 导出 → 客服人工发卡（已拍板） |
| 点数计费 | 1 操作 = 1 点；**扣点先于调用**（余额不足直接 429，不调上游） |
| route_rate 定价表 | 网关统一收口：产品/端点/定价/汇率（星尘 SD，1 点≈¥0.07 锚），人工改表即生效 |
| 一卡一机 | 设备指纹绑定防共享；客户端自助解绑限 2 次 + 客服换绑 |
| 对账 | api_usage 全量启用：收入 = Σ 售卡×售价；成本 = Σ api_usage.cost；月度报表 |
| 防滥用 | 单卡密并发 ≤5 + 全局 QPS 兜底（商业模型自保：时间+点数双限制） |
| 购买引导 | 余额不足/到期 → 「联系客服购买」（客服人工发卡，已拍板） |
| 自动更新 | 不加授权/商业化校验（v1.66 已砍）——更新保持 v1.47 定案：公开静态桶 latest.json、人人可更新、不收费；**替换机制（v1.84 拍板）**：Windows 运行中 exe 文件锁+安装目录写权限 → 行业标准"退出后替换"落地 A3：阶段一=下载新版→提示重启→重启时替换（装用户目录保写权限）；阶段二升级 A2=launcher 引导程序自动替换 |

**阶段二验收判据**：用户可自助激活卡密→扣点使用→余额不足引导购买；对账报表毛利可算；一卡一机防共享生效；定价改表即可、客户端无需发版。

### 4. 依赖与排期影响

- **P0 / P1 / P2 全部落在阶段一**（动工前置 → 数据/缓存地基 → 换源/减项）；商业化 P3 拆入阶段二。
- **阶段一即可交付可自用版本**；阶段二在其上叠加收费闭环，不返工核心（表结构、缓存、换源在阶段一已定型）。
- 表结构：`api_usage` 阶段一即建（成本可观测），对账逻辑阶段二启用；`card` 表不建（柠檬为真相源，两个阶段都遵守）。
- 里程碑建议：阶段一完成 = 自用版发布；阶段二完成 = 商业化上线（依赖柠檬真时间卡开发方案落地或先用限期积分卡顶上）。

### 5. 阶段一闭环性审查（2026-10-28 追加）

**结论：阶段一可独立闭环**（无服务器、无商业化组件也能完整自用），但有 3 个必须落实的点，否则会暗中依赖阶段二：

**① 缓存归属修正（关键，防"阶段一依赖服务器"）**：
- v1.27「网关化」是**阶段二**（C/S 中转、有服务器）的架构：L1/L2/L4 落在网关共享（跨用户跨机器省钱）。
- **阶段一（自用、无服务器）缓存必须落在本地 SQLite**——同一套逻辑（channel_alias / author_list_snapshot / search_cache 本地建表，字段与网关版一致），否则阶段一依赖服务器 = 不闭环。
- 实施口径：缓存逻辑按「存储无关」实现（接口化），阶段一接本地 SQLite，阶段二把同一套逻辑上移到网关 DB（表结构兼容、字段不变，只换存储层，零返工）。

**② 阶段一前置条件（外部依赖，非划分缺口）**：
| 项 | 状态 |
|---|---|
| TIKHUB_KEY | ✅ 已建（server-secrets，len=60，2026-10-27 核验） |
| TikHub 充值/权限 | ✅ **已实测可用（v1.60 风控解除：fetch_user_videos / fetch_user_profile / fetch_video_comments 全 200 计费成功；v1.65 export_id 直通 + media full_url Range 206 断点续传实测）**；仅搜索域（fetch_search/fetch_search_videos）与 channel_id 域（fetch_channel_id_to_username）为**平台侧 400（v1.80 官方确认含"服务器内部错误"且不计费）**→ 不接入主链路，由红狐 searchWork/searchUser 与 share_url 直达替代；不再存在"权限搁置待开通"状态 |
| 本机 Python 后端（内嵌解密） | ✅ **已验证（v1.70 端到端实测）**：Python 内嵌解密（ISAAC-64 + 128KB XOR）本地样本与真实素材均解密成功、ffprobe 可播；Go 下载/解密服务**已移除**（v1.40 拍板）；阶段一验收判据已实测达成 |

**③ 自动更新降级**：阶段一保留基础更新机制（§2.6），更新源/频率可先禁用或手动——更新失败不阻塞自用（浏览/下载不依赖更新）。

**阶段一闭环验收清单（一条链路跑通即闭环）**：
搜索/贴作者链接 →（L1 链接解析命中）→ 作者列表（L2 缓存秒开）→ 浏览互动数 → 勾选下载（直链在列表响应，本地自研下载器）→ 本地 **Python 解密**落盘 → 任务进度/取消/去重 → 监控增量拉新（低频）→ api_usage 本地落库。
全程不出现：服务器地址、卡密输入、点数/余额、任何收费 UI；断网/无服务器时本地功能照常。

### 6. 阶段一架构缺口审查与决策（2026-10-28 起，逐条拍板）

> 来源：阶段一架构闭环审查发现的缺口清单（#1–#12，按影响分三档：主线断点 / 实施前收口 / 可选增强）。逐条讨论拍板，已拍板条目落档此处，未拍板条目待继续。

| # | 缺口 | 决策 | 状态 |
|---|---|---|---|
| 1 | **解密链路未定**（下载后是加密文件，无解密=无法播放） | **已拍板：Python 后端内嵌解密（双链路并存，TikHub 解密为必保能力）**。事实依据：①TikHub 是纯数据 API，只返回加密直链 full_url + decode_key，不提供解密接口；②算法公开=Isaac64 PRNG 生成 131,072 字节密钥流 + 对视频前 128KB 做 XOR（看雪逆向公开、Evil0ctal 开源确认）；③本地已有纯 Python 实现与验证样本：`D:\dev\wechat-decrypt\WeChat-Channels-Video-File-Decryption\`（decrypt_wechat_video_cli.py 纯 Python CLI + wx_encrypted.mp4 加密样本 + wx_response.json 含 decode_key=2136343393）；④红狐直链免解密（§6.1 实测）**不能成为放弃自研解密的理由**——双供应商任一侧失效都必须能独立完成全链路，防供应商单点失效。**决策**：①下载=双链路并存——主链路=红狐 videoUrl 直链直下（免解密）；备用链路=TikHub media full_url + 同响应 decode_key **Python 内嵌解密**；②**Go 进程整体移除**（2026-10-28 用户确认"太重"）——解密职责由 Python 后端内嵌模块承担（ISAAC-64 生成 128KB keystream + XOR），进程形态=**前端壳 + Python 后端（两件套）**，去掉 Go 服务及其启停管理，不引入 Docker、不依赖外部黑盒；③解密位置=客户端本地（两阶段一致，视频文件不进服务器，隐私+带宽双优）。**P0 动作：✅ 已验证（2026-10-28）**：Python 解密实测通过——`scripts_probe_python_decrypt.py`（1:1 翻译 Hanson/WechatSphDecrypt Go 实现：Seed[0]=encKey 其余 0、大端 8 字节输出、倒序取随机数）用 `wx_encrypted.mp4`（decode_key=2136343393）解密成功，ffprobe 解析 52.31s 可播放；**TikHub 备用链路端到端可用**。生产解密模块以此脚本为算法基准，本地样本（wx_encrypted.mp4 + wx_response.json）为回归单测 | ✅ 已拍板 2026-10-28，P0 已验证 |
| 2 | Go 服务职责边界不明（2022 下载弃用后 service/start\|stop\|restart 仍保留的理由未定义） | **已闭环：Go 进程整体移除**（2026-10-28 用户确认"太重"）。解密职责=**Python 后端内嵌模块**（ISAAC-64 + 128KB XOR，参考 Evil0ctal 纯 Python CLI + 本地验证样本）；`/api/service/start\|stop\|restart` 路由**下线**（gui.py 启动链路相应简化）；2022 create2 下载弃用（自研 downloader.py 取代）；进程形态=**前端壳 + Python 后端两件套**（无独立 Go 服务、无启停管理） | ✅ 已闭环 2026-10-28 |
| 3 | 搜索端点内部矛盾 + 响应未验证 | **已闭环：引入红狐补位（双供应商并存，红狐优先）**。事实依据：①TikHub `wechat_search/v2/fetch_search` 是官方"搜一搜"（business_type=account 即搜公众号·服务号·视频号账号，官方推荐"发现内容的起点"），但我们账号 9 连测全 400（含官方建议重试 5 次、最小参数），疑似账号级权限未开通（400 指引提交支持团队）；②`fetch_search_videos` 实为**搜视频**端点，Spec 旧文"用它做跨号作者搜索"写错；③红狐 RedFoxHub 有 `search_users`（关键词搜账号，已实测 200：返回 findName=v2_…@finder 即 TikHub username、nickname、signature、headUrl、coverImgUrl、uid、total）。**决策**：①搜作者主链路=红狐 search_users（REDFOX_API_KEY 已有）；TikHub 搜一搜走支持工单开通（不阻塞，开通后按红狐优先原则可保留备用）；②L4 搜索缓存设计保留，键值=红狐 searchUsers 响应；③Spec 全部 `fetch_search_videos` 作搜索端点的表述修正（见 §6.1 与 Implementation Decisions） | ✅ 已闭环 2026-10-28 |
| 4 | 前端大整数 json-bigint 改造遗漏 | **已闭环：前端零改造，不需要 json-bigint**。行业标准=API 层 ID 一律字符串返回（Twitter `id_str` 历史教训明文、GitHub `node_id`、Stripe `cus_xxx`——超大整数在 JSON 里本就该是字符串）；我们 Python 后端 `tikhub_client` 已规定大整数按字符串处理（Spec 1228）、实测确认按字符串返回（1355）→ 前端只调 Python 后端、拿到的已是字符串，**无精度问题**。**全链路统一字符串（P0，2026-10-28 用户确认"统一用 string"）**：①后端响应模型所有 id 类字段（id/object_id/object_nonce_id/export_id/topic_id/live_id/comment_id/uid/decode_key）一律 `str` 类型，禁止 int；②数据库存 TEXT 列（禁止 INTEGER，防 Python int↔SQLite INTEGER 边界）；③缓存键拼接用字符串原样；④Python 解密模块入参 decode_key 按 str 处理。前端无需引入任何解析库 | ✅ 已拍板 2026-10-28 |
| 5 | TTL 口径矛盾（P1 15–30min vs 拍板 120min；L4 10–30min vs 24h/1h；L3 7–30 天 vs 24h 窗口） | **已闭环（2026-10-28）：TTL 单一事实源治理**——根因=旧段落未随拍板回填（非设计矛盾）。权威口径以 §4 缓存表为准：L1=1 年复查期 / L2=120min（48h 硬上限）/ L3=decode_key 不长期缓存 + media 年龄安全窗口（出数前 24h 保守=实测×0.8）/ L4=有结果 24h、无结果 1h / L5=永久。**同步回填 9 处旧残留**：①总表 L3 口径 ②P1 建表名（author_list_snapshot、L3 无新表）③P1 L2/L3/L4 TTL ④P1 service 路由（v1.40 下线）⑤fetch_search_videos 搜索端点表述 5 处（v1.39 实锤为搜视频端点）⑥P1 create2 下载残留。**新纪律（P0）**：今后每轮拍板必须回填受影响旧段落（决策记录+段落同步改，不留副本） | ✅ 已拍板 2026-10-28 |
| 6 | 超时/重试计费防护（30s 超时已扣费，重试可能双计费） | **已拍板（2026-10-28，v1.45）：超时分级 + 失败分类重试（本版做）；熔断切换后置（阶段二，v1.83 修正：供应商级熔断提前阶段一）**。事实依据：①上游计费=按调用次数扣，**执行完即扣费、不关心客户端是否收到**——30s 卡点丢弃=白付费+用户失败，超时值必须"够大到不白丢"；②红狐失败（非 200）不计费、TikHub 400/404 免费（实测）→ 确定性失败重试安全；③读超时=状态未知（上游可能已执行）→ 绝不重试；④公司规范 ADR-020：禁止写死全局超时、失败分类两套处理、熔断切换；⑤幂等白捡：柠檬 consume 自带 biz_id 幂等（v1.26 实证）。**决策**：①**超时分级**（值进 billing_config，改表不改代码）：连接超时 5s 统一、红狐读 30s、TikHub 读 90s（官方要求 ≥30s，宁可大、靠观测调）；②**失败分类重试**：连接失败（未到达上游）/429/5xx → 指数退避 3 次（2s→4s→8s+jitter）；401/402/400 → 不重试直接失败+提示；**读超时 → 绝不重试**；③**api_usage 加 duration_ms 列**（P95 观测驱动超时调参，不拍脑袋）；④熔断切换（supplier_cost active 机制，连续 3 次失败→熔断 60s→冷却恢复）：**供应商级熔断提前阶段一**（成本感知转备 v1.83=实施前风险①拍板：供应商故障自动切换阶段一实施），计费级熔断仍后置阶段二；⑤失败返还 + biz_id 幂等利用=阶段二商业化 | ✅ 已拍板 2026-10-28 |
| 7 | 本地应用取 TIKHUB_KEY 通道（server-secrets 注入方式未定义） | **已拍板（2026-10-28，v1.46）：key=静态配置，走 Pydantic Settings（.env）**。阶段一（自用版，无服务器）：本地 `.env` 文件两行 `REDFOX_API_KEY` / `TIKHUB_KEY`，Python 后端启动时读；改 key=改 .env 重启。阶段二（商业化，网关在服务器）：**key 上收服务器 env（server-secrets 落库），客户端零 key**——key 在客户端=用户拿到即可绕过我们直连上游，与"价格永不在客户端"同一原则。**配套纪律**：.env 不进安装包（打包排除）、不入 git；自用版本地明文可接受（不对外发）；key 有效性检测走既有接口级全局熔断（401/402 → 提示检查 Key/余额） | ✅ 已拍板 2026-10-28 |
| 8 | 阶段一自动更新源矛盾（保留基础机制但无更新源，柠檬=阶段二） | **已拍板（2026-10-28，v1.47）：复用公司标准 OTA（ADR-022 静态存储发布模式），阶段一即启用完整自动更新**。事实依据：①拾光AI 已有生产验证的完整 OTA 标准——ADR-022（客户端直连 OSS 零服务器、latest.json 指针人控切换）+ 拾光 v0.6.7 发版（`shiguang-ai/releases\|updates/v0.6.7/` + `updates/latest.json` 指针，ETag=本地 MD5）+ 发版手册（`-PublishPointer` 人控覆盖指针、release_record.py 自动登记）+ 就绪度清单（latest.json 四字段 version/sha256/url/pub_date）；②自动更新与支付/卡密解耦——阶段一有自动更新但无任何收费元素。**产品定名（2026-10-28）**：**「号匣」**（OSS 目录 `haoxia`，撞名初判无同名知名产品；拼音好拼无歧义）。**决策**：①更新源=`lemon-kami-artifacts` 公共读桶（规范钦定 OTA 分发桶）`https://lemon-kami-artifacts.oss-cn-beijing.aliyuncs.com/haoxia/updates/latest.json`；②目录结构对齐拾光：`haoxia/releases\|updates/{版本}/`（安装包+update.zip 双产物不可变）+ `updates/latest.json` 指针（人控切换）；③客户端版本号 **1.0.0 起步**（v1.84 修正 v1.47"v0.1.0"残留：VERSION 单一事实源沿用、号匣从 1.0.0 独立起步，与 Spec 版本号独立两套）；④发布链路对齐 ADR-021 本地化：本机构建→公共桶不可变产物+私有桶归档→`-PublishPointer` 切指针→release_record.py 登记；⑤客户端 updater 逻辑复用既有自动更新设计（929 行状态机：后台检查 10s 超时静默失败/当天不重试/独立安装器/sha256 校验）；⑥阶段二同机制零改造（源不变，自动更新本身不收费） | ✅ 已拍板 2026-10-28 |
| 9 | 断点续传未设计（自研下载器 resume） | **已拍板（2026-10-28，v1.50）：阶段一实施，A 方案（单连接 Range 自动续传）**。事实依据：①HTTP Range 协议（RFC 7233：Range/206/416）；②**红狐直链实测支持**（206 Partial Content + Accept-Ranges: bytes + Content-Range 完整，2026-10-28 `scripts_probe_range_support.py` 实测，文件总长 3.1MB 单视频样本）；③TikHub 微信系端点账号级风控已于 **v1.60 解除实测**（fetch_user_videos / fetch_video_detail 200 计费成功），**v1.65 实测 media full_url（wxapp.tc.qq.com CDN）Range 探测 HTTP 206 + Accept-Ranges: bytes**——断点续传 TikHub 链路已实测可用（与红狐 206 同设计），不再有"权限搁置待开通"状态；④TikHub 直链与红狐同微信 CDN 集群（finder.video.qq.com vs findermp.video.qq.com、同 251/20302/stodownload 路径格式）。**决策**：①自研下载器断点续传=**通用探测设计**：下载失败/中断→任务标 pending（gui.py 既有机制）→恢复时探测直链 `Accept-Ranges`→支持则 `Range: bytes=已下字节-` 续传（进度写 resume_states）→不支持/416 则整包重下+提示；②下载完成后 Content-Length 对齐校验→统一进解密（解密在下载后执行，续传不影响解密逻辑）；③阶段一双链路均启用（红狐 v1.50 实测、TikHub v1.65 实测） | ✅ 已拍板 2026-10-28（v1.65 补测收口） |
| 10 | 封面/头像 URL 过期兜底 | **已拍板（2026-10-28，v1.48）：行业标准版，复用 L3 机制零额外成本**。事实依据：①行业标准=签名 URL 不存库当永久地址——存 URL 同时存过期时间、提供前检查过期、过期重新拉取（PostPulse「store expiry alongside URL + check before serving + re-fetch when expired」/ 技术栈「签名URL不要存库当永久地址」）；客户端=加载失败→占位图+**有限次重试**+重试上限防无限循环（CSDN data-retry-times / safe-img fallback chain）；②封面/头像 URL 天级过期是常态（DEV：YouTube 创作者头像一周内有效）；③红狐 `get_user_works` 返回 headUrl/coverImgUrl → **L2 列表刷新顺带更新封面/头像，无独立调用**。**决策**：①authors 表加 `cover_updated_at` 列（头像封面同源同更）；②浏览作者页检查年龄（TTL 按天计、与 L3 同机制宽松），过期走 L2 列表刷新顺带带回新 URL；③客户端图片加载失败→占位图 + 重试≤3 次 + 超限稳定占位图（防无限循环） | ✅ 已拍板 2026-10-28 |
| 11 | 多 Key 轮换 | **已拍板（2026-10-28，v1.51）：不做（平台口径不支持）**。事实依据：①TikHub 官方限流=**账号级速率**——默认 10 RPS（按单端点计、不同端点并行不抢限额），RPS 提速为账号级月付（20 RPS $5/月、100 RPS $55/月）；控制台可生成多个 token，但**无"多 token 独立配额"承诺**——换 key 不涨 RPS，多 key 对限流无效；②红狐定价按每日请求量阶梯（1,000–30,000 次/月），有频率限制（社区实测调用间隔 0.15–0.25s≈4–7 QPS），**官方未公开限流粒度条款**（无 key 级独立配额承诺）；③已有防护已覆盖多 key 想解决的问题：429 指数退避重试（v1.45）+ 双供应商互备（v1.39）+ 账号级问题走工单/多账号备用。**决策**：多 key 轮换**不优先做**；仅当未来实测发现某上游按 key 粒度限流时再启用 | ✅ 已拍板 2026-10-28（不做） |
| 12 | 自用成本统计视图 | **已拍板（2026-10-28，v1.49）：阶段二实施项，阶段一跳过**。归属=网关侧（服务器端）——`api_usage` 表由网关转发时顺手记（endpoint/supplier/count/cost/duration_ms），成本统计视图=网关侧内部报表接口，按日期/端点/供应商聚合，仅供运营看、不给用户；**阶段一无网关（客户端直连上游）→ 不计量不报表，跳过不阻塞阶段一闭环**；**阶段二定价前必须做**（真实成本基准，回答"毛利是否严谨"） | ✅ 已拍板 2026-10-28（阶段二实施） |

### 6.1 双供应商接口映射（红狐优先，2026-10-28 拍板）

> **策略**：TikHub 与红狐（RedFoxHub）**并存**；同一功能红狐能覆盖的**尽量先走红狐**（红狐微信视频号数据端点基价 **¥0.04/次**（广域库 T+1，阶梯最低 ¥0.02）、实时端点 ¥0.06 起、字幕 ¥0.3 起 vs TikHub 微信系 $0.01≈¥0.07/次；红狐作品直链**免解密**）。红狐端点均已实测（2026-10-28）：search_users / search_works / get_user_works / get_work / get_work_by_link 全部 200；**get_user_works 与 get_work 返回 videoUrl 直链，实测下载可播**（content-type=video/mp4，ffprobe：H.264 High / 720×1280 / 9:16，未加密）。认证：`REDFOX_API_KEY` 请求头（server-secrets 已有），base=`https://redfox.hk`，成功码 `code=2000`。**红狐端点级价格已统计（2026-10-28 官网 API 文档，见下方"红狐端点价格"）**。

| 功能 | 红狐（RedFoxHub） | TikHub | 首选 | 备注 |
|---|---|---|---|---|
| 关键词搜作者 | `search_users` ✓（/story/api/sphAllData/searchUser） | `fetch_search`+account（**当前账号 400**） | **红狐** | searchUser 返回 findName（=username）、nickname、signature、headUrl、coverImgUrl、uid、total；分页 page/pageSize≤50 |
| 关键词搜作品 | `search_works` ✓ | `fetch_search_videos`（**400**） | **红狐** | 红狐结果**无 videoUrl**（有 videoId/exportId/互动数）；TikHub 端点实为"搜视频"非"搜作者" |
| 账号作品列表 | `get_user_works` ✓（**入参=nickname 昵称精准匹配**；username 实测 0 条） | `fetch_user_videos` ✓（username，实时） | **红狐** | 红狐列表项带 **videoUrl 直链（v1.78 实测未加密可播 MP4，免解密）** + like/comment/fav/forward 互动数 + publishTime + videoDuration + exportId + topic；TikHub 带 media+decode_key（加密源需解密） |
| 作品详情 | `get_work` ✓（videoId） | `fetch_video_detail` ✓（object_id/export_id/share_url） | **红狐** | 红狐返回 videoUrl 直链；TikHub 返回 full_url+decode_key |
| 短链解析 | `get_work_by_link` ✓（**仅元数据+exportId，无直链**） | `fetch_video_detail`(share_url) ✓（media+decode_key，**v1.77 实测真实解析闭环：短码→nickname+username+media**） | 红狐(资料)/TikHub(兜底) | **贴链接直接下载=红狐 `videoDownload/sph` 单端点主（v1.78 实测直链可播 ¥0.04 免解密）**，TikHub share_url 兜底（红狐源失效时）；红狐 exportId→videoId 映射待确认（仅作 export_id 入参用） |
| 视频下载 | videoUrl **直链直下、免解密** ✓（列表/详情/链接下载源均实测可播，v1.78） | full_url + decode_key + 本地 ISAAC-64 解密 ✓ | **红狐**（主）/ **TikHub**（备） | 红狐直链已实测可播（ftyp isom，列表源 18.27s / 链接源 310.13s）；**双链路并存**——TikHub 解密为必保能力（红狐失效/改版时备用链路须端到端可用），详见缺口 #1 |
| 作者主页资料+统计 | ✗（searchUser 仅基础字段） | `fetch_user_profile` ✓ | **TikHub** | 红狐无主页统计端点 |
| 作者认证信息（增强） | ✗ | `fetch_channel_info` ✓（**v1.79 实测 200**） | **TikHub（可选增强）** | 返回 **Channels ID（sph 前缀，username→channel_id 反向映射）**+认证主体（服务单位，官媒/机构认证）+IP 归属地+资料所在地；**接入价值**=作者卡片认证标记/官媒筛选/可信度展示；与 profile（粉丝/获赞）互补，懒触发 TTL 7 天 |
| 作品评论 | ✗ | `fetch_video_comments` ✓ | **TikHub** | — |
| 合集 | ✗ | `fetch_user_collections` / `fetch_collection_videos` ✓ | **TikHub** | — |
| 直播回放 | ✗ | `fetch_live_history` / `fetch_live_detail` ✓ | **TikHub** | — |
| 号内搜索 | ✗ | `fetch_search_channel_videos` ✓ | **TikHub** | 需先知 username |
| 生成分享链接 | ✗ | `fetch_video_share_url` ✓ | **TikHub** | — |
| sph 短号→username | ✗ | `fetch_channel_id_to_username`（**v1.79/80 实测 400 平台侧确认**） | ✗（**移出**） | **v1.80 官方确认：TikHub 文档定义 400="参数错误或无效，有时因服务器内部错误"（Sometimes occurs due to server internal errors），且 400 不计费**；真实 sph ID（sphi9BjV8GK0Zsl，来源 fetch_channel_info）喂入=400（与 fetch_search 同形态）→ **平台侧问题，非我们用错**，彻底移出主链路；主页链接场景兜底=链接页取昵称→红狐 searchUser |
| 账号信息 | ✗ | `fetch_channel_info` ✓ | **TikHub** | — |
| 链接提文案/字幕 | `transcript_submit/result` ✓（红狐独有） | ✗ | **不采用（主线排除）** | **✅ 已拍板 2026-10-28：主线不接字幕端点**。submit **¥0.3/次起**、result 免费；成本=数据端点 7.5 倍（¥0.04），属可选增强，且 TikHub 无对应端点。需求出现时改走**本地 Whisper 转写**（免费、纯本地算力、音频从已下载视频抽取），不进阶段一/二主线；成本锚不含此路由 |

**红狐端点价格（2026-10-28 官网 API 文档核实）**：

| 端点 | Path | 数据档 | 基价（起步档） | 阶梯最低（30k+） |
|---|---|---|---|---|
| 搜索视频号作品 | `/story/api/sphAllData/searchWork` | 广域库 T+1 | ¥0.04/次 | ¥0.02/次 |
| 搜索视频号账号 | `/story/api/sphAllData/searchUser` | 广域库 T+1 | ¥0.04/次 | ¥0.02/次 |
| 作品内容详情 | `/story/api/sphAllData/queryWorkDetail` | 广域库 T+1 | ¥0.04/次 | ¥0.02/次 |
| 账号作品列表 | `/story/api/sphAllData/queryWorkList` | 广域库 T+1 | ¥0.04/次 | ¥0.02/次 |
| 作品链接更新详情（实时） | `/story/api/sph/ability/workLinkDetail` | 实时 | ¥0.06/次 | ¥0.03/次 |
| 视频号链接下载（parseWork） | `/story/api/parseWork/videoDownload/sph` | 实时 | 未标注（按实时档 ¥0.06 预估，**待官网核实**） | 未标注 |
| 提文案-提交任务 | `/story/api/parseWork/sphSubtitle/submit` | 任务制 | 未标注（¥0.3 起） | ¥0.3/次 |
| 提文案-查询结果 | `/story/api/parseWork/sphSubtitle/result` | 任务制 | **免费** | 免费 |

阶梯规则（官网 pricing）：账户**全接口累计调用量合并**判定档位，优质 0-1k ¥0.04 → 1k-5k ¥0.036 → 5k-10k ¥0.032 → 10k-20k ¥0.028 → 20k-30k ¥0.024 → 30k+ ¥0.02；实时档 0-1k ¥0.06 → 最低 ¥0.03；**失败（非 200）不计费**；充值 1:10（100 元=1000 积分）；订阅收录 ¥100/账号/年、付费回溯 1000 积分/账号/年（不参与阶梯）。

**关键影响（落档）**：
1. **下载双链路并存**：主链路=红狐直链直下（免解密、便宜，列表/详情/链接下载三源均实测可播）；备用链路=TikHub full_url+decode_key 本地解密（红狐直链失效/改版时自动启用）。**TikHub 解密是必保能力，必须实现并验证**（缺口 #1 决策已强化，P0 验收=decode_key 配对解密实测成功），防供应商单点失效。
2. **作者主键**：红狐按 `nickname` 拉列表（**精准匹配，v1.78 实测入参=nickname、username/findName 入参 total=0**）、TikHub 按 `username` 拉列表 → **统一主键=username（findName，唯一稳定）**，nickname 为红狐调用参数（作者改名需刷新映射，属 L3 缓存/资料更新范畴）。**风险标注：nickname 不唯一**（重名作者精准匹配可能命中错账号；share_url 返回的 nickname 与 findName 成对，应缓存两者映射，优先用"链接解析得到的 findName→红狐列表"时注意红狐列表只认 nickname——实施时列表场景以"链接解析所得作者主页为准"校对，遇重名取最新作品归属者）。
3. **贴作者链接（L1）闭环（v1.79 终版：双路径+入参 nickname）**：用户贴分享链接（短码）→ **两路径**：①**直接下载该视频**：红狐 `videoDownload/sph`（`parseWork/videoDownload/sph`，入参 url）**单端点返回未加密可播直链**（v1.78 实测：As68wzqwSd → downloadUrl=finder.video.qq.com/stodownload?encfilekey=…，ffprobe 310.13s 可播，¥0.04 免解密）；兜底 TikHub `fetch_video_detail(share_url)`（$0.01≈¥0.072，full_url 加密源+decode_key 解密）；②**进入作者列表**：TikHub `fetch_video_detail(share_url)` 返回作者 **nickname**（v1.77 实测：200 REAL-DATA，nickname=棋虎南厦）→ 红狐 `get_user_works(nickname)` 拉列表（**入参=nickname 昵称精准匹配，username/findName 入参实测 total=0**）→ 直链下载（免解密）。**fetch_channel_id_to_username 已实测 400 平台侧确认（v1.79/80：真实 sph ID sphi9BjV8GK0Zsl 喂入=400 不扣费；官方文档定义 400 含"服务器内部错误"且不计费）→ 彻底移出主链路**；主页链接场景兜底=链接页取昵称→红狐 searchUser（实施时遇真实主页链接再验，不阻塞）；**时效注意**：红狐广域库 T+1，当天新发布作者列表可能 total=0（棋虎南厦 10-27 发布 10-28 查 0 条实测）→ 列表兜底 TikHub `fetch_user_videos(username)`（实时，方案 A v1.83：补拉结果空→7 天空确认标记免补；total=0 三态区分=红狐无区分字段、TikHub empty_reason，见 v1.83），链接直接下载不受影响（parseWork 实时）。
4. **互动数据**：likeCount/commentCount/favCount/forwardCount 红狐列表直接返回 → 视频表保存互动数无需额外调用（满足"接口返回字段要保存"）。
5. **待确认**：①✅ **红狐各端点精确单价已统计（2026-10-28 官网 API 文档**：数据端点广域库 T+1 基价 ¥0.04/阶梯最低 ¥0.02、实时端点 ¥0.06/¥0.03、字幕 submit ¥0.3 起/result 免费，阶梯按账户全接口累计量合并**）；②`get_work_by_link` 的 exportId 如何转 videoId（贴单视频链接下载归属）；③红狐直链 TTL（纳入 L5/过期观察）。
6. **收/支分离（v1.41 拍板）**：接入红狐**不改对客定价**（route_rate 扣点不变、售价不变）——行业标准=收支持分离（one-api/new-api 渠道独立定价）；上游成本按供应商拆入新表 `supplier_cost`（route×supplier→人民币分），`api_usage` 加 `supplier` 列记实际供应商，路由优先级=红狐优先/TikHub 兜底（active+成本最低，失败熔断切换）；route_rate.upstream_cost_cents 弃用为兜底默认。成本锚更新：核心数据路由红狐 ¥0.04（→0.02）< TikHub ¥0.072。

## Problem Statement

现有「二合一总下载器」（微信视频号 + 短剧嗅探）的视频号数据获取完全依赖本机微信客户端：

- 用户必须**打开微信客户端**并打开过视频号页面，注入脚本回连后端（端口 2022）后功能才可用；
- 依赖**根证书安装**，证书不生效则视频号页面白屏、注入失败；
- **微信版本升级即失效**，需持续拉取外部维护的黑盒二进制（wx_video_download / res_download）；
- 故障难排查：`channels.available` 字段已知不可靠，微信未打开与证书故障两种成因难区分。

目标：**让用户无需打开微信客户端即可使用视频号功能**，用已入知识库的外部数据 API（红狐主 / TikHub 备，v1.39 双供应商）替代依赖微信客户端的"数据获取"环节，同时尽量保留现有本地下载/解密/存储能力，控制改造成本与使用成本。

## Solution

- **数据获取层换源**：搜索作者、作者作品列表、直播回放列表、视频详情、分享链接解析，全部改调外部数据 API（红狐 `redfox_client` 主 / TikHub `tikhub_client` 备，鉴权 `Bearer REDFOX_API_KEY` / `Bearer TIKHUB_KEY`），不再经过微信客户端注入链路。
- **本地能力保留**：下载引擎（url + decode_key 即可下载）、ISAAC-64 解密、SQLite 存储、播放器、头像/封面直链均不依赖微信客户端，原样保留。
- **前端接口层不变**：现有视频号 **38 个** `/api/*` 前端接口与交互不变（短剧 10 个不在本版本范围），替换只发生在 FastAPI 与数据源之间。
- **成本受控**：微信系数据端点上游成本=红狐 ¥0.04/次（主，v1.41）或 TikHub ¥0.072/次（备），按量计费；监控轮询频率从"每 30 分钟"改为**打开界面即同步 + 标星作者每天 2 次兜底（v1.22）**，增量只拉第一页对比 `createtime`。
- **合规定位（v1.75 修正）**：**红狐=正规付费数据 API（有 ToS/商业授权），对外商业化的主数据源走红狐，合规**；**TikHub 抓取违反平台 ToS，属合规灰色**——仅作内部备用链路（自用阶段一可用；对外商业化阶段二**不把 TikHub 作为主数据源对外承诺**，红狐为主）；文档与 UI 明示"抓取类数据仅限个人调研/内部分析"。
- **范围**：本版本仅覆盖视频号功能；**短剧嗅探（res_download 链路 / static/sniff 前端）不在本版本范围**，后续版本再合入。

## 接口映射总表（前端 38 ↔ 后端数据源）
> 阶段归属：**阶段一**（换源核心，前端接口不变）

前端**视频号 38 个接口全部复用不变**（短剧 10 个不在本版本范围）；映射发生在「后端服务层 ↔ 数据源」这一层。分三类：

### A. 数据获取类：换源红狐主/TikHub 备（7 个后端接口，前端接口不变）
> 注：本表为 TikHub 换源时代分析。v1.39 双供应商后：**同功能端点红狐优先且成本更低（红狐广域库 ¥0.04/次 < TikHub ¥0.072/次，见 §6.1 supplier_cost）**；表中计费列为 TikHub 备胎价。

| 前端接口 | 当前数据源（微信客户端） | TikHub 替代端点 | 计费 |
|---|---|---|---|
| `/api/search/authors?q=` | contact/search | **红狐 `searchUsers`（主）/ TikHub `wechat_search/v2/fetch_search` account 垂类（备）**（v1.39 修正：`fetch_search_videos` 实为搜视频端点） | ¥0.04 / $0.01 |
| `/api/search/author/add` | contact/search + feed/list 首屏 | `fetch_user_videos` 第 1 页（链接解析昵称→红狐 searchUser 兜底，v1.79/80 后 fetch_channel_id_to_username 已 400 移出） | $0.01/次 |
| `/api/search/author/batch-add` | 同上（批量） | `fetch_user_videos` × N | $0.01 × N |
| `/api/video/author/:id/add` | feed/list | `fetch_user_videos` 第 1 页（增量） | $0.01/次 |
| `/api/video/add-all` | feed/list × 全部作者 | `fetch_user_videos` × N（增量） | $0.01 × N |
| `/api/video/sync-new` | feed/list + live/replay/list | `fetch_user_videos` + `fetch_live_history`（第 1 页对比 createtime） | $0.01–0.02/作者 |
| `/api/monitor/start`（内部轮询） | feed/list + live/replay/list | `fetch_user_videos` + `fetch_live_history`（低频：标星作者每天 2 次兜底，v1.22） | $0.01–0.02/作者/轮 |

### B. 语义调整类（2 个）

| 前端接口 | 调整 |
|---|---|
| `/api/service/status` | `wechat_connected` → `tikhub_connected` + 余额状态 |
| `/api/status` | 同上（状态聚合语义） |

### C. 纯本地不动（29 个）

| 分组 | 接口 |
|---|---|
| video（7） | `all` / `author/:id` / `:id`(GET+DELETE) / `batch-delete` / `author/:id/all` / `avatar/:id` / `cover/:id`（头像封面直链本就不依赖微信） |
| task（6） | `list` / `cancel` / `cancel-all` / `:id` / `completion-log` / `batch-create`（v1.21：自研 `downloader.py` 直链下载模块，url+key 由数据层供给） |
| inputer（7） | csv/excel/tencent-doc 导入 + 两个模板 + 两个上传 |
| monitor（4） | `stop` / `doc-sync/start` / `doc-sync/status` / `doc-sync/stop` |
| 其他（5） | `player/play` · `service/config` · `service/logs` · `events`(SSE) · `leader/splash` |

### D. 短剧前端独立（10 个）—— **本版本不在范围**

`resources` / `get-config` / `set-config` / `proxy-open` / `proxy-unset` / `download` / `direct-download` / `clear` / `is-proxy` / `set-type`

> 短剧前端（static/sniff）与 res_download 链路不在本版本范围，后续版本合入；本次交付物为单「号匣」——数据源=红狐主 / TikHub 备（v1.39 双供应商），不再保留二合一形态。

### 后端内部被替换的 weixin_client 调用（4 个，前端不可见）

| 现状（微信通道） | TikHub 替代 |
|---|---|
| `contact/search` | **红狐 `searchUsers`（主）/ TikHub `wechat_search/v2/fetch_search`（备）**（v1.39 修正） |
| `contact/feed/list` | `fetch_user_videos` |
| `live/replay/list` | `fetch_live_history` |
| `feed/profile` | `fetch_video_detail` |
| `check_wechat_connected`（微信连接探测） | TikHub 连通 + 余额检查（只读探测） |

### TikHub 端点使用清单（按本映射收敛）

- **核心 5**：红狐 `searchUsers`（搜作者，主）/ TikHub `fetch_user_videos` / `fetch_live_history` / `fetch_video_detail`（**含 share_url 解析=L1 主路径，v1.77 实测闭环**）/ ~~`fetch_channel_id_to_username`~~（**v1.79/80 实测 400 平台侧确认，彻底移出主链路**；主页链接兜底=链接页取昵称→红狐 searchUser；`fetch_search_videos` 实为**搜视频**端点，不再作为搜索端点）
- **增强 4（已部分进本版）**：`fetch_user_profile`（主页资料，**v1.60 已接入本版**懒触发+TTL 7 天）/ `fetch_video_comments`（评论，**v1.60 已接入本版**懒触发+TTL 7 天）/ `fetch_user_collections` + `fetch_collection_videos`（合集，**v1.54 已进本版**顺风车）/ `fetch_search_channel_videos`（号内搜索，**仍 P3 后置**）

## 接口收敛分析（现状繁琐/重复 ↔ TikHub 覆盖）
> 阶段归属：**阶段一**

基于前端代码统计（`static/js/datahandle/*`、`component/authorDialog.js`、`api/*`），现状存在多处"一次操作串多个接口 / 同一逻辑多份重复"，且多个后端接口可由 TikHub 单端点覆盖：

| # | 现状繁琐点（代码证据） | TikHub 覆盖 | 收敛方案 | 是否动前端 |
|---|---|---|---|---|
| 1 | 添加作者 = 2 次调用：`/api/search/authors?q=` → 用户点添加 → `/api/search/author/add`（后端再拉首屏）；搜索结果字段映射不完整（profession/friend_count 恒空） | 红狐 `searchUsers`（搜作者，主）+ `fetch_user_videos`（首屏） | 后端把「搜索 → 入库 → 首屏」合并为一个动作；前端搜索页 1 次调用拿全 | 前端调用次数减少（接口名可不动） |
| 2 | 作者同步逻辑重复在 3 个接口：`/api/video/author/:id/add`、`/api/video/add-all`、`/api/video/sync-new`（同一套「拉列表→对比 createtime→入库→建任务」） | `fetch_user_videos` / `fetch_live_history`（第 1 页增量） | 后端收敛为 1 个内部「同步引擎」，3 个入口共用 | 前端接口名不动（仅内部复用） |
| 3 | 建任务在前端 3 处重复调 `/api/task/batch-create`（videoOps.js 37/101/693） | TikHub/红狐返回 media+decode_key / videoUrl 直链 → 直接喂自研下载模块（v1.21，弃用 gopeed） | 同步引擎内自动建任务，前端无需反复手动批量创建 | 前端代码清理（接口不动） |
| 4 | CSV/Excel 导入两套 ~90 行几乎相同代码 + 上传→导入两步（upload-csv → csv/import） | —（与 TikHub 无关） | 合并为通用导入函数 | 前端代码清理（接口可合并） |
| 5 | 视频详情 `/api/video/:id`（DB）与实时详情分离 | `fetch_video_detail`（一次全量：详情+media+decode_key+互动） | 后端 `/api/video/:id` 内部兜底调详情 | 前端不动 |
| 6 | 转义工具函数 escAttr/escHtml 各文件重复定义 | — | 收敛到 utils | 前端代码清理 |
| 7 | 下载前「微信连接检测」重复 2 处（videoOps.js:7-16 / :522-534 几乎同段代码），批量失败诊断再查 `/api/status`（:127）判微信断开 | TikHub 版无需微信连接 | 3 处检测统一替换为 TikHub 连通检测（或移除）——**TikHub 化隐性改动面** | 前端代码改（必要） |
| 8 | 裸 `fetch` 绕过 `api/` 封装共 43 处调用点（裸 fetch≈34 + 封装≈9）；`api/task.js` 等封装大多未被业务代码调用（app.js/videoOps.js/authorDialog.js 自行裸 fetch） | — | 统一收敛到 `api/` 封装，接口语义调整时只改封装一处 | 前端代码清理 |
| 9 | `addAuthor` 把「添加作者」伪装成「按昵称关键词再搜一次」（`payload.keyword = nickname`，authorDialog.js:249） | 红狐 `searchUsers` + `fetch_user_videos` 直接按 ID/username 取 | 前端直接传 username/id 一步入库，去掉间接搜索 | 前端调用简化 |
| 10 | 同步完成双通道状态机：HTTP 返回 + SSE done 互相兜底（SyncDialogState + _onSyncDoneCloseDialog），逻辑复杂 | TikHub 同步收敛为单接口后 SSE 进度保留、双通道兜底可简化 | 简化双通道兜底逻辑 | 前端代码清理 |
| 11 | 删除作者 4 阶段进度状态机（cancel_tasks→delete_files→delete_dirs→delete_records + 圆环进度 SVG，authorDialog.js） | 与 TikHub 无关 | **合理保留，不收敛**（本地删除） | 不动 |
| 12 | escape 函数第 3 处重复：authorDialog.js 再定义 esc/escHtml（:21 / :297 / :501） | — | utils 收敛点扩至 3 个文件 | 前端代码清理 |

**TikHub 化隐性改动面（前端微信依赖点，映射表外）**：
- 接口语义 2 个：`/api/status`、`/api/service/status`（B 类，已在映射表）；
- 前端 `wechat_connected` 依赖点 5 处：videoOps.js:12/:16（_batchCreateWithProgress 前置检测）、:127（批量失败诊断）、:529/:533（_startBatchProgress 前置检测）、authorDetail.js:32（服务状态展示）；
- 下载前置提示语义：「微信未连接」→「TikHub 未连通 / 余额不足」；
- ⚠ 这些点不在首版映射表内，实施时漏改会导致「TikHub 已通但前端仍拦截下载」的假象。

**收敛结论**：
- **后端数据获取原语收敛为 3 个**：`search+ingest`（搜索并入库）、`user_videos`（作品增量）、`live_history(+detail)`（回放增量/详情）——现有 7 个"换源"后端接口内部共用；
- **前端隐性改动面 5+2 处**（wechat 依赖点）必须随 TikHub 化同步调整，属必要改动而非可选；
- **前端「接口复用不动」是底线**：接口名不动 / 调用次数减少 / 代码收敛属可选优化，列为 P1 后置项，不影响本版映射对齐目标（上表"必要"行除外）。

## 换源后可砍项清单（采用 TikHub 后冗余逻辑/功能）
> 阶段归属：**阶段一**

换源红狐主/TikHub 备后，依赖「微信客户端」的逻辑整体失去存在意义，可按档位移除或替换：

### A. 彻底移除（微信客户端依赖消失）

| # | 可砍项 | 现状位置 | 移除后 |
|---|---|---|---|
| A1 | **微信客户端本体**：登录 / 扫码 / 常驻运行 / 引导 UI | 使用前提 | 用户无需打开微信（本方案核心收益） |
| A2 | `weixin_client.py` 微信通道封装：contact/search、feed/list、live/replay/list、feed/profile、check_wechat_connected | `core/utils/weixin_client.py` | 替换为 `redfox_client.py`（主）+ `tikhub_client.py`（备）（同接口、异实现，v1.39 双供应商） |
| A3 | 状态接口 `wechat_connected` 字段 | `/api/status`、`/api/service/status` | 改为 `tikhub_connected` + `balance` |
| A4 | 前端微信连接状态 UI 与 5 处检测（videoOps.js:12/:16/:127/:529/:533、authorDetail.js:32） | 下载前置检测 / 首页状态卡 | 改 TikHub 连通检测或移除 |
| A5 | 微信详情接口解析 url+decodeKey 的链路 | 后端 task 创建前段 | TikHub `fetch_video_detail` 直接供给 |
| A6 | 「微信已断开」失败诊断分支 | videoOps.js:127-141 | 删除，改 TikHub 诊断 |

### B. 保留但语义替换（功能仍在、实现换源）

- 搜索 / 作品列表 / 直播回放 / 详情 4 个数据动作 → TikHub 5 端点（映射表 A 类）；
- 下载前置检测 → TikHub 连通 + 余额检查（不再依赖微信会话）。

### C. 保留不动（与微信无关，本地 Python 后端承载）

- 自研直链下载模块（v1.21）+ **Python 内嵌解密**（v1.40）、task 模块、播放、SQLite 存储、封面头像；
- 导入（CSV/Excel/腾讯文档）、doc-sync、SSE、监控器本体；
- 短剧（已另行排期，不在本版本）。

### D. 已拍板：彻底移除（2026-10-27）

- A1–A6 全砍，交付物最小、无兜底；前端微信 UI/检测、`weixin_client.py` 微信封装、微信客户端本体一并移除；
- 监控器**功能保留**，内部微信数据获取源换 TikHub（低频：打开界面即同步 + 标星每天 2 次兜底，v1.22）；
- 保留「TikHub 失败时提示检查 API Key / 余额」的文案出口，不再提示用户打开微信。

## 前端可减项统计（后端换 TikHub 后，2026-10-27 全量扫描 static/js）

> **术语修正（v1.19）**：下文"直下模式"= **三路径并存**（我的作者主页 / 搜索 / 导入链接可选），不是"让用户贴链接"；核心变化是**去掉手动同步（配置弹窗/进度条/同步按钮），数据后台自动拉取**（L2/L4 缓存）。下文各删除/简化项在本语义下仍然成立。

**总体结论：前端可减/可简化面 ≈ 交互逻辑的 20–30%**，分四类：

### 1. 微信依赖类（67 处命中，绝大多数可删或可改）——彻底删除

| 位置 | 逻辑 | 处置 |
|---|---|---|
| `utils/api.js:5/:10` | 错误码 `-2`=「微信客户端未连接」 | 删 / 改 TikHub 语义 |
| `videoOps.js:12-14、529-532` | 下载前「微信未连接」拦截 2 处 | 删（改 TikHub 连通/余额检查或直接删） |
| `videoOps.js:127-141` | 批量失败诊断 `fetch('/api/status')`（死调用，后端无此路由） | 删 |
| `status.js:130-148、255-262` | 微信状态灯 txtWechat/dotWechat、「已连接/已断开」toast、wechat-off 按钮态 | 删 |
| `app.js:224/234`、`authorDetail.js:38/104/289` | `wechat_connected` 状态字段渲染 | 改 `tikhub_connected`+`balance` |
| `doc_sync_monitor.js:96-103/156-157/217-218/347-356` | 监控就绪判断依赖 wechatConnected 2 处 + 诊断分支 2 处 | 改 TikHub 就绪判断 |

### 2. 「添加作者→同步入库」旅程整体可移除（直下模式下不需要"先入库再下载"）

| 位置 | 逻辑 | 处置 |
|---|---|---|
| `component/authorDialog.js:18-220` | 同步模式配置弹窗：按日期 / 按页数同步 | **删**（直下：输入链接直接全量列） |
| `component/authorDialog.js:369-530` | 同步 4 步进度 UI + 已找到统计（约 160 行） | **删** |
| `app.js:317` | 全局「同步最新」`/api/video/sync-new` | **删入口** |
| `authorDetail.js:946/1002` | 作者页「同步最新」`/api/video/author/:id/add` | **删入口** |
| `api/video.js:39` | `/api/video/add-all` 封装 | **删入口** |
| `authorOps.js:245-357` | 「搜索作者→添加弹窗」两段式衔接 | 简化：输入链接 → 直接列出（保留搜索界面本体） |

### 3. 批量下载路径收敛（保留功能、去掉重复与前置）

- `videoOps.js:37/:101/:693` 三处 `batch-create` 重复 → 收敛 1 处；
- 批量下载的微信前置检测 + 失败诊断分支 → 删，变为无条件直接下载。

### 4. 保留不动（与微信无关或直下仍需）

- 导入（CSV/Excel/腾讯文档 `authorOps.js:2/:97/:184`）、播放器、任务管理、封面头像、分页、搜索界面、设置、日志、监控器本体（内部换源低频轮询）、SSE 通道。

> 注：前端 38 接口名仍全部不动；本表是**旅程/逻辑层**的删除与简化，不涉及接口改名。

## 商业化与缓存降本设计（定价表 + 保本公式 + 缓存降本，2026-10-27）

> **共识（2026-10-27，用户拍板）：缓存先行、定价完全搁置。** 先把成本降到接近 0，定价才有完全自由空间（缓存期内收不收费都不亏）；两件事并行任务量大、做不精、不闭环。攻克节奏：**一次只攻一层，每层完成定义=可写代码+验收用例闭环，验收过才进下一层**（攻克顺序见 §4.1，L1 完整规格见 §4.2）。

### 1. 成本端（TikHub 契约 §2）
> 阶段归属：**阶段一**（成本意识；不涉及对外定价）

- 微信系端点统一 **$0.01/次** ≈ **¥0.07/次**（按 7.2 汇率粗算，非实时）；无订阅、余额充值制；新户赠 $0.05（**实测不吃赠额**，v1.13：微信系 `allow_free_credit=false`）；
- 日阶梯折扣：**已实测不覆盖**（v1.13：`allow_discount=false`，微信系固定 $0.01 无阶梯折扣）——红狐阶梯（1k-30k+，¥0.04→¥0.02）见 §6.1；
- 默认 10 RPS 免费；规模化后 20 RPS=$5/月、100 RPS=$55/月（固定成本项）。

### 2. 行业定价对标（2026-10-27，3 类来源）

| 模式 | 参考 | 单价量级 |
|---|---|---|
| C 端下载器订阅 | 迅雷超级会员 ¥28–30/月、4K Video Downloader €9.99/月 | ¥15–80/月心理带 |
| B 端 API 聚合转售 | SocialAPI $3.22/千请求（Starter $29/月）、Apify Actor $2.2–4.99/千结果 | **¥0.009–0.023/次** |
| 同类社交数据 API | Xpoz $20/月 7500 credits、Lamatok $1/千请求 | ¥0.007/次 |

**关键结论：按"请求数"转售的行业价（¥0.009–0.023/次）低于我们的成本 $0.01/次（¥0.07）——走"按请求转售"必亏。必须按「产物价值」定价：作者全量/视频条数/包月订阅。**

### 3. 定价表草案（三档，毛利目标 50–70%）
> ⚠️ **已废弃（v1.44 拍板）**：本表为 2026-10-27「缓存先行、定价完全搁置」时代的讨论稿。**最终定价唯一真相源 = §2.5 卡型规格（v1.33 定稿）**：点数 × 时长 4 档卡（1天3点 ¥0.9 / 3天10点 ¥1.9 / 7天25点 ¥2.9 / 30天100点 ¥9.9）；**不做单作者月卡、不做按条计费、不做打包档**（v1.44 用户确认）。下表仅作历史留档，实施一律以 §2.5 为准。
> 阶段归属：**阶段二**（阶段一不做定价）

| 档位 | 定价 | 无缓存月成本 | 缓存 80% 命中后有效成本 | 毛利率（按缓存后） |
|---|---|---|---|---|
| A 单作者月卡（自动追更，每天 2 次打开） | ¥9.9/作者/月 | 120 次/月=$1.2≈¥8.6 | 30–60 次/月≈¥2.2–4.3 | **57–77%** |
| B 打包月卡（10 作者） | ¥29.9/月 | 1200 次=$12≈¥86 | 300 次≈¥21 | **30%（无缓存巨亏，必须绑定配额+缓存）** |
| C 按条（零散） | ¥0.3/条；作者全量 ¥5.9/次 | 全量 50 条≈$0.53≈¥3.8 | 命中缓存≈¥0.7 | 36%（冷启动）→ **88%（缓存后）** |

> 计价锚：定价 ≥ 有效成本 ÷ (1 − 目标毛利率)。示例：命中率 80%、毛利 60% → 定价下限 = ¥0.07×0.2÷0.4 ≈ **¥0.035/次**；按条 ¥0.3 远超下限。打包档必须配合"每作者每日拉取次数配额 + 冷却"，否则冷启动期亏穿。

### 4. 缓存设计（降本增效核心，5 层）
> 阶段归属：**混合**——L1–L5 阶段一（本地 SQLite 实现）；网关共享形态（跨用户省钱）= 阶段二（见「两阶段交付路线」§5①）

| 层 | 缓存对象 | TTL | 命中率预估 | 说明 |
|---|---|---|---|---|
| L1 | 分享链接（sph 短码）→ username+nickname 映射（v1.78 改 share_url 入参，顺带昵称/简介） | 1 年复查期（惰性失效+验证兜底） | ~100% | 短号几乎不变；失效/删号靠下游验证兜底删映射重取（完整规格见 §4.2） |
| L2 | 作者作品/回放列表（fetch_user_videos / fetch_live_history） | **120 分钟（2026-10-27 用户拍板，省钱档）** | 追更 80–95% | 打开界面秒开 + 后台静默刷新；列表 raw=false 自带下载链接 → 命中=浏览+下载双省；48h 硬上限（urlValidDuration 官方字段，观察实验校准） |
| L3 | 单作品详情（fetch_video_detail：media） | **详情 media 短 TTL 4–12 小时（v1.60 详情页懒触发缓存）+ 下载前安全窗口 = 实测保质期×0.8（出数前 24h 保守，v1.16 权威口径）** | 详情 90%+（旧视频全在 DB） | **decode_key 每次请求变化，不长期缓存**（v1.11 文档实证，修正"key 长缓存"）；两个参数职责不同：TTL=详情页缓存多久刷新（4–12h），安全窗口=下载前链接年龄判断（实测×0.8，观察实验校准）；过期由现有 ensure_valid_url 触发刷新 |
| L4 | 作者搜索结果（关键词 → 作者列表） | **24h 有结果 / 1h 无结果（2026-10-27 用户拍板，惰性刷新）** | 50–70% | 作者集合按天/周变化，非"每次搜完有新作者"（修正：原 10–30 分钟是误套视频节奏）；无结果短 TTL 防新号误判 |
| L5 | 下载任务级去重（已有 DB：url/key/spec） | 永久 | 100% 去重 | 同一视频不重复下载，天然省 |

**有效成本公式**：单次成本 × (1 − 命中率)。追更作者：列表 1 次 miss/天 + 详情仅新视频 → **单作者月有效成本 ≈ ¥2–4**，支撑 ¥9.9 月卡 57–77% 毛利。

### 4.1 攻克顺序与每层完成定义（2026-10-27 用户拍板：逐个击破、不铺开）

| 攻克序 | 层 | 完成定义（验收才算过） |
|---|---|---|
| ① | L1 链接解析（原短号映射，v1.78 改 share_url 入参） | 表结构 SQL + 命中/失效/熔断逻辑 + 边界清单 + 3 条验收用例，落地代码并测试通过 |
| ② | L2 列表缓存 | 缓存键/TTL/刷新时机 + 与互动数顺带更新联动 + 监控复用 + 验收（追更 10 次=1 次调用） |
| ③ | L3 详情缓存 | media 短缓存 + decode_key 刷新改造（ensure_valid_url 链路）+ 验收（旧视频下载 0 新增调用） |
| ④ | L4 搜索缓存 | 键设计（query+business_type）+ TTL + 前端防抖联动 + 验收（同词 10 次=1 次调用） |
| ⑤ | L5+前端冷却 | 下载去重现状核验 + 同步冷却/防抖 + 验收（狂点刷新只触发 1 次） |

### 4.2 L1 链接解析缓存（原"短号映射"，完整规格，v1.78 重写）

**通俗定位**：用户贴分享链接（短码 `weixin.qq.com/sph/xxx`）→ 系统解析出作者信息（username+nickname，**v1.77/78 实测：TikHub `fetch_video_detail(share_url)` 一步返回两者+media**，不再走 fetch_channel_id_to_username）→ username 喂 TikHub 拉列表 / nickname 喂红狐 `get_user_works`。解析一次花 $0.01；记住结果后，同链接再贴免费。

**表结构**（新表 `channel_alias`，与 Spec v1.6 建表项合并落地；主键从 channel_id 改为 link，v1.78）：

```sql
CREATE TABLE channel_alias (
    link           TEXT PRIMARY KEY,        -- 分享短码链接（https://weixin.qq.com/sph/xxx，解析入参）
    username       TEXT NOT NULL,           -- v2_...@finder（统一主键，喂 TikHub fetch_user_videos）
    nickname       TEXT,                    -- 作者昵称（喂红狐 get_user_works，v1.78 实测其入参）
    desc           TEXT,                    -- 简介，可 NULL
    source         TEXT DEFAULT 'tikhub',
    created_at     TEXT NOT NULL,
    updated_at     TEXT NOT NULL,
    fail_count     INTEGER DEFAULT 0,       -- 连续失败计数（熔断依据）
    failed_at      TEXT,                    -- 最近失败时间
    cooldown_until TEXT                     -- 冷却截止（单短链熔断）
);
```

**决策流程**：
- **命中且未过期**（TTL 1 年复查期）→ 直接用 username+nickname，**0 成本**；nickname/desc 视为非权威资料（权威更新靠 L2 列表顺带）
- **命中但过期**（惰性失效，请求时才判）→ 重调 TikHub `fetch_video_detail(share_url)`（$0.01）→ 成功则更新映射 + 顺带刷新昵称/简介
- **未命中** → 调 TikHub → 成功写库（share_url 实测返回 nickname+username 成对，两者都存）；**未命中返回**（`data.bad_input` / `data.error`，v1.76/77 实测形态）→ **fail_count+1、冷却 1 小时**，不写错误映射（防同短链反复烧钱）
- **接口级故障**（401 key 无效 / 402 余额不足）→ **全局熔断**，停止一切调用，提示检查 Key/余额，不重复打
- **下游验证兜底**：拿 nickname 喂红狐拉列表报错（作者注销/改名）→ **删映射** → 下个请求重新解析，自动纠错
- **格式校验前置**：链接须 `weixin.qq.com/sph/<短码>` 格式；非该格式（如含 sph 前缀 ID 的主页链接）→ 兜底=链接页取昵称→红狐 searchUser（v1.77；`fetch_channel_id_to_username` 实测 400 不可用 v1.79，不纳入）

**边界条件清单**：短链非法 / TikHub 未命中 / 作者注销 / key 失效 / 余额不足 / **读超时（v1.45 分级：红狐 30s / TikHub 90s，宁可等到干完不白丢费；读超时绝不重试）** / 并发同短链（加锁或幂等写）。

**验收标准（可测）**：
1. 同一短号连续解析 10 次 → 实际 TikHub 调用 **1 次**（`api_usage` 表计数验证）
2. 构造已失效短号（模拟 404）→ 自动删映射重取，**不落错误缓存**
3. 连续失败 3 次 → 冷却生效，24h 内不再调用该短号（计数为 0）

### 4.3 L2 列表缓存（完整规格，2026-10-27 落档 v1.14）

**通俗定位**：用户打开某个作者的页面 → 系统去拉他的作品/回放列表（一次 $0.01）→ 记住"这作者啥时候拉过"。没过期就直接免费给，过期才再去拉一次，增量只补新发的。**列表（raw=false）自带下载链接（full_url+decode_key 配对），所以列表缓存命中 = 浏览 + 下载双省**（v1.13 实测确认）。

> **红狐优先后口径（v1.39/v1.78 补充）**：列表主链路=**红狐 `get_user_works`（按次 ¥0.04，videoUrl 直链免解密，v1.78 实测可播）**，TikHub `fetch_user_videos`（$0.01/页，需解密）为**兜底**（红狐 T+1 当天新作者 total=0 时补拉，v1.83 方案 A）；缓存键/TTL/命中机制不变（存储无关接口化，§5①），下方 TikHub 页计费口径为兜底链路成本。

**接口能力事实（v1.20 统计确认，分页决策的依据）**：
- **TikHub 列表接口无"全量返回"模式**：`fetch_user_videos` / `fetch_live_history` 只能靠 `last_buffer`（base64 不透明游标，首页留空）**一页一页翻**；`fetch_search_channel_videos` 同理用 `cursor`/`next_cursor`
- 文档**无 total 字段、无每页条数参数**；成本 = **$0.01/页 × 页数**，与作者规模线性挂钩
- 含义：小作者（50 视频 ≈ 3 页）≈ $0.03；大作者（500-1000 视频）全量拉到底 ≈ $0.2-0.5，**成本不可预估** → 不能设计"全量拉到底"（2026-10-27 用户拍板改为策略 C）

**要动的落点（现状代码，均已定位）**：

| # | 文件 | 动什么 |
|---|---|---|
| 1 | `core/utils/database/crud/models.py` | 新增 `ChannelSyncState` dataclass；`AuthorVideo.decode_key: int → str`（TEXT 迁移，v1.11 已定） |
| 2 | 新建 `core/service/redfox_client.py` + `core/service/tikhub_client.py` | `RedfoxClient`（主，Bearer `REDFOX_API_KEY`，base=redfox.hk，成功码 code=2000）/ `TikhubClient`（兜底，Bearer `TIKHUB_KEY`）：统一 `raw=false`、浏览器 UA（P0 纪律）、**超时分级（v1.45：连接 5s / 红狐读 30s / TikHub 读 90s，值读 billing_config）**、401/402/5xx 语义 + **失败分类重试（连接失败/429/5xx 指数退避 3 次；读超时绝不重试；401/402/400 不重试）**（替代 weixin_client 的数据获取部分） |
| 3 | `core/service/video.py` | `_fetch_author_videos_from_backend` / `_fetch_author_replays_from_backend` 内部换源走 TikhubClient；`sync_and_get_new_videos` / `add_author_latest_videos` 入口加缓存判断；新增 `ensure_author_list_fresh(author_id)`（浏览入口） |
| 4 | `core/api/routers/video.py` | 前端接口**不改**；`get_author_videos` 读库天然命中；作者页打开时联动 `ensure_author_list_fresh`（静默后台） |

**网关化修正（v1.27；阶段一注 v1.85）**：L2 分两层——**网关侧 `author_list_snapshot` 共享响应快照**（键=`username|video_type|page`，raw=false 完整响应含 full_url+decode_key，TTL=120min；跨用户命中=浏览+下载双省，我们只付一次钱）+ **客户端本地 `channel_sync_state` 便利贴**（用户私有同步进度，从网关快照回填自己的 author_videos）。流程：客户端请求作者列表 → 网关查共享快照（命中=0 成本直接返回；未命中=调上游、落快照）→ 客户端把返回数据回填本地 author_videos（用户私有副本，秒开+隐私）。**阶段一（无服务器）**：缓存落本地 SQLite、逻辑同（存储无关接口化，§5①），网关共享形态=阶段二。下面表结构是客户端本地便利贴（用户层）。

**表结构**（客户端本地 `channel_sync_state`，方案 A"便利贴"：用户私有数据只有 author_videos 一份，本表只记同步状态）：

```sql
CREATE TABLE IF NOT EXISTS channel_sync_state (
    author_id         TEXT PRIMARY KEY,      -- 对应 authors.id（内部主键）
    source_author_id  TEXT NOT NULL,         -- TikHub username（v2_...@finder）
    last_sync_at      TEXT NOT NULL,         -- 上次同步时间（ISO）
    next_sync_at      TEXT NOT NULL,         -- 下次允许同步时间（= last_sync_at + TTL）
    video_cursor      TEXT,                  -- 短视频翻页游标（惰性续拉时记录）
    replay_cursor     TEXT,                  -- 回放翻页游标
    video_pages_fetched INTEGER DEFAULT 0,   -- 短视频已拉页数（策略 C 首拉 3 页计数）
    replay_pages_fetched INTEGER DEFAULT 0,  -- 回放已拉页数
    video_count       INTEGER DEFAULT 0,     -- 上次同步短视频数
    replay_count      INTEGER DEFAULT 0,     -- 上次同步回放数
    fail_count        INTEGER DEFAULT 0,     -- 连续失败计数
    failed_at         TEXT,                  -- 最近失败时间
    cooldown_until    TEXT                   -- 冷却截止（连续失败熔断）
);
```

**读取决策流程（前端打开作者页 → ensure_author_list_fresh）**：
- **无记录（首见作者）** → **策略 C 首拉：列表+回放各拉 3 页入库**（≈60-90 条，覆盖 90% 场景）→ 返回库数据（首次成本封顶 ≈ 6 页 × $0.01 ≈ $0.06/作者，通常 3-4 页 ≈ $0.03-0.04；**注：按 TikHub 按页价估算，红狐按次计价模型不同、成本更低（§6.1）**）
- **未过期**（now < next_sync_at）→ **0 成本**，直接读库返回
- **已过期** → 增量同步（见下）→ 更新 next_sync_at → 读库返回
- **冷却中**（cooldown_until > now）→ 直接读库返回，不调接口
- **翻页续拉（惰性，策略 C 核心）**：用户翻页超过已拉范围（video_pages_fetched < 目标页）→ 用 `video_cursor`/`replay_cursor` **逐页续拉**（$0.01/页，拉完入库并更新游标+页数）→ **已拉过的页翻回 0 成本**（本地读库）；大作者也只花"用户实际翻到的页数"，成本随用户行为走，永不失控

**同步细节（增量模式，TTL 过期后）**：
- `fetch_user_videos(username, raw=false)`：拉第一页（20 条级），整页 `video_id` 均已在库 → 停止（作者未发新）；有新的 → 新条入库，旧条互动数顺带更新；`video_pages_fetched < 3` 且首拉未完成 → 续拉补齐 3 页
- `fetch_live_history(username, raw=false)`：`lives[]` 同理（结构同 collection_videos 的 video）
- **惰性续拉（翻页触发的补拉）**：前端请求第 N 页 > 已拉页数 → 用 `video_cursor`/`replay_cursor` 逐页续拉到第 N 页，每页 $0.01，拉完入库、更新 cursor 与 pages_fetched；同页翻回 → 本地读库 0 成本
- **入库纪律（v1.13 收口）**：`video_id=id`（字符串）、`full_url+decode_key` 同响应配对（TEXT）、`duration` 列表毫秒 → 秒归一、`create_time` 秒级 → ISO、互动 5 列（read/like/fav/forward/comment）、`media_type` 过滤非视频、`file_size` 用 `duplicateFileSize` 或详情兜底
- **顺带更新作者资料**（nickname/头像，若响应带）——L1 的昵称/简介非权威资料在此刷新
- **失败熔断**：401/402 → 全局熔断（同 L1）；5xx → fail_count+1、冷却 1h、连续 3 次 → 24h 冷却；冷却期间浏览直接读库（0 成本）

**TTL（L2 缓存有效期）**：
- **取值 120 分钟（2026-10-27 用户拍板，省钱档）**：30=重新鲜度 / 60=平衡 / 120=重省钱（追更场景 2 小时新鲜度足够）
- **硬上限参考：48 小时**（列表项 `urlValidDuration=172800`，官方字段——列表链接官方有效期，超过必失效）
- **观察实验校准**：下载直链实测 TTL 出来后回填（v1.15 起；若实测远大于 48h 可放宽、若 ≈48h 维持 ≤48h）

**边界条件清单**：首拉 3 页中断（游标续拉补全）/ 翻页续拉失败（冷却后用户再翻时重试）/ 作者注销（列表报错 → 联动 L1 删映射）/ 空列表作者 / 回放为空（total_count=0）/ 并发同作者（加锁或幂等写）/ **读超时（v1.45 分级：红狐 30s / TikHub 90s，不白丢费；读超时绝不重试）** / 大整数 id（字符串入库）/ 大作者（>3 页，成本随用户翻页走，永不失控）。

**验收标准（可测）**：
1. 首次浏览作者 → TikHub 恰好列表+回放各 1 页（或各 3 页内，按作者实际条数，`api_usage` 计数）；TTL 内刷新 10 次 → **0 次调用**
2. 作者发新视频 → TTL 过期后刷新 → **1 次调用（$0.01）**，只补新增 1 条，旧视频计数不翻倍
3. **翻页（策略 C）**：翻到第 4 页（超出首拉 3 页）→ 恰好 1 次调用（$0.01）拉第 4 页；翻回第 2 页 → **0 次调用**（本地读库）；大作者翻到第 20 页 → 共 20 次调用，成本 = 翻页数 × $0.01，无全量烧钱
4. 下载走缓存列表的 full_url+decode_key 配对成功（同响应配对纪律）；列表无 file_size 时详情兜底可下载
5. 互动数顺带更新：过期刷新时旧视频互动 5 列更新为最新值
6. 连续失败 3 次 → 24h 冷却生效，冷却期内浏览 0 调用、页面照常出库数据

### 4.4 L3 详情缓存（完整规格，2026-10-27 落档 v1.16）

**通俗定位**：下载视频前先看"上次拿下载链接是什么时候"——链接还新鲜就白嫖直接用（0 成本）；快过期了才花 $0.01 刷新一次。搜索搜出来的视频没有下载链接（文档实锤：搜索命中项不含 media），必须调一次详情补链（$0.01，唯一必花点）。

**核心事实（v1.13/v1.15 实锤）**：
- 列表 `raw=false` 同步时已把 `full_url+decode_key` 配对入库（author_videos.url 现状语义=完整直链，`url+urlToken+X-snsvideoflag`，代码实锤）→ **作者页浏览的视频下载基本不需要调详情**
- 现状 `ensure_valid_url`（`core/service/search.py:313`）已实现"下载前校验 → 403 → 刷新"兜底，被 `task.py`/`compensation_manager.py` 调用——L3 是把它升级为"年龄判断 + 主动刷新"
- 现状 `_parse_video_object` 已有 duration 毫秒→秒归一、file_size 按分辨率估算兜底 → 换源后直接复用

**要动的落点**：

| # | 文件 | 动什么 |
|---|---|---|
| 1 | `core/utils/database/crud/models.py` | `AuthorVideo` 加 `url_updated_at`（链接入库/刷新时间）；`decode_key: int → str`（TEXT 迁移，v1.11 已定） |
| 2 | `core/service/search.py` | `ensure_valid_url` 增强：先按"链接年龄"判断，年龄 < 安全窗口直接放行（0 成本），≥ 窗口先刷新再放行；403 兜底不变 |
| 3 | `core/service/video.py` / `search.py` | 入库写 `url_updated_at`；搜索命中补链走 `fetch_video_detail(raw=false)`（$0.01） |
| 4 | 数据源层 | TikhubClient 提供 `fetch_video_detail`（同 L2） |

**表结构变更**（无新表，ALTER 两处）：

```sql
ALTER TABLE author_videos ADD COLUMN url_updated_at TEXT;  -- 链接入库/刷新时间（ISO），可空（老数据）
-- decode_key INTEGER → TEXT（迁移脚本，v1.11 已定）
```

**决策流程（下载前 ensure_valid_url 增强版）**：
- `url_updated_at` 为空（老数据）→ 视为年龄未知，走现状校验（稳妥）
- 年龄 = now − `url_updated_at`；**安全窗口 = 观察实验实测保质期 × 0.8**（保守系数）
- 年龄 < 安全窗口 → **直接用，0 成本**（常态路径）
- 年龄 ≥ 安全窗口 → **主动刷新**（fetch_video_detail $0.01）→ 更新 url + decode_key（同响应配对）+ `url_updated_at` → 下载
- 下载中 403 → 刷新重试（现状兜底，语义不变）
- **搜索命中项**（无 media）→ 详情补链（$0.01）→ 入库 url/decode_key/url_updated_at → 下载

**可观测性（成本可度量底座，接 SRE 纲领）**：
- 记录事件（event_bus / api_usage / log_dao）：url 命中（0 成本）/ 预刷新（年龄超窗）/ 403 刷新 / 搜索补链 / 刷新失败
- 汇总指标：**下载缓存命中率**（命中 ÷ 总下载）、403 率、每视频刷新成本、链接年龄分布
- 与观察实验互证：实测保质期 → 安全窗口初值；真实 403 分布校准窗口 → TTL 越用越准
- 产出：成本报告（每周/每次发布），喂定价模型

**可观测性四件套补全（v1.71，接 SRE 纲领，最小骨架防过度设计）**：
- **日志（Logs）**：api_usage（v1.23 DDL：每次调用一笔 endpoint/supplier/cost/duration_ms/成败/card_id）+ event_bus 事件日志（已有）——地基
- **指标（Metrics）**：从 api_usage 聚合——L1 缓存指标（命中率/403 率/刷新成本/年龄分布，已有 527 行）+ **供应商维度**：错误率、P95 耗时、双供应商调用占比（聚合查询即可，不新建设备）
- **告警（Alerts，最小 3 条，阶段二上线启用）**：①成本超周预算（api_usage 周聚合 > 阈值）②错误率突增（连续 N 次 5xx/超时）③熔断触发（供应商切换）——通知=运营侧（日志/巡检人工看，**不建独立告警平台**）
- **追踪（Traces）**：request_id 贯穿 客户端→网关→柠檬→上游（复用 api_usage.biz_id/request_id，失败排查定位到跳）
- **明确不做**：独立监控看板/告警系统（阶段一自用=日志+报表足够；规模到了再上）

**日志埋点规范（v1.72，分级 + 必埋点清单，写代码时照此埋）**：
- **分级**：INFO=正常流程 / WARNING=可恢复异常（有兜底，不打扰用户）/ ERROR=失败需处理（必带 request_id+参数摘要+耗时，**不打卡密明文/key 明文**）
- **必埋点清单（按层）**：

| 层 | WARNING（可恢复） | ERROR（必须处理） |
|---|---|---|
| 上游调用（红狐/TikHub） | 单次 5xx/超时/429（重试前）、401/402（key 失效/欠费→提示充值） | 重试后仍失败、熔断触发 |
| 网关计费 | 余额不足（正常拦截，INFO 即可） | **扣点失败**（钱相关：扣了没调/调了没扣，必查）、幂等冲突异常 |
| 柠檬对接 | 柠檬 5xx（重试前） | 兑换失败、绑定失败、token 校验失败 |
| 下载/解密 | 下载中断（断点续传重试） | **下载最终失败、解密失败、校验不过（文件损坏）**——用户拿不到文件=最高优先级 |
| 缓存层 | 缓存刷新失败（惰性下次重试）、TTL 过期刷新 | —（兜底由 event_bus 记） |
| 自动更新 | 更新检查失败（静默不影响主功能） | 更新包下载失败 |
| 全局兜底 | — | **未捕获异常**（统一 handler 打 ERROR+traceback） |

**异常处理纪律（v1.73，try/catch 不空等）**：
1. **禁止空等/空转**：catch 到异常后必须三选一落地——**降级返回**（缓存兜底/提示用户）/ **有上限重试** / **熔断切换**（双供应商）；**禁止静默吞异常后继续等待**（无感知空等=最差行为，用户卡住还不知道）
2. **等待必带上限**：重试=固定次数 + 退避间隔（仅明确瞬时错误才重试，同动作失败 2 次即换通道）；超时=连接 5s / 红狐读 30s / TikHub 读 90s（v1.45），**禁止无限等待/空转轮询**
3. **读超时不重试**（v1.45：宁可等到干完，不白丢费）——读超时=等结果而非重试
4. **每次异常必打日志**：按 v1.72 埋点表分级（WARNING=可恢复 / ERROR=失败），**禁止裸 catch 不打日志**

**TTL/安全窗口**：初值 = 观察实验出数前用 **24h**（保守）；实验出数后 = 实测保质期 × 0.8（回填 v1.17）；48h `urlValidDuration` 仅约束列表链接，详情链接以观察实验为准。

**验收标准（可测）**：
1. 旧视频（库里有链接且年龄 < 窗口）下载 10 次 → **0 次详情调用**（api_usage 计数验证）
2. 构造年龄 ≥ 窗口的链接 → 下载前触发 **1 次刷新**（$0.01）后成功，`url_updated_at` 更新
3. 搜索命中新视频 → **恰好 1 次详情补链**（$0.01）后可下载
4. 403 兜底回归：人为过期链接 → 下载失败 → 自动刷新 → 重试成功（现状链路）
5. 命中率/刷新率可从 api_usage 出数，成本报告可交付

### 4.5 L4 搜索缓存（完整规格，2026-10-27 落档 v1.17）

**通俗定位**：用户搜"象棋"第一次花 $0.01，把结果记住 24 小时；当天再搜"象棋"（自己或别人）直接给缓存结果，0 成本。隔天第一次搜同词才刷新一次。

**关键事实（v1.17 修正）**：
- 前端搜索 = **搜作者**（`GET /api/search/authors?q=&exact=`，现状走**红狐 `searchUsers`（主）/TikHub `fetch_search`（备）**，2022 端口已弃用 v1.21，返回作者列表）→ **缓存对象是"关键词 → 作者列表"**，不是视频
- **作者集合按天/周变化**（新号注册/改名/平台收录），非"每次搜完有新作者" → TTL 可以 24h（用户拍板），**惰性刷新**（请求时判过期，过期才重拉，同 L1）
- 搜索结果不落业务表（作者库只存添加过的）→ **必须存结果快照**（新表 `search_cache`），不同于 L2 的便利贴方案

**要动的落点**：

| # | 文件 | 动什么 |
|---|---|---|
| 1 | `core/utils/database/crud/models.py` | 新增 `SearchCache` dataclass（结果快照） |
| 2 | `core/service/search.py` | `search_author` 加缓存判断：命中返回快照 / 未命中调供应商（红狐 searchUsers 主 / TikHub fetch_search 备）写缓存；无结果也缓存（短 TTL） |
| 3 | 数据源层 | 供应商客户端提供搜索端点（红狐 `searchUsers` 主 / TikhubClient `fetch_search` 备，实施时按前端场景确认入参） |
| 4 | 前端静态 JS（static/） | 搜索框 **300ms 防抖**（实施时核实现状有无，有则优化、无则加） |

**表结构**（新表 `search_cache`）：

```sql
CREATE TABLE IF NOT EXISTS search_cache (
    search_key   TEXT PRIMARY KEY,   -- 键：q|exact|page（如 "象棋|1|2"），含精确标志与页码
    result_json  TEXT NOT NULL,      -- 该页作者列表快照（搜索响应原样存，天然含 next_cursor 供续页）
    has_result   INTEGER NOT NULL DEFAULT 1,  -- 1=有结果 0=无结果（无结果只发生在 page=1，TTL 短）
    created_at   TEXT NOT NULL,
    expires_at   TEXT NOT NULL       -- created_at + TTL
);
```

**决策流程（search_author 改造）**：
- 命中且未过期 → 返回快照，**0 成本**
- 未命中/过期 → 调**红狐 `searchUsers`（主，¥0.04）/ TikHub `fetch_search`（备）**→ 写缓存（有结果 TTL=24h）→ 返回
- **无结果**（空列表，仅 page=1 会发生）→ 也写缓存，**TTL=1h**（防同词反复烧钱 + 防新号上线后长时间误判）
- **翻页续拉（v1.20 补丁）**：请求第 N 页（N>1）且该页缓存未命中 → **用上一页缓存 result_json 里的 `next_cursor` 直接续拉**（$0.01/页）→ 写该页缓存；已缓存页翻回 → **0 成本**。不带页码缓存的翻页需重搜第 1 页拿游标（2 次/页），带页码只需 1 次
- 失败/熔断 → 同 L1/L2：401/402 全局熔断、5xx 冷却、格式校验前置（空关键词直接拒）

**TTL（用户拍板）**：有结果 **24h**、无结果 **1h**；惰性刷新（不主动定时清，请求时判断）；**每页独立缓存、同 TTL**

**与上下层关系**：搜出作者 → 点进去走 L2（作者列表缓存）；搜出视频（号内搜索场景）→ 下载走 L3 补链；L4 只省"搜索动作"本身

**验收标准（可测）**：
1. 同一关键词（有结果）搜 10 次 → **红狐调用 1 次**（api_usage 计数）
2. 无结果词搜 10 次 → 调用 1 次；1h 后同词再搜 → 允许重试 1 次
3. `exact=true/false` 同词不同键，各自独立缓存（互不污染）
4. 作者列表快照完整可还原（前端渲染字段不缺失）
5. 5xx 连续 3 次 → 冷却 24h，期间搜索直接透传报错不烧钱重试

### 4.6 L5 下载去重 + 前端冷却（完整规格，2026-10-27 落档 v1.18）

**通俗定位**：最外层保险——"重复**操作**不花钱"。同一个视频不重复下载；用户删了文件再下能自己发现；狂点按钮只触发 1 次。

**核心原则（SRE 权威源）**：**文件系统是权威来源，DB 的 `is_downloaded` 只是缓存标记**。判断"能不能下载"以磁盘 stat 为准，不信任静态标记。

**要动的落点**：

| # | 文件 | 动什么 |
|---|---|---|
| 1 | 新增 `core/service/downloader.py` | **自研直链下载模块（v1.21 拍板，替代 wx_video_download/gopeed）**：full_url 直接 HTTP 下载（带浏览器 UA），弃用 2022 端口；配合下载入口三态判断 |
| 2 | `core/api/routers/video.py` / `core/service/task.py` | 下载入口三态判断（见下）；后端"进行中"幂等锁（同一 video_id 只有一个下载任务）；task 模块下载执行器切到 downloader.py |
| 3 | `core/utils/file_validator.py` | 复用：stat 存在性 + **有效性校验（大小 > 0 / 对照下载 Content-Length 字节数，v1.82；`file_size` 字段降级纯展示不做校验，口径存疑见 v1.82）** |
| 4 | 前端静态 JS | 下载/刷新/添加作者按钮：点击后禁用 2–3 秒（防呆） |

**下载入口三态判断（点击下载时）**：
- `is_downloaded=0` → 正常下载
- `is_downloaded=1` + 文件**存在且有效**（大小 > 0，对照下载记录字节数 Content-Length，v1.82）→ 提示"已下载"，给"打开文件夹/播放"，不重复下
- `is_downloaded=1` + 文件**不存在或无效**（被删/移动/改名/损坏/0 字节/`download_path` 为空）→ **自动重置 is_downloaded=0** → 提示"文件已被删除/移动，重新下载" → 正常走下载

**前端冷却 + 后端幂等（防呆）**：
- 前端：按钮点击后禁用 2–3 秒（下载/刷新/添加作者）
- 后端：下载任务创建入口加"进行中"判断——同一 `video_id` 已有 running 任务 → 直接返回现有任务，不新建（防双开/并发狂点）

**边界清单（长期使用穷举）**：删除/移动/改名/换盘 → stat 兜底转重下；下载一半失败 → is_downloaded=0 天然安全；文件损坏/0 字节 → 有效性校验兜底；download_path 为空 + 标记已下载（老数据）→ 视为无效；双开并发 → 幂等锁；同步盘占位文件（OneDrive 等）→ 已知边界，本机单机工具暂不处理。

**验收标准（可测）**：
1. 下载完成 → 列表显示已下载；再点下载 → 0 次新任务（提示已下载），文件校验通过
2. **手动删除文件** → 再点下载 → 自动转重新下载成功，is_downloaded 重置为 0 → 下载后恢复 1
3. 构造 0 字节文件（或损坏）→ 点下载 → 视为未下载，重新下载成功
4. 同一视频并发点 10 次下载 → 只创建 **1 个**下载任务（幂等锁）
5. 狂点刷新/下载按钮 → 前端冷却生效，实际触发 ≤ 1 次

### 5. 亏钱风险与对策
> 阶段归属：**阶段二**（对外售卖场景；自用无盗刷/铺号风险）

| 风险 | 场景 | 对策 |
|---|---|---|
| 冷启动铺号 | 新作者无缓存，全量拉取每作者 ≈¥3.8 | 按次/按作者计费兜底 + 每日新作者配额（≤10/天）+ 列表分页上限 |
| 高频刷新 | 用户狂点刷新 | 同作者冷却 5 分钟 + L2 缓存强制命中 |
| URL 过期重复调用 | media 过期触发详情刷新 | L3 分层失效（key 长/media 短）+ ensure_valid_url 复用 |
| 恶意滥用/脚本 | 脚本循环刷 | **时间+点数双限制（成本封顶）+ 一卡一机 + 并发≤5 + 全局 QPS 兜底**（v1.28：不做账号体系与频率限流，防亏靠商业模型自保） |
| 规模化 RPS | 免费 10RPS 不够 | 买提速（20RPS $5/月）计入固定成本 |
| 汇率波动 | $ 计费、¥ 售卖 | 定价按 $ 锚定或定期调价 |

### 6. 待拍板（新增）
> 阶段归属：**混合**——#7 缓存落地=阶段一；#6 商业化形态 / #8 配额冷却=阶段二

| # | 项 | 默认建议 |
|---|---|---|
| 6 | 商业化形态 | **✅ 已拍板（2026-10-28 用户确认）：点数 × 时长卡型为唯一策略**——收费=点数 + 时长（1 天 3 点 / 3 天 10 点 / 7 天 25 点 / 30 天 100 点，v1.33 唯一真相源）；**早期「A 单作者月卡 + C 按条 + B 打包」形态废弃**（v1.44 确认：不做单作者维度、不做按条计费、不做打包档） |
| 7 | 缓存落地 | L1–L5 全上（L2/L3 为本版必做，否则毛利不成立） |
| 8 | 配额与冷却 | 每作者日拉取配额 + 5 分钟冷却，与定价绑定（防铺号亏本） |

## 表结构设计（TikHub 化后实体关系评估，2026-10-27）
> 阶段归属：**混合**——现有表 4 必改=阶段一；缓存新表（channel_alias/author_list_snapshot/search_cache）=阶段一本地实现；api_usage=阶段一建表（成本日志）、阶段二启用对账；card 表两阶段都不建（柠檬为真相源）

基于 `core/utils/database/base.py` 全表结构（authors / author_videos / download_tasks / task_log / resume_states）对照 TikHub 契约 §3/§4 数据模型逐字段评估。

### 1. 现有表兼容性结论：核心可不大改，但有 4 个必改点

| 表 | 兼容性 | 必改点 |
|---|---|---|
| authors | ✓ 语义吻合：`source_author_id` 可直接承担 TikHub `username`（作者主键）；name/bio/avatar_url/latest_publish_date 与 TikHub 返回同构 | **① 无需新增 channel_id 列**（v1.78：L1 解析主键=分享链接 link；channel_id 仅作者认证增强场景需要，来源=`fetch_channel_info` v1.79 实测 200，实施时如接入再定列）；资料字段每次拉列表顺带覆盖更新 |
| author_videos | ✓ `object_nonce_id`/`url`(media)/`spec`/`video_type`/`create_time` 全部对上；`decode_key` 列已存在 | **② 新增 `export_id`/`share_url` 列**（链接直下：用户贴的短链解析出 export_id 先落库，避免重复解析）；**③ 主键语义对齐：`video_id` 应= TikHub `object_id`**（64 位大整数按字符串存），否则同一视频重复入库破坏去重 |
| download_tasks | ✓ url+key+spec 与 create2 链路完全同构，不动 | — |
| task_log / resume_states | ✓ 与数据源无关，不动 | — |

**④ decode_key 格式已实测（v1.69 收口）**：TikHub 返回的 `decode_key` **=字符串（9 位纯数字）**——契约 §4"大整数按字符串处理"规范实测确认；Python 解密模块按字符串读（v1.40 Go 透传已不存在），列类型统一 TEXT 无碍。

**索引补充**（现有仅 author_id / video_id / status 三个索引）：
- `author_videos(video_type)`——列表按类型分页（videoListRender 高频路径）
- `author_videos(create_time)`——按发布时间排序/增量
- `download_tasks(video_type)`——任务列表按类型过滤

### 2. 新增表清单（v1.23 修正：替代 v1.6 旧方案）

> **⚠️ v1.27 网关化修正（2026-10-28）+ v1.85 阶段注**：商业化架构定为 C/S 中转后，缓存分两层——**省钱层在网关共享**（L1 `channel_alias` / L2 **`author_list_snapshot` 响应快照** / L4 `search_cache`，跨用户跨机器命中=我们只付一次钱，不绑卡密/用户/设备，只认数据新鲜度），**用户层在客户端本地**（author_videos / L3 链接列 / download_tasks / 文件校验，隐私+秒开）。v1.23 曾废除 `author_list_cache` 改 `channel_sync_state` 便利贴——那是本地应用架构的产物；网关化后**恢复网关侧响应快照**（author_list_snapshot），`channel_sync_state` 定位改为客户端本地同步状态便利贴。`card` 表在 v1.26 已废除（柠檬为卡密真相源）。**阶段一实现口径（v1.53/§5①）**：阶段一（自用、无服务器）缓存全部落**本地 SQLite**（同表结构、字段不变），缓存逻辑按「存储无关」接口化实现，阶段二把同一套逻辑上移到网关 DB（只换存储层，零返工）；下表「（网关）」标注为阶段二挂载形态。

| 表 | 用途 | 关键字段 | 对应层 |
|---|---|---|---|
| `channel_alias`（网关） | 分享链接 → username+nickname 映射（共享省钱） | link PK（分享短码）、username、nickname、source、created_at、updated_at；TTL 1 年+惰性失效，下游验证兜底 | L1 |
| `author_list_snapshot`（网关，v1.27 恢复） | 作者作品/回放列表**完整响应快照**（raw=false，含 full_url+decode_key）——跨用户共享省 TikHub 钱 | 键=`username\|video_type\|page` PK、payload_json（原样存，含 next_cursor）、fetched_at、expires_at（=fetched_at+120min） | L2（TTL=120min，分页策略 C） |
| `search_cache`（网关） | 搜索响应快照（共享省钱） | 键=`q\|exact\|page` PK、result_json（含 next_cursor 原样存）、has_result、created_at、expires_at | L4（有结果 24h / 无结果 1h） |
| `channel_sync_state`（客户端本地） | 作者同步状态便利贴（用户私有：自己库的同步进度） | author_id PK、source_author_id、last_sync_at、next_sync_at、video_cursor/replay_cursor、video_pages_fetched/replay_pages_fetched、video_count/replay_count、fail_count、failed_at、cooldown_until | 客户端 L2 私有副本 |
| `api_usage` | TikHub 调用计量（成本账，网关侧） | 见下方 §「商业化授权形态（v1.23）」完整 DDL | 成本/对账 |
| ~~`card`~~ | **已废除（v1.26）**——柠檬卡密为真相源 | 禁止按旧表建 | — |

> `api_usage` 是商业化「赚差价」的地基：定价、对账、防滥用（限流）都靠它，本版即建（User Story 18 调用次数可计量）。

### 2.5 商业化授权形态（v1.23 拍板：卡密 + 点数 + 一卡一机，不做用户系统）
> 阶段归属：**阶段二**（商业化收费闭环；阶段一不涉及）

> 商业模式 = **B 方案（C/S 中转）**：客户端（现有桌面壳）→ 我们服务器后端（路由 + 缓存 + 记账）→ **上游供应商（红狐主 / TikHub 备，我们充值付费）**；差价 = 我们收用户的钱（点数×单价）− 我们付上游的成本（api_usage.cost 合计）。
> 行业对照（2026-10-28 查证）：视频下载器行业（4K Video Downloader / Video DownloadHelper）主流=授权制（买断/订阅/VIP，自己逆向自己爬，无供应商差价概念）；API 中转行业（AI 中转站）核心机制=**服务端反向代理 + 计费拦截 + 倍率加价**（爱范儿/36氪报道），计费必须在代理层；**"客户端直连 + 本地扣点"赚差价无行业先例（本地验证必被破解，IDM 本地授权破解案为例）**。我们自己的拾光AI 已验证"卡密—点数：按次扣费、失败自动退款"模式（知识库实锤，服务端语义）。

**拍板结论（2026-10-28 用户确认）**：
- **不做用户系统**（无注册/登录/账号/用户管理后台）；卡密号 = 身份
- **一卡一机**：卡密激活时绑定设备指纹，防共享
- 流程：用户激活卡密 → 服务端校验 + 绑定设备 + 返回点数 → 每次调**上游（红狐主/TikHub 备）**服务端扣点 → 余额不足提示购买
- 复用柠檬卡密系统发卡/兑换逻辑；设备换绑（换机/重装）走客服或自助换绑码（后续迭代）
- 定价：1 次调用 = 1 点（点单价自定，倍率 = 定价空间）
- **卡型规格（v1.33 定稿，唯一真相源）**：

| 卡型 | 时限 | 点数 | 售价 | 每点卖价 | 每点成本 | 倍率 |
|---|---|---|---|---|---|---|
| 1 天体验卡 | 1 天 | 3 点 | ¥0.9 | ¥0.30 | ¥0.07 | ≈4.3 倍 |
| 3 天卡 | 3 天 | 10 点 | ¥1.9 | ¥0.19 | ¥0.07 | ≈2.7 倍 |
| 7 天卡 | 7 天 | 25 点 | ¥2.9 | ¥0.116 | ¥0.07 | ≈1.7 倍 |
| 30 天月卡 | 30 天 | 100 点 | ¥9.9 | ¥0.099 | ¥0.07 | ≈1.4 倍 |

> 定稿依据（2026-10-28）：成本锚 1 点=¥0.072≈0.07（汇率 7.2）；4 档全毛利恒正；缓存命中 0 成本用户照扣 1 点=纯赚，真实毛利 ≥ 账上。量大优惠（买得越多每点越便宜）。["https://docs.newapi.ai/en/docs/guide/feature-guide/admin/system-setting-advanced","https://doc.newapi.pro/guide/console/settings/rate-settings/","https://oneapi-doc.apifox.cn/doc-3703372","https://stripe.com/docs/products-prices/pricing-models?locale=es-ES"]

**④ 防滥用（v1.28 拍板：靠商业模型自保，限流只留服务器保护）**：

> **核心结论：防亏不需要限流**——时间+点数双限制 = 成本天然封顶。**任何卡密对上游的成本贡献 ≤ 卡点数 × 单次成本上界**（v1.41 双供应商成本锚：红狐优先实际 ¥0.04/次 < TikHub ¥0.072/次，¥0.072 为保守上界；永远封顶），加上"**扣点先于调用**"（余额不足直接 429，根本不调上游），定价覆盖最大成本即毛利恒正：1 天 3 点全用满成本 ¥0.22 < 售价 ¥0.9；30 天 100 点全用满成本 ¥7.2 < 售价 ¥9.9（27.3%，红狐优先后实际毛利更高）。

- **砍掉**：卡密/设备/IP 维度频率限流（点数封顶已防脚本烧钱，脚本烧完点数余额不足自然熔断）；连续超限熔断（同上，无需另建）
- **保留（服务器保护，仅 2 个轻桶）**：单卡密**并发上限 ≤5**（防瞬时打爆网关）；**全局 QPS 兜底**（防多卡同时打）
- **扣费与限流顺序**：鉴权 → 扣点（余额不足 429 不调上游）→ 限流（并发/全局桶）→ 业务；超限 429 + Retry-After，**不扣点**

**接入柠檬前置检查（v1.25 新增，引用 ADR-062/086）**：
- 新建 app 时 app 名/简介为中文 → **必须确认连接层 charset 已修复**（`DATABASE_URL` 带 `?charset=utf8mb4`，ADR-062 A+B 已上线），否则 app 中文名会乱码
- 建完 app 后**立即验证 app 名在后台显示正常**（「号匣」非乱码；2026-10-28 已更名完成）
- 存量乱码修复（apps.id=1 两列，ADR-086）为柠檬侧历史问题，与本版接入无阻塞关系；巡检脚本（mojibake 特征 SQL）已纳入巡逻计划

**服务端新表（商业化）**：

> ⚠️ **v1.26 架构修正（2026-10-28）**：原 `card` 表**废除**——柠檬后台为卡密唯一真相源（源码实证：兑换 `redeem-by-app` 幂等、一卡一机 `MachineBindMode.one_card_one_device` + `KamiDeviceBinding` 绑定表、扣点 `consume` 自带 biz_id 幂等 + min/max + 自动记设备、余额 `get_points_balance_summary`、用户凭证 `create_user_access_token`）。**我们自建 card 表/幂等表/扣点事务全部砍掉**，网关只做编排层（无感建 EndUser → 兑换 → 绑定 → 扣点透传）。仅保留 `api_usage`（成本账，柠檬没有 TikHub 成本概念）。

```sql
-- 供应商调用计量（成本账：只记我们实际付给供应商的真实花费）
-- v1.41：supplier 列新增——红狐/TikHub 双供应商并存后，必须记实际走了哪家才能算每笔赚/亏
CREATE TABLE IF NOT EXISTS api_usage (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    card_id     TEXT,                -- 发起调用的卡密号（关联柠檬 Kami.kami_code；无卡密 = 内部/调试）
    endpoint    TEXT NOT NULL,       -- 端点名（fetch_video_detail 等；= route_rate.route_id / supplier_cost.route_id）
    supplier    TEXT,                -- v1.41：实际供应商（redfox / tikhub；缓存命中/失败不调用供应商=NULL）
    cost        REAL NOT NULL,       -- 本次付给供应商的费用（人民币分口径，取 supplier_cost.cost_cny_cents；失败=0）
    points      INTEGER NOT NULL DEFAULT 0,  -- 本次扣用户点数（定价倍率，可调；柠檬 consume 侧扣）
    ok          INTEGER NOT NULL,    -- 1=成功 0=失败
    http_status INTEGER,             -- 响应码（200/401/402/429/5xx，排查用）
    cache_layer TEXT,                -- 由哪层缓存过期触发的调用（L1/L2/L3/L4/NULL=用户直接）
    error_code  TEXT,                -- 失败原因（401/402/余额/超时 等）
    duration_ms INTEGER,             -- v1.45：本次调用耗时（毫秒），P95 观测驱动超时值调参
    called_at   TEXT NOT NULL        -- 调用时间（ISO）
);
```

**api_usage 写入纪律（P0，v1.41 更新）**：
1. **只记真实供应商调用**——缓存命中 0 成本不记（api_usage = 实际花费；命中率看真实调用数随部署下降）
2. **成功失败都记**——失败不扣供应商钱（红狐非 200 / TikHub 非 200 均不计费）但必须留痕（401/402/429/5xx 次数 = 故障排查关键）
3. **supplier 必记**——双供应商并存下，同一 endpoint 可能走 redfox 或 tikhub，成本不同；漏记 supplier = 对账失真（P0）
4. **cache_layer 标注**——看出 L1-L5 各层省了多少、哪层失效最勤
5. 对账：`SUM(cost)`（我们付供应商，按 supplier 分组）vs `SUM(points)×单价`（我们收用户）→ 差价；`SUM(cost)` vs 红狐/TikHub 后台余额定期核，防异常扣费

**② 鉴权 + 扣费（2026-10-28 柠檬对齐版，源码实证）**：

> 原则：**柠檬是卡密真相源，网关只做编排层**。所有"钱"的逻辑复用柠檬，网关自建只剩编排 + api_usage。

| 能力 | 柠檬现成接口 | 我们自建？ |
|---|---|---|
| 卡密生成/规格 | admin specs generate（lemon-kami-admin 技能已通） | ❌ 复用 |
| 兑换（幂等） | `POST /points/redeem-by-app`（X-App-Id/Secret 明文比对，卡密不可重复用） | ❌ 复用 |
| 一卡一机绑定 | `MachineBindMode.one_card_one_device` + `KamiDeviceBinding`（admin/devices.py 有管理控制台） | ❌ 复用 |
| 扣点（原子+幂等） | `POST /points/consume`（biz_id 幂等、min/max 限额、自动记 device_uuid/fingerprint） | ❌ 复用 |
| 余额/到期 | `get_points_balance_summary` | ❌ 复用 |
| 用户凭证（无感） | `create_user_access_token`（无注册无登录，激活即签发） | ❌ 复用 |
| **激活编排**（无感建 EndUser → redeem → 绑定 → 发 token） | — | ✅ 网关切片 |
| 设备指纹采集规范 | — | ✅ 客户端 |
| api_usage 成本账 | — | ✅ 网关（柠檬无成本概念） |

**激活流程**：客户端提交 卡密+设备指纹 → 网关无感建 EndUser（username=设备指纹 hash，防枚举）→ 柠檬 redeem-by-app（兑换入账）→ 绑定设备（一卡一机）→ 柠檬签发用户 token → 返回客户端。
**日常请求**：客户端 带 token + biz_id(UUID) → 网关验 token → 柠檬 consume（amount=1、biz_id=request_id 幂等、自动记设备）→ 缓存命中逻辑照旧 → 记 api_usage → TikHub 5xx 退回（柠檬 refund）。
**边界**：用户感知=无注册无登录，激活卡密即自动获得凭证；换机=客服换绑（旧 token 吊销）。

**③ 计费配置（v1.29 拍板：配置表驱动计费 + 价格永不在客户端）**：

> **行业查证（2026-10-28，3 来源族）**：配置表驱动计费是行业标准——one-api/new-api（同行 AI 中转站）"倍率设置=计费核心配置、Per-call Billing=Fixed Price×倍率、Cache Billing=命中按比例计费"；AWS/Azure API 网关按调用计费表驱动；Stripe "Product+Price 对象分离，价格是配置可改、代码不硬编码"。**我们的两张表结构与行业对齐，非自定义**。

**核心架构原则：价格永不在客户端**——客户端是"哑终端"，只发请求、只显示点数余额，**从不显示 ¥ 价格**（价格在买卡那一刻由客服价目定）。改价即时生效、无需 OTA/更新/通知：
- 改售价 → 客服卖新卡用新价（已售卡不受影响）
- 改扣点 → 服务器改 route_rate 一行，下一请求立即按新规则扣（客户端无感）
- 改汇率/倍率 → 只影响我们毛利计算（用户完全无关）

**两张表（我们独有的计费参数；卡密本身柠檬管，不重复建）**：

```sql
-- 路由费率表（收侧：每个路由扣用户几点）——改扣点改这里
-- 架构边界（v1.37）：网关=单产品起步（当前仅 haoxia）；预留 product_id 维度，
--   未来多产品共用网关时改复合主键 (product_id, route_id) 即可合并，无需重建
-- v1.41 行业对齐（收/支分离，one-api/new-api 渠道维度独立定价）：本表只存"收"（扣用户点数），
--   "支"（上游成本）按供应商拆到 supplier_cost 表；upstream_cost_cents 列保留为兜底默认（弃用中）
-- v1.62 新增 cache_points（缓存命中扣点分级，命中值 0.1 象征性）：0=命中免费（合集顺风车/后台同步） / 0.1=象征性（用户主动操作命中，用户感知≈0） / 1=同价；
--   扣点只发生在"用户主动操作触发上游"时；后台自动行为（监控/同步/顺风车）0 扣点；billing_config.cache_discount 为未配时的兜底比例
CREATE TABLE IF NOT EXISTS route_rate (
    product_id          TEXT NOT NULL DEFAULT 'haoxia', -- 产品维度（预留扩展：拾光AI/切片并入时按产品隔离费率）
    route_id            TEXT PRIMARY KEY,   -- 端点名（= api_usage.endpoint）
    route_name          TEXT NOT NULL,      -- 人类可读名（跨号搜索/作者作品/…）
    points              INTEGER NOT NULL,   -- 扣用户点数（1 点=1 次操作，真实调用全价）
    cache_points        REAL    NOT NULL DEFAULT 0, -- 缓存命中扣点（v1.62：0=免费/0.1=象征性/1=同价；未配时按 billing_config.cache_discount 兜底）
    upstream_cost_cents INTEGER NOT NULL,   -- [弃用 v1.41] 兜底默认成本（人民币分）；实际成本以 supplier_cost 为准
    active              INTEGER NOT NULL DEFAULT 1,
    updated_at          TEXT NOT NULL
);

-- 供应商成本表（支侧：每路由 × 每供应商的实际上游成本，人民币分，避浮点）
-- v1.41 新增（2026-10-28 拍板，行业对齐：one-api/new-api 渠道维度独立计价、收支持分离）
-- 收益：接入新供应商不改代码只加行；api_usage 记 supplier 后每笔对账可算赚/亏
CREATE TABLE IF NOT EXISTS supplier_cost (
    route_id       TEXT NOT NULL,      -- 端点名（= api_usage.endpoint / route_rate.route_id）
    supplier       TEXT NOT NULL,      -- 供应商：redfox / tikhub（后续第三家直接加行）
    cost_cny_cents INTEGER NOT NULL,   -- 上游成本（人民币分）：红狐广域库=4/实时=6/字幕 submit=30、TikHub 微信系=7.2（USD0.01×7.2）
    active         INTEGER NOT NULL DEFAULT 1,  -- 1=可用（红狐优先路由先查 active=1 且成本最低）；0=停用（供应商挂/降价切换）
    updated_at     TEXT NOT NULL,
    PRIMARY KEY (route_id, supplier)
);
-- 路由优先级（v1.41）：同路由多供应商时选 active=1 且 cost_cny_cents 最低者（当前=红狐优先、TikHub 兜底）；
--   供应商失败熔断（连续 5xx/超时）→ 置 active=0 自动切另一家，冷却后恢复；不搞权重轮询（2 家无必要）
--   v1.45：熔断切换=网关服务器级（非用户级），对客户端透明；阈值/冷却细节见下方「熔断切换设计（阶段二实施）」

**熔断切换设计（v1.45 落档；v1.83 修正：供应商级熔断提前到阶段一，计费级熔断仍阶段二）**——防供应商单点故障，对客户端透明生效：
- **层级**：客户端 → 我们的网关（服务器）→ 上游（红狐/TikHub）。熔断发生在**网关层**，对客户端完全透明（客户端只连网关，不知道背后切换）；不是用户级兜底
- **粒度**：当前按**供应商全局**熔断（仅 2 家）；预留按 (route, supplier) 细化（未来供应商增多再拆）
- **触发**：该供应商**连续 3 次失败**（5xx / 读超时 / 连接失败均计入）→ 熔断
- **动作**：熔断期间该供应商视为不可用（等同 active=0），新请求直接走另一家（**不白等主源超时**）
- **冷却与半开**：熔断 60s 后自动进入半开状态——放 **1 个探测请求**：成功 → 恢复 active=1（新流量切回主源）；失败 → 继续熔断 60s
- **状态**：连续失败计数在内存（每进程）；active 落库（supplier_cost.active）——重启后按库恢复、计数重新累计
- **记录**：api_usage.supplier 记实际走的供应商（熔断切换期间自然记成另一家，对账不受影响）

-- 全局计费配置表（$↔¥↔点转化参数）——汇率/倍率改这里
-- 多产品扩展：key 按产品前缀区分（如 haoxia:fx_usd_cny / shiguang-ai:fx_usd_cny），天然支持
CREATE TABLE IF NOT EXISTS billing_config (
    key         TEXT PRIMARY KEY,           -- [product:]key（如 fx_usd_cny / haoxia:fx_usd_cny）
    value       TEXT NOT NULL,              -- 值（存字符串，读时按类型转）
    value_type  TEXT NOT NULL DEFAULT 'decimal',  -- decimal / int / text
    description TEXT,
    updated_at  TEXT NOT NULL
);
```

**初始配置**：`fx_usd_cny`=7.2（汇率锚）；`point_price_cny`=0.1（点单价基准，定价锚）；`cache_discount`=0.1（缓存命中扣点兜底比例，v1.62：route_rate.cache_points 未配时按此；显式配优先）；`timeout_connect`=5（s，统一连接超时）；`timeout_read_redfox`=30（s）；`timeout_read_tikhub`=90（s，v1.45 超时分级，改表不改代码）。

**成本锚换算（好算）**：1 点 = 1 次调用 = 上游成本 **红狐 ¥0.04（主，v1.41）** / TikHub ¥0.072（备，$0.01×汇率 7.2）→ 口算锚 **0.04–0.07 元/点**，表里存精确值（supplier_cost：红狐 4 分 / TikHub 7.2 分）。卡型倍率：1 天 3 点 ¥0.9（每点 ¥0.30 ≈ 4.3 倍）/ 3 天 10 点 ¥1.9（¥0.19 ≈ 2.7 倍）/ 7 天 25 点 ¥2.9（¥0.116 ≈ 1.7 倍）/ 30 天 100 点 ¥9.9（¥0.099 ≈ 1.4 倍）——量大优惠、毛利恒正。**缓存命中扣点分级（v1.62 终版，route_rate.cache_points=0.1 象征性）**：命中 0.1（≈¥0.01 用户无感、成本 0 纯赚）/ 后台自动 0 扣点 / 下载与 L1 旧数据 0 点——扣点只随用户主动操作触发上游；对账=真实调用成本 + 缓存命中纯赚分开算（毛利 = 收入 − 真实成本，缓存命中收入=纯毛利不稀释毛利）；v1.61"全免"与 v1.62 首版"0.5"均被 0.1 终版取代。

**计费纪律（P0）**：
1. **代码零硬编码价格/点数/汇率**——网关所有计费从两张表读
2. **改价只改表**（运营人工可改，不动代码）；route_rate 缺失 = 该路由拒绝（防新端点没配费率被白嫖）
3. 网关启动全量加载到内存，改表 → 运行中刷新生效；api_usage 记账时快照当时配置（调价不影响历史对账）
4. **扣点规则（v1.28 后；v1.61 修订、v1.62 分级落表、命中值 0.1）**：5 个数据路由各 1 点/请求（跨号搜索/作者作品/直播回放/视频详情/sph 短号解析，翻页=1 点/页，真实调用全价）；3 个非数据路由 0 点（卡密激活/卡密状态/服务状态）；**下载不额外扣**（直链已含在列表/详情那 1 点）；**缓存命中扣点分级（v1.62 拍板，route_rate.cache_points 表逐路由配）**：高频易察觉路由（作者列表/视频详情/搜索/短号/作者主页/评论/直播）命中=**0.1 象征性**（≈¥0.01，用户几乎无感；成本 0 纯赚）；**后台自动行为 0 扣点**（标星同步/监控/合集列表顺风车——用户未主动操作，扣点=暴力；成本从售价毛利覆盖）；下载/L1 旧数据 0 点；v1.28"照扣 1 点=差价最大化"、v1.61"缓存命中全免"、v1.62 首版"0.5 半价"均被 **v1.62 终版"0.1 象征性"**取代（用户感知最优：易察觉场景近乎免费、无操作场景免费、真实调用全价）；失败退款（柠檬 refund）

**④ 配置管理（v1.30 拍板：Pydantic Settings 分工——静态配置走 Settings，动态配置走表）**：

> **现状**：网关切片未写代码，配置管理规范此刻定，写代码时照做。行业标准 = pydantic-settings（FastAPI 生态标配，12-Factor 配置外置）：环境变量 > .env 文件 > 默认值 三层加载，统一前缀。

**核心分工（两类配置，两种管理）**：

| 类型 | 例子 | 管理方式 |
|---|---|---|
| **动态配置**（运营随时改） | 汇率、倍率、路由扣点 | **数据库表**（route_rate / billing_config）——运行中改、审计留痕、人工可改 |
| **静态配置**（部署时定死） | API 地址、超时、UA、环境区分、**供应商 API key（v1.46：阶段一 .env / 阶段二服务器 env，客户端零 key）** | **Pydantic Settings**（env / .env / 默认值 / 统一前缀）——按环境注入、启动时定、类型安全 |

**Pydantic Settings 设计要点**：
- **统一前缀**：`REDFOX_`（REDFOX_API_KEY，v1.46 阶段一 .env）、`TIKHUB_`（TIKHUB_API_BASE / TIKHUB_TIMEOUT / TIKHUB_UA）、`LEMON_`（LEMON_API_BASE / LEMON_APP_ID）、`GATEWAY_`（GATEWAY_DB_URL）
- **三层加载**（pydantic-settings 内建）：环境变量 > .env > 默认值
- **密钥通道（v1.46 拍板，v1.75 修正旧"不进 .env"口径）**：**阶段一自用版=本地 `.env` 明文两行 REDFOX_API_KEY / TIKHUB_KEY**（项目根，打包排除、不入 git；自用不对外发可接受）；**阶段二=key 上收服务器 env（server-secrets 落库），客户端零 key**（防用户拿 key 绕过网关直连上游）——密钥与配置通道分离原则不变，落地按阶段区分
- **环境区分**：dev / prod 用不同 .env 或环境注入（GATEWAY_ENV）
- 记账/计费字段（points/cost）**禁止**放进 Settings——它们是运营数据不是部署参数

**⑤ 用户提示文案（v1.32 拍板：从用户视角，不替用户做决定）**：

> 原则：**用户提示一律从用户视角——只告知事实（当前状态）+ 给购买通道；不替用户做决定（不指定卡型/价格）**。卡型列表展示=不做（v1.32 明确砍掉，避免替用户选）。

| 场景 | 文案模板 |
|---|---|
| 余额不足 | 「点数不足（当前余额 X 点，本次需要 1 点）。请购买卡密后继续使用，联系客服购买即可。」 |
| 授权过期（真时间卡时间到） | 「授权已过期，点数已失效。请购买新卡密后继续使用。」 |

**⑥ 客户端激活交互（v1.34 拍板：行业标准 + 单卡规则 + 文案）**：

**① 用户旅程**：拿到卡密（客服发）→ 打开下载器 → 激活卡密（主界面第三 tab）→ 绑定本机（无感）→ 日常使用（状态区常驻剩余）→ 到期/换机（客服后台解绑）

**② 行业标准落定（2026-10-28 检索验证：点盾云一机一码 / EXE卡密网络验证系 / Freelancer 许可激活 / Windows 激活 UX / Windows microcopy 原则）**：
1. 激活入口：主界面明确入口（第三 tab）；首次使用可强制弹窗
2. 激活窗口：**单面板**——一个输入框 + 激活按钮；错误分门别类提示
3. 绑定：**首次输入卡密激活成功 = 绑定本机，纯无感**（无"确认绑定"步骤）
4. 激活成功反馈：立即弹成功 + **展示这张卡的信息**（剩余点数/有效期）；此后状态区常驻显示
5. 未激活/到期：软件能打开、功能锁死，常驻"需激活"提示；到期前提前提醒=可选增强
6. 换机：**已拍板进本版（v1.36 客户端自助解绑）**——第三 tab「我的卡」区域（已激活时显示当前卡信息+[解绑本机]按钮）；流程=点解绑→确认弹窗→调网关 unbind→成功提示→本机回未激活；技术=客户端→网关新增 unbind 路由（卡密路由 2→3）→柠檬 `/sdk/unbind`（sdk.py:2040），客户端哑终端不直连 SDK；**规则=一张卡限解绑 2 次**（网关计数，防转卖；正常换机 1-2 次够用），超限提示联系客服

**③ 单卡规则（2026-10-28 用户拍板）**：一个用户**同一时间只能有一张卡生效，不允许并行多卡叠加**（1 个月卡 + 2 个月卡叠加 → 拒绝）。
- **占用判定**：激活新卡前网关查用户 `available_balance`（get_points_balance_summary，排除过期 lot）——**available_balance > 0 → 拒绝激活**（提示"已有卡生效中"）；= 0 → 放行
- **语义对齐**：改造点 1 生效后 lot 到期=min(点数,时间) → 时间到期自动 available=0 → **到期/点数用完后可换新卡**（续费放行）
- **实现位置**：网关 activate 编排层（**服务端权威判断，客户端不判，防绕过**）；柠檬 redeem 无此限制（同用户可 redeem 多卡、积分叠加——由网关拦）
- 边界：点数用完但时间未到 → available=0 → 允许激活新卡（新 lot 时间重新起算）——符合"只有可用点数的卡才算占用"

**④ 文案清单（2026-10-28 从用户视角审定：告知事实 + 给出口，不替用户决策）**：

| 场景 | 文案 |
|---|---|
| 激活成功 | 「激活成功，本卡已绑定本机。剩余 100 点，有效期至 2026-11-27。」 |
| 卡密无效/格式错 | 「卡密无效，请核对后重新输入。」 |
| 已被使用 | 「此卡密已被使用。」 |
| 已冻结 | 「此卡密已被冻结，请联系客服。」 |
| 已过期 | 「此卡密已过期。」 |
| 设备不匹配 | 「此卡密已绑定其他设备。如需换机请联系客服解绑。」 |
| 已有卡生效中 | 「您有一张卡正在使用中（剩余 X 点，有效期至 X）。请使用完或到期后再激活新卡。」 |
| 未激活状态 | 「未激活：请激活卡密后使用。」 |
| 状态区常驻 | 「剩余 92 星尘 · 2026-11-27 到期」（纯点数不限时卡仅显示「剩余 92 星尘」） |

**⑦ 架构边界与统一货币（v1.37 拍板：单产品起步 + 表预留多产品 + 货币统一=星尘）**：

> 背景：探讨"多软件共用网关 + 各自计费"的合理性（行业对照 one-api/new-api 统一计费、AWS API Gateway 多服务、Stripe Product+Price），并确定公司品牌语境下的货币命名（暗宇宙星夜微光意象 → **星尘 Stardust**，2026-10-28 用户拍板）。

**① 网关=单产品起步（现状不变）**：网关是下载器数据采集族垂直切片，只服务 **haoxia**；**表结构预留 product_id 维度**（route_rate / billing_config / api_usage 都带 product 列，默认 haoxia）——第 2 个产品接入=加几行配置即用，不推倒重建、不迁移。

**② 基础设施共用一套、业务数据按产品隔离**：
- 共用：一张 route_rate 表、一个网关、一套缓存层（省运维）
- 隔离：**卡密 + 点数余额按产品隔离**（柠檬 App 维度）——**haoxia** 的卡只能在号匣激活，余额按产品分
- **隔离原因**：各产品成本/定价策略不同（下载器搜索 红狐¥0.04/TikHub¥0.072 每次、生图 ¥0.03/次）；点数共用会"便宜点数跑贵服务"亏钱

**③ 统一货币=星尘（Stardust，代号 SD）**：
- 全链路统一叫"**星尘**"（柠檬规格名 / 界面 / 文案 / 代码 / 文档），**不引入第二货币**（钻石/积分等叫法不用）
- 1 星尘 = 1 次调用（下载器）；**每个产品 1 星尘的实际价值由各自 route_rate 扣点决定**（下载器 1 星尘=1 次搜索；生图 1 次可能扣 3 星尘）
- 命名出处：暗宇宙品牌意象（星夜微光粒子）——星尘=微小可积累的能量粒子，聚沙成塔；呼应 slogan"我们探索宇宙，也照亮每一个你"
- 旧文档/代码中"点/点数"为同义简称，新写一律用"星尘"

**④ 扩展边界**：卡密**跨产品**通用（下载器的卡激活生图）= 柠檬层大工程，本期不碰，后续单独决策；网关多产品共用同理（规模到了再启用 product_id）

**⑧ 客户端 UI 规范（v1.38 拍板：遵循暗宇宙设计系统，氛围层+操作区克制）**：

> 背景：下载器客户端前端将新建（卡密激活模块等），公司品牌资产/设计系统已定稿——UI 从一开始就按设计系统做，不与品牌资产脱节。2026-10-28 用户拍板"稍微有点特色就行"（平衡=氛围层有品牌味，操作区实用优先）。

**① 视觉底座（全部取公司定稿资产，不另造）**：
- 色彩：`tokens/color.json`——深空底 `#07070b`、面 `#0c0c14`、品牌主色 `#6d5cff`（按钮/选中）、强调 `#22d3ee`（星尘余额/链接/小面积）、渐变 `#6d5cff→#5a47e5`（仅氛围层）
- 字体：`tokens/font.json`——正文系统 sans 栈，卡号/星尘余额/等宽场景用 mono 栈（不引入联网字体）
- 意象：星夜微光（星环/光锥/星云/微光粒子）——**只用于氛围层**：激活页首屏辉光、空状态、加载态、徽标
- 语气：深邃、温暖、谦和、清晰（品牌关键词）——文案调性与"星尘"命名一致

**② 操作区克制原则（工具类软件）**：搜索/列表/下载等操作区**不游戏化、不重装饰**，信息密度合理、功能优先；品牌元素只做点缀（徽标/空状态/余额强调），不干扰操作效率。

**③ 实施纪律**：客户端前端（index.html + 各 JS 模块）动手前**必读公司前端规范**（`D:\暗宇宙\knowledge\content\design\`）+ tokens 正本；参考已对齐案例 ADR-042（livecaps 首屏视觉治理）。

### 2.6 自动更新机制（v1.25 收口 + v1.47 更新源定案：时机 + 状态机 + 容错 + 视觉 + 可靠性 + 标配防护）
> 阶段归属：**混合**——基础更新机制=阶段一；不引入授权/商业化校验（v1.66 已砍）

> **背景（v1.75 修正更新源）**：原 v1.25 方案"接柠檬 updates/check 做客户端更新"——**v1.47 已拍板改为复用 ADR-022 静态存储发布模式**：更新源= `lemon-kami-artifacts` 公共读桶（`…/haoxia/updates/latest.json`，指针人控切换，产品「号匣」），替代柠檬 updates/check；检查时机/状态机/防护清单（下方③④⑦）通用不变（源换了、机制相同）。客户端检查时机行业依据：Electron 官方启动 + 每 10 分钟 / Sparkle 默认 24h——"仅启动一次"偏离行业标准（更新送不达/安全修复滞后），**2026-10-28 用户拍板修正**，柠檬 docs 文档已同步修订（本地 clone）。

**① 术语**：全链路统一叫"**自动更新**"；"OTA"仅保留在接口路径名（updates/check），不再作为叫法。

**② 客户端检查时机**：**启动检查一次 + 后台每日静默检查一次**（低频不打扰、有更新才提示、更新必达）；跳过首次启动；不抄柠檬文档"仅启动一次"。

**③ 状态机（客户端唯一权威状态，事件驱动）**：
`idle → checking（后台，10s 超时）→ downloading（后台，不阻塞 UI，失败重试≤3 次退避）→ ready（通知条）→ installing（用户确认后，独立安装器）→ done`
- 无更新 / 用户稍后 / 任何 error → 静默回 idle（当天不重试）
- 连续失败 N 次 → 降级为仅手动检查（防骚扰）

**④ 分阶段容错**：
- 检查：后台线程、10s 超时、失败静默 + 日志、当天不再重试；前端零阻塞
- 下载：后台、断点续拉、退避重试 ≤3 次、sha512/签名校验、坏包丢弃
- 安装：只提示不强制、用户确认才装、失败可重试、**旧版本继续可用**、数据目录不受影响

**⑤ 前端视觉（最小打扰）**：检查/下载全程无视觉；下载完成显示**顶部通知条**"新版本 vX.Y.Z 已就绪（更新摘要），[立即重启] [稍后]"；更新失败静默（设置页常驻「检查更新」按钮 + 上次检查时间兜底，三种结果文案：已是最新 / 发现新版本 / 连接失败请稍后再试）。

**⑥ 交互反馈可靠性（防"点了没反应/断了没下文/卡死无感知"）**：
1. 点击必有即时反馈（按钮 loading 防重复点击）
2. 状态必先落盘（点击确认先写本地状态，崩溃后下次启动可恢复提示）
3. 安装器必独立进程（spawn setup 后主进程退出，安装不依赖主进程）
4. 失败必可恢复（安装中断 → 下次启动提示"上次更新未完成，重试？"）
5. 全程必有日志（update.log：每次点击/每阶段/每次失败）

**⑦ 标配防护清单（行业最常见，2026-10-28 用户拍板收敛版）**：

| # | 防护 | 解决 |
|---|---|---|
| 1 | 后台检查 + 超时 + 静默失败 + 设置页手动入口 | 连不上/无感知 |
| 2 | 后台下载 + sha512 校验 + 重试 ≤3 次 | 下载断/坏包 |
| 3 | 通知条 + 用户确认才装 | 强插打断 |
| 4 | 点击即反馈 + 状态落盘 + 独立安装器进程 | 点击无响应/中断 |
| 5 | **代码签名**（打包必做） | 杀软误报（高风险） |
| 6 | **数据目录与安装目录分离**（更新只换程序，绝不碰用户数据） | 更新丢数据（最高风险） |
| 7 | 安装器请求管理员权限（NSIS requestExecutionLevel） | 权限不足 |
| 8 | 安装失败 → 旧版继续可用（不覆盖旧文件） | 装坏 |
| 9 | 单实例锁 | 多开冲突 |

**明确不做（过度设计）**：装坏自动回滚旧版（靠"失败旧版仍在"）、强制更新（后置）、系统时间校验、磁盘预检、代理专项适配、32 位支持（只出 x64）。

**⑧ 运营纪律（ADR-063 教训）**：发版/发卡统一走香港底座（adminlm.hubapi.work），禁止 SSH 隧道连阿里云后台生成产物/卡密，防止双底座分裂。

**⑨ 柠檬侧修正**：`lemon-kami` 仓库 `docs/UPDATE_CLIENT_INTEGRATION.md`「零、检查时机」已改为"启动 + 每日静默"（本地 clone 已改，commit/部署时同步；柠檬为公共底座，服务端改动须回归测试——本次只改文档不动代码）。

### 3. 不做重构（低收益高风险项，记录在案）



- `authors.id` 与 `source_author_id` 双键**保持不动**：作者唯一身份约定为 `source_author_id = username`，不强行把主键改成 username（牵连 author_videos 外键，迁移风险高、收益低）；channel_id 列仅在可选辅助场景需要时再加（v1.78）。
- download_tasks / task_log / resume_states 结构冻结。

### 4. 「结构不是最优」的准确定性（2026-10-27，逐项查证 models.py + store.py + 字段使用）

**不是**「整体冗余很多」，也**不是**「实体分割不符合行业标准」——6 张业务表职责单一、边界清晰，是通用业务模型划分。真正的非优点是 3 类：

| 类别 | 项 | 定性 | 处置 |
|---|---|---|---|
| 真冗余（1 处） | `author_videos.author_avatar`：视频表存作者头像，且 `authors.avatar_url` 已存在（models.py 注释即 `contact.headUrl`，微信时代搬运痕迹） | 违反 2NF 部分依赖，应删 | TikHub 版删字段，头像统一走 authors 表 |
| 快照冗余（合理，非问题） | `task_log.username`、`download_tasks.create_time/video_type`（从视频表复制） | 日志/任务表快照是行业惯例（保留创建时点的历史事实，避免关联查询） | 保留 |
| 主键策略非标（核心问题） | ① `video_id` = 自造 16 位随机串（`store.py:22 generate_id` = secrets 随机），**未用平台自然键 object_id** → 同一视频重复入库必须额外判重（object_nonce_id/url），幂等成本高；L3 缓存被迫以 object_id 建复合键 ② `authors.id` 随机串 + `source_author_id` UNIQUE 双键间接层 | 行业标准：平台不可变 ID 作自然键直接当主键（upsert 幂等天然成立） | TikHub 版 `video_id` 直接= object_id（字符串）；authors 保留双键但身份唯一=username |
| 索引不足（3 个） | author_videos 缺 `(video_type)`、`(create_time)`；download_tasks 缺 `(video_type)` | 高频查询路径，规模后慢查询 | 补索引 |
| 待实测 | ~~`decode_key` 类型：模型标 int，TikHub 大整数规范下需实测~~ **已实测（v1.69）=str 9 位纯数字，统一 TEXT，Python 解密按字符串入参** | — | 已闭环 |

**结论：不需要推倒重构；修 3 类（删 1 冗余字段、video_id 对齐 object_id、补 3 索引）+ 建 5 张新表即可达到"最佳"。**

## 实施路线图（按优先级分部分 × 维度 × 点，2026-10-27）

### 第一优先级 P0：动工前置（不解决不可动工）
> 阶段归属：**阶段一**

- **维度：阻塞与实测**
  1. ~~TikHub 充值/Key 口径核验~~ **已核验（2026-10-27）**：密钥库（server-secrets）存在 **`TIKHUB_KEY`**（len=60，md5=f341020c83a2，明文未回显）——**key 已建**（命名 ≠ 契约占位 `TIKHUB_API_KEY`，契约"key 未建"说法过时，以密钥库为准）；**充值 $10 状态无法从密钥库验证**，需登录 user.tikhub.io 后台或实际调用确认（401=key 无效 / 报错余额不足=未充值）。剩余动作：更新知识库契约（占位名→实际名、状态回填）+ 实测调用
  2. **范围拍板**：作者直下（前端旅程对齐 TikHub 端点粒度）+ 前端减项是否正式进本版
  3. ~~**decode_key 格式实测**~~ **已实测（v1.69 收口）**：decode_key=**str（9 位纯数字）**，按字符串存（统一 TEXT）、Python 解密按字符串→int 喂算法（v1.70 端到端验证通过）；**剩余：无**
  4. **字段映射实测清单（7 项待实测，一次实测全收）**：① full_url 是否含规格参数 / 可否追加 X-snsvideoflag；② media 是否带 fileSize；③ create_time 格式（秒/毫秒/ISO）；④ duration 单位；⑤ 列表是否已过滤非视频；⑥ 搜索命中项字段路径（账号 username/nickname/头像）；⑦ live_history 是否带 read_count。**已实测收口（v1.13：⑦ 之外全收；v1.74 补测确认 ⑦ read_count 在列）**；任一不符 → 回填 Spec + 契约

### 第二优先级 P1：本版地基（数据层 + 缓存层，换源与前端减项的依赖）
> 阶段归属：**阶段一**

- **维度：表结构（Spec v1.6 修 3 类）**
  4. `authors` 不新增 `channel_id` 列（v1.78：L1 解析主键=分享链接 link；channel_id 仅作者认证增强场景，来源=fetch_channel_info v1.79，实施时如接入再定）
  5. `author_videos`：新增 `export_id/share_url` 列；**`decode_key` 改 TEXT**（TikHub 每次请求变化，INTEGER 语义作废）；**新增互动 5 列**（read_count/like_count/fav_count/forward_count/comment_count，官方命名）；删除冗余 `author_avatar`；`video_id` **已为平台自然键（v1.11 修正：入库即 obj.id，无需迁移）**
  6. 补索引：`author_videos(video_type)`、`author_videos(create_time)`、`download_tasks(video_type)`
- **维度：缓存层（5 张新表 + 4 层缓存）**
  7. 建表：`channel_alias`（L1）、`author_list_snapshot`（L2，v1.27 响应快照；旧名 author_list_cache 已废除）、`search_cache`（L4）、`api_usage`（计量）；**L3 无新表**（author_videos 加 url_updated_at，旧表 video_detail_cache 已废除，v1.23 禁止按旧表建）
  8. L1 落地：短号→username，TTL 1 年 + 惰性失效 + 下游验证兜底（拉取报错→删映射重取）
  9. L2 落地：作者作品/回放列表缓存 TTL **120 分钟（v1.15 拍板省钱档，48h 硬上限 urlValidDuration）**；打开界面秒开 + 后台静默刷新；响应顺带更新 authors 资料（免费追新改名/头像）
  10. L3 落地：**decode_key 不长期缓存（v1.11 实证每次请求变化）**；media 链接年龄安全窗口（出数前 24h 保守 = 实测保质期×0.8）；过期由 `ensure_valid_url` 触发刷新
  11. L4/L5：搜索缓存 **有结果 24h / 无结果 1h（v1.17 拍板）**；下载去重复用现有 DB（url/key/spec）

### 第三优先级 P2：本版主体（后端换源 + 前端减项）
> 阶段归属：**阶段一**

- **维度：后端换源（Spec v1.0 映射表 A 类 + 路由核对）**
  12. 新增 `redfox_client.py`（主）+ `tikhub_client.py`（备）（替代 `weixin_client.py` 数据获取 4 动作：search/user_videos/live_history/video_detail，同接口异实现）
  13. 16 个 `require_wechat` 门禁路由处置：search 3 / video 3 / task 2 → 门禁替换为 TikHub 连通+余额检查；inputer 3 / monitor 5 → 移除门禁
  14. 后端独有 6 路由：`wechat-status` 移除、`link-status` 语义改 TikHub、`service/start|stop|restart` **下线**（v1.40 拍板 Go 进程移除）、`task/download-all` 门禁替换
  15. 监控器：保留本体，数据源换 TikHub 低频（打开界面即同步 + 标星每天 2 次兜底，v1.22）；5 处新增微信耦合点（task.py:750、monitor.py:252、service_status_push.py、tencent_doc.py、cli/service.py）同步清理
  16. 新增薄适配路由（非聚合）：`share_url→作者`（fetch_video_detail）、`user_videos`、`live_history`、`video_detail` 一一对应 TikHub 端点
- **维度：前端减项（Spec v1.3 四类）**
  17. 微信依赖清理：67 处命中——videoOps 检测×2、死调用 `/api/status`、status.js 微信灯/toast、doc_sync_monitor 就绪判断×4、api.js 错误码、app/authorDetail wechat_connected 字段
  18. 「添加作者→同步入库」旅程移除：authorDialog 同步模式弹窗+4 步进度（约 300 行）、sync-new/add/add-all 入口×4
  19. 批量下载收敛：videoOps 3 处 batch-create → 1 处，去掉前置检测与诊断分支
  20. 新增「作者直下」入口：贴作者链接 → 列表直出 → 勾选/全选 → **自研直链下载模块**（v1.21 拍板，弃用 create2/2022 端口）

### 第四优先级 P3：商业化与后置（本版之后）
> 阶段归属：**阶段二**（商业化/对账/增强端点；短剧另行排期）

- **维度：商业化（Spec v1.4 起；**定价已定稿 v1.33/v1.44**，本节为实施项）**
  21. `api_usage` 计量接对账逻辑（本版已建表）：每次**上游调用（红狐/TikHub，supplier 列区分）**落库，支撑定价/对账/防滥用
  22. 定价表实施（**✅ v1.33/v1.44 已定稿：点数 × 时长 4 档卡（1天3点/3天10点/7天25点/30天100点）；早期 A 单作者月卡 + C 按条 + B 打包废弃**）
  23. 配额/冷却/防滥用：每作者日拉取配额 + 5 分钟冷却
- **维度：后置优化**
  24. 12 项收敛：34/43 裸 fetch 收敛到 api/ 封装、CSV/Excel 导入两步序列合并、escape 3 处去重、addAuthor keyword 伪装等
  25. 增强端点（**v1.75 修正归属**）：**合集（fetch_user_collections+fetch_collection_videos）已进本版 v1.54**、**评论（fetch_video_comments）与主页资料（fetch_user_profile）已进本版 v1.60**（懒触发+TTL 7 天）；**仅号内搜索（fetch_search_channel_videos）仍 P3 后置**
  26. 短剧版本另行排期（本版 Out of Scope）

**依赖链：P0 → P1（数据/缓存地基）→ P2（换源/减项）→ P3（商业化/后置）；P2 的 16/20 依赖 P1 的 5/7/8/9/10（video_id=object_id、缓存表先建）。**

### 5. 互动数据保存（用户 2026-10-27 要求：TikHub 返回的互动数必须入库）
> 阶段归属：**阶段一**

- `author_videos` 新增互动列（**官方命名，2026-10-27 文档实证**）：`read_count`（播放）、`like_count`（点赞）、`fav_count`（收藏）、`forward_count`（转发）、`comment_count`（评论）——此前预估的 view_count/favorite_count/share_count **弃用**；
- 数据来源（**文档实证**）：`fetch_user_videos` **列表每个视频自带上述 5 项互动数 + media（含 decode_key）**——同步/浏览一次调用同时拿齐列表、互动数、下载地址，"顺带更新互动数"**零额外请求成本成立**（原预估"详情最全"修正为"列表已全"）；`fetch_video_detail` 详情同字段（5 项一致）；
- 前端展示：作者页视频列表/详情显示互动数（User Story 12「视频详情可见」扩展，原仅评论数）。

## TikHub 文档比对结论（2026-10-27，OpenAPI + Apifox 官方文档 + 官方 Python SDK 三重核对）
> 阶段归属：**阶段一**（换源/字段映射的实施依据）

按用户指示"先看文档比对、后实测"，本轮完成三重文档核对（openapi.json 快照 / docs.tikhub.io Apifox 各端点页 / PyPI tikhub SDK 2.2.0 源码）。**结论：换源所需字段结构已在文档层确认，实测仅剩"与文档一致"的低成本验证。**

### 1. 核心端点字段结构（raw=false 精简结构，官方推荐做媒体下载；2026-10-27 全端点比对）

| 端点 | 入参 | 关键返回结构（JSON Path） | 互动数 | media |
|---|---|---|---|---|
| fetch_channel_id_to_username | channel_id（`sph…` 短号，pattern `^sph[A-Za-z0-9_-]+$`） | `data.channel_id`（回显）/ `data.username`（`v2_…@finder` 可直接喂下游）/ `data.nickname` / `data.desc`（可 null）；**未命中：username=null + `data.error`** | — | — |
| fetch_user_videos | username / last_buffer（首页空，`up_continue` 真时回传） | `data.username/nickname/count/up_continue/last_buffer`；`data.videos[N].id/object_nonce_id/username/nickname/title/create_time/location` | **videos[N] 自带 read_count/like_count/fav_count/forward_count/comment_count** | videos[N].media.{url,url_token,full_url,decode_key} |
| fetch_video_detail | object_id > export_id > share_url（三选一，object_nonce_id 可选提命中） | data 即单视频对象：id/username/nickname/title/create_time/object_type/location | data 自带同上 5 项 | data.media.{url,url_token,full_url,decode_key} |
| fetch_live_history | username / last_buffer / flag（默认 12） | `data.username/count/total_count`（**无回放=0**）/ `data.lives[]`：id/username/nickname/title/create_time；`continue_flag`/`last_buffer`；**下载=列表条目自带 media 直链，复用普通视频链路，不依赖 fetch_live_detail（v1.76 实测确认）** | lives[N] 自带 like/fav/forward/comment（**read_count 已实测存在，v1.74 确认**） | lives[N].media.{url,url_token,full_url,decode_key} |
| fetch_user_profile（增强） | username | `data.username/nickname/signature/head_url/region/fans_count`（**部分账号返回 0**）/feeds_count/like_count/fav_count/forward_count/friend_follow_count/live_duration_hours/original_flag/collection_count/verify_desc/linked_accounts[]（关联公众号）；另带 object[] 首屏作品 | 账号级统计（获赞/收藏/转发） | — |
| fetch_user_collections（增强） | username | `data.username/count/collections[]`：topic_id/name/desc/cover_url/feed_count/topic_type（示例 16） | — | — |
| fetch_collection_videos（增强） | topic_id（必填）/topic/username 可选提命中/last_buffer/topic_type（默认 16） | `data.topic_id/title/total_count/count`；`data.videos[]` 同作品列表结构（id/username/nickname/title 可 null/create_time）；`down_continue`/`last_buffer` | **videos[N] 自带 5 项互动数全** | videos[N].media.{url,url_token,full_url,decode_key}+cover_url/duration/width/height/media_type |
| fetch_video_comments（增强） | object_id（必填）/comment_id（可选，展开二级回复）/last_buffer | `data.object_id/comment_id/count/down_continue/last_buffer`；comments[N]：comment_id/nickname/username/head_url/content/like_count/reply_count/create_time/ip_region；raw=true 带全局计数 monotonicData.commentCount + countInfo | 评论点赞/回复数；raw=true 顺带全作品计数 | — |
| fetch_search_channel_videos（增强，号内搜） | username + query + cursor | `data.items[]`：title/desc/thumb_url/username/nickname/doc_id/type；`continue_flag`/`next_cursor` | — | **不带 media**（官方明确：命中项需再走 fetch_video_detail） |
| ~~fetch_search_videos~~（v1.39 修正：实为**搜视频**端点，非跨号搜索；搜作者=红狐 `searchUsers`（主）/ TikHub `wechat_search/v2/fetch_search` account 垂类（备）） | query + business_type（18 键，实测仅 all/account/article/video/sticker 返回数据）+ pagination | **响应 data 结构文档未展开**（入参 OpenAPI 已确认）；搜索命中项带 export_id/object_nonce_id → fetch_video_detail 链路（已闭环） | — | 经 detail 获取 |

**L1 缓存增强（v1.77/78 实证重写）**：L1 解析走 `fetch_video_detail(share_url)`，**一步返回 username+nickname 成对**（v1.77 实测 REAL-DATA）——L1 命中即可免费补作者昵称与 username 映射，不必额外调 profile；作者简介/头像等权威资料靠 L2 列表顺带更新（红狐列表项 headUrl/description）或 P3 profile；未命中语义（`data.bad_input`/`data.error`，v1.76/77 实测形态）正好支撑 L1「下游验证兜底」（拉取报错→删映射重取）。

### 2. 视频加密与下载纪律（文档实证，影响下载链路设计）

- **视频文件是加密的**：MP4 无法播放即加密，必须用 `decode_key` 解密；
- **每次请求返回新的加密链接与 decode_key**（即使同一视频）——**decode_key 必须与下载的加密文件来自同一次响应**，否则解密失败；
- **防盗链**：`url` 需拼接 `url_token`（官方 `full_url` 已拼好、可直接下载）；
- 官方解密方案：在线工具 + **可自部署 Docker 解密 API**（github.com/Evil0ctal/WeChat-Channels-Video-File-Decryption）——**v1.40 已拍板弃用 Docker**，改 **Python 内嵌解密**（ISAAC-64 keystream + 前 128KB XOR，参考该仓库纯 Python CLI `decrypt_wechat_video_cli.py`，v1.70 端到端实测通过）；
- → **L5 下载去重缓存键排除 decode_key**（每次变化），按 video_id 去重、按需刷新 media。

### 3. 入参语义（文档实证）

- fetch_video_detail 三选一：`object_id`（优先，来自列表 id）> `export_id`（搜索 `export/` 开头，**会过期需尽快用**）> `share_url`（仅前两者为空，`https://weixin.qq.com/sph/…`）；`object_nonce_id` 可选提命中；
- fetch_user_videos 翻页：`up_continue` 为真时原样回传 `last_buffer`（base64）；
- **号内搜索 fetch_search_channel_videos 命中项不带 media**（官方明确），拿媒体必须再走 fetch_video_detail——号内搜索仅作索引，下载多 1 次调用；
- **大整数 ID（id/object_id/object_nonce_id/topic_id/live_id/comment_id）64 位超 JS 安全整数**：~~前端 fetch 响应解析必须用 json-bigint 按字符串处理~~（**v1.42 已闭环修正：前端零改造、不引 json-bigint**——Python 后端 tikhub_client 已统一字符串化且实测确认，前端拿到的已是字符串，无精度问题；全链路统一字符串 P0）。

### 4. 对 Spec 的修正与优化

- 互动字段官方命名修正（见上文 §5）；
- **成本优化（重大）**：列表自带互动数+media → "顺带更新"零成本成立；同步旅程 1 次调用=列表+互动+下载源全齐；
- 解密环节设计：**Python 内嵌解密**（v1.40 拍板：ISAAC-64 + 128KB XOR，纯本地，不引入 Docker/Go；v1.70 端到端实测通过）；decode_key 与 media 同响应落库、短 TTL。

### 5. 文档层缺口（实测时一并验证）

- **fetch_search_videos（v1.39 修正：**搜视频**端点，非跨号作者搜索；搜作者=红狐 searchUsers 主 / TikHub fetch_search 备）响应 data 结构未在已抓页面展开**：入参 business_type 已 OpenAPI 确认（18 键，实测仅 all/account/article/video/sticker 返回数据、其余恒空仍计费）；搜索命中项 export_id → fetch_video_detail 链路已闭环（export_id 会过期需尽快用）；
- fetch_live_history 互动数文档列 like/fav/forward/comment（read_count 以"等计数"表述未明列）——**已实测确认在列（v1.74：readCount 字段存在）**；
- fetch_video_comments raw=false 未列全局计数（raw=true 带 monotonicData.commentCount + countInfo）——评论场景可顺带取全作品互动数，实测验证；
- OpenAPI/SDK 对 data 均为泛型（Any），字段结构仅 Apifox 文档描述提供——若实测与文档不符，以实测为准并回填契约。

## 字段映射核对表（现有代码 ↔ TikHub，2026-10-27 逐字段核对）

基于 `core/service/video.py`（_parse_video_object）、`core/service/search.py`（_parse_video/_parse_author/搜索返回）、`core/utils/database/base.py`（表结构）、`core/utils/database/crud/models.py`、`static/js/app.js`（mapAuthor/mapVideo）、`static/js/datahandle/authorOps.js` 逐字段对照 TikHub 文档。结论：**多数字段同构可直接映射，6 处不吻合/需适配，7 处待实测**。

### 1. 视频对象（fetch_user_videos / fetch_live_history / fetch_video_detail → author_videos）

> ⚠ **本表 ⚠ 标注为收口前旧标注（v1.75 统一回填）**：7 项待实测已全部收口——duration=详情秒/列表毫秒（两处单位不同，适配层归一，v1.13）、create_time=秒级时间戳→ISO（v1.13）、file_size 用 `duplicateFileSize` 或详情兜底（v1.13 §4.2 入库纪律）、列表已过滤非视频（media_type 过滤，v1.13）、搜索命中项=username/nickname（v1.13）、规格参数=X-snsvideoflag 无文档证据但 raw=false 已拼 token 直链可用（v1.13）、live_history read_count=在列（v1.74）。实测明细见「实测闭环与缓存设计更新 v1.13」表 + v1.74 补测。

| 现状字段（微信 object → 存库） | 现状来源 | TikHub raw=false 对应 | 吻合性 | 处置 |
|---|---|---|---|---|
| video_id（主键） | obj.id（**平台自然键**，非自造串） | videos[N].id | ✓ 同构 | 无需改（见 §4 修正） |
| object_nonce_id | obj.objectNonceId | videos[N].object_nonce_id | ✓ 同构 | 直接映射 |
| title | obj.objectDesc.description | videos[N].title | ✓ 更简单（TikHub 平铺） | 直接映射 |
| url | media[0].url + urlToken + `&X-snsvideoflag=规格` | media.full_url（已拼 token） | ⚠ **规格参数无文档证据** | 实测 full_url 是否含规格/可否追加 flag（见不吻合②） |
| spec | media.spec[] 选 1080/720/original | **TikHub 无 spec 列表证据** | ⚠ 缺失 | 实测；无则默认单规格 |
| file_size | media.fileSize（按分辨率估算） | media 文档**未列 fileSize** | ⚠ 可能缺失 | 实测；缺失则前端"大小"为空 |
| cover_url | media.coverUrl | media.cover_url ✓（文档确认） | ✓ | 直接映射 |
| decode_key（**INTEGER**） | media.decodeKey（长期有效） | media.decode_key（**每次请求都变**） | ⚠ **语义+类型双变** | 列改 TEXT；下载前必须刷新（不吻合①） |
| duration（秒） | spec[0].durationMs / videoPlayLen*1000 | media.duration（单位未标） | ⚠ 单位待实测 | 实测秒/毫秒后对齐 |
| create_time（ISO 字符串） | obj.createtime 秒级时间戳 → ISO | videos[N].create_time（格式未标） | ⚠ 格式待实测 | 必须统一 ISO（增量基准依赖字典序） |
| author_avatar（冗余） | obj.contact.headUrl | **列表无 contact（只有 username/nickname）** | ⚠ 源消失 | 删字段（前端仅 app.js:74 透传映射，不渲染，可安全删） |
| mediaType==4 过滤 | obj.objectDesc.media[0].mediaType | TikHub 列表是否已过滤非视频未标 | ⚠ 待实测 | 实测；已过滤则删过滤逻辑 |

### 2. 作者对象（搜索 / 列表顺带更新 → authors）

| 现状字段 | 现状来源 | TikHub 对应 | 吻合性 | 处置 |
|---|---|---|---|---|
| source_author_id | contact.username | 搜索命中项 username / **share_url 解析 username（v1.77 实测）** | ✓ | 直接映射 |
| name | contact.nickname | 搜索 nickname / **share_url 解析 nickname（v1.77 实测）** | ✓ | 直接映射 |
| bio | contact.signature | **share_url 无作者 desc（v1.77 实测 keys 无该字段）**；红狐列表项 description=作品描述非作者简介 | ⚠ 来源变化 | 权威更新靠 P3 user_profile（signature，增强）或接受空 |
| avatar_url | contact.headUrl | user_profile head_url（增强）；**搜索命中项未确认** | ⚠ 待实测 | 实测搜索命中项字段路径 |
| cover_img_url | contact.coverImgUrl | **TikHub 无对应**（user_profile 无封面） | ⚠ 长期为空 | 接受空值（前端不渲染该字段） |
| tag（profession） | 前端 authorOps 透传 profession | **前端搜索契约字段** | ✓ 后端兜底 | TikHub 搜索适配必须产出 snake_case（见 §3） |

### 3. 搜索接口返回契约（前端写死，TikHub 适配必须复刻）

`core/service/search.py:66-73` 模糊模式返回、`authorOps.js:271-273` 直接使用：**username / nickname / head_url / signature / profession / cover_img_url / friend_count**（snake_case）——TikHub 换源后**后端薄适配层必须把 TikHub 命中项翻译成这套字段名**，前端搜索渲染零改动。fetch_search_videos 命中项字段路径待实测（重点：账号项的 username/nickname/头像）。

### 4. Spec 此前错误修正（重要）

- **v1.6 声称"video_id=自造 16 位随机串（store.py:22 generate_id）"——读代码推翻**：`video.py:157` / `search.py` 入库 `video_id = obj.id`（**平台自然键**）；作者 id 用 `author_{username}`（author.py:71 / search.py:729）；`generate_id()` 仅导出、**未被业务使用**。
- 修正结论：**主键策略已经=平台自然键，TikHub 对齐零成本**（同一视频重复入库被 PK 天然拦截，去重幂等成立）。Spec v1.6"主键策略非标"条作废。

### 5. 不吻合点优先级（实施时处理顺序）

| # | 不吻合点 | 风险 | 处置 |
|---|---|---|---|
| ① | decode_key 每次请求变化 + INTEGER→TEXT | 存库 key 过期导致解密失败（最高） | 列改 TEXT；L3 缓存+ensure_valid_url 刷新；Python 解密模块按字符串入参 |
| ② | 规格选择（X-snsvideoflag）无 TikHub 证据 | 下载规格/流量成本不确定（商业化成本项） | 实测 full_url 规格语义后定 |
| ③ | 作者资料来源变化（contact 消失） | 头像/简介更新策略要改 | **share_url 解析给 username+nickname（v1.77 实测）**；头像/简介走 P3 user_profile（v1.78 修正：share_url 不给 desc） |
| ④ | create_time 格式未标 | 增量基准（latest_publish_date）依赖 ISO 字典序 | 实测后统一 ISO |
| ⑤ | 搜索命中项字段路径未展开 | 搜索前端契约（snake_case）依赖后端翻译 | 实测时重点核对 |
| ⑥ | mediaType 过滤/非视频 | 过滤逻辑去留 | 实测列表是否已过滤 |

## 后端路由交叉核对（前端 38 ↔ 后端路由，2026-10-27）

对后端 `core/api/routers/*` 全量提取路由定义并与前端调用点逐一对账，**发现 3 类缺口**，本节为映射表的修正依据：

### 1. 前端 38 个调用点：全部有后端路由对应 ✓

（含 upload-csv/upload-excel/csv-template/excel-template 走 `public_router`，无门禁；其余走主 router。）

### 2. 后端另有 6 个路由前端页面不调（GUI/CLI 内部用）

| 路由 | 用途 | TikHub 版处置 |
|---|---|---|
| `/api/service/start` · `/stop` · `/restart` | Go 进程管理（gui.py 用） | **下线**（v1.40：Go 进程移除，Python 后端内嵌解密，无独立进程需管理） |
| `/api/service/wechat-status` | 微信连接探测（GUI 用） | **移除**（微信通道砍除） |
| `/api/service/link-status` | 连接状态聚合（link_status.py） | 语义改 TikHub |
| `/api/task/download-all` | 全部下载（挂 require_wechat） | 门禁替换（同 batch-create） |

### 3. 门禁层修正：`require_wechat` 覆盖 16 个路由（远超映射表 A 类 7 个）

`core/api/deps.py` 的 `require_wechat` 挂载面：

| 模块 | 覆盖路由 | TikHub 版 |
|---|---|---|
| search router | `/authors`、`/author/add`、`/author/batch-add`（3） | 移除门禁，改 TikHub 连通 |
| video router | `/author/:id/add`、`/add-all`、`/sync-new`（3） | 同上 |
| task router | `/batch-create`、`/download-all`（2） | 同上 |
| inputer router | `/csv/import`、`/excel/import`、`/tencent-doc/import`（3） | **移除门禁**（原分类误标"纯本地不动"） |
| monitor router | `/start`、`/stop`、`/doc-sync/*`（5） | **移除门禁**（原分类误标"纯本地不动"） |

> ⚠ 映射表 C 类修正：`inputer` 3 个 import、`monitor` 5 个并非"纯本地不动"——前端接口名不变，但后端必须移除微信门禁，列入必要改动。

### 4. weixin_client.py 修正：不是整文件删除

- **移除**：微信通道数据/探测方法（contact/search、contact/feed/list、live/replay/list、feed/profile、check_wechat_connected）；
- **保留**：`build_video_filename` 等纯本地工具函数（file_validator.py / task 建名在用）。

### 5. 新增微信耦合点（此前未入账，实施时必须覆盖）

| 位置 | 耦合 | 处置 |
|---|---|---|
| `core/service/task.py:750` | batch-create 前 `check_wechat_connected` | 改 TikHub 连通/余额检查 |
| `core/monitor/monitor.py:252` | 轮询探测微信 | 改 TikHub |
| `core/utils/service_status_push.py` | SSE 状态推送 `wechat_connected` | 改 `tikhub_connected + balance` |
| `core/utils/tencent_doc.py` | 导入校验依赖 WechatVideoAPIClient | 改 TikHub 校验或去依赖 |
| `core/cli/service.py` | CLI 微信探测 | 改 TikHub |

### 6. 遗留死调用

`videoOps.js:127` `fetch('/api/status')` 后端无此路由（实际为 `/api/service/status`）——疑似遗留死调用（404 静默），列入前端清理项。

## User Stories
> 阶段归属：**混合**——#1–#17、#19–#21=阶段一（自用旅程+运维）；#18 调用可计量=阶段一（成本日志）兼阶段二（对账）；商业化 stories（卡密激活/扣点/一卡一机/解绑/购买引导）为阶段二新增，见「两阶段交付路线」§3

1. 作为用户，我希望**不打开微信客户端**就能搜索、浏览、下载视频号作品，以便降低使用门槛。
2. 作为用户，我希望**无需安装/信任根证书**，以便安装部署简单、无安全顾虑。
3. 作为用户，我希望微信客户端升级后下载器依然可用，以便不受微信版本迭代影响。
4. 作为用户，我希望**粘贴视频号分享链接（sph 短链 / channels.weixin.qq.com URL）即可解析并下载**，以便分享场景直接使用。
5. 作为用户，我希望按作者浏览**普通视频列表**（分页），以便选择下载。
6. 作为用户，我希望按作者浏览**直播回放列表**（分页），以便下载回放。
7. 作为用户，我希望对已添加作者做**增量监控**：只拉取新发布的视频/回放并自动建下载任务，以便自动化追更。
8. 作为用户，我希望**批量下载**（作者全部/勾选多条）并自动去重，以便一次拿完。
9. 作为用户，我希望**下载进度、状态、速度实时可见**，以便掌握任务情况。
10. 作为用户，我希望下载任务支持**取消/删除/清空**，以便管理失误操作。
11. 作为用户，我希望**头像、封面图正常显示**，以便界面完整。
12. 作为用户，我希望**视频详情**（标题、画质规格、时长、发布时间、评论数）可见，以便决策下载。
13. 作为用户，我希望**数据全部留在本机（SQLite）**，无需注册、登录、云端同步，以便隐私可控。
14. 作为用户，我希望本版本聚焦视频号能力、短剧功能另行排期，以便先快速落地 TikHub 通道。
15. 作为用户，我希望应用明确提示**TikHub 连接/余额状态**（余额不足、Key 失效），以便及时充值。
16. 作为维护者，我希望 **API Key 经 server-secrets 管理、明文不落盘**，以便密钥安全。
17. 作为维护者，旧微信版 `data/app.db` **不迁移**（2026-10-28 拍板）：仅 6 作者 + 457 条视频元数据、直链与封面链接均已过期（TTL 10 天级）、无下载记录（download_tasks=0）、主键体系不兼容（旧 `v2_...@finder` vs 新 username），新库从零开始、作者重新搜索一次即回（搜索成本极低），切换无痛。
18. 作为维护者，我希望**调用次数可计量**（每次 TikHub 请求记录），以便成本对账。
19. 作为维护者，我希望 TikHub 不可用时**有明确降级路径**（提示/红狐备用，双供应商互备；v0.8 微信通道已移除），以便不阻塞用户。
20. 作为维护者，我希望**合规风险在文档与 UI 有提示**（仅限个人调研/内部分析），以便风险知情。
21. 作为用户，我希望**输入作者主页/链接即可直接下载该作者全部视频与回放**（前端旅程对齐 TikHub 端点粒度，无需"添加作者→同步入库→进作者页"前置步骤），以便高频追更作者一键全拿。

## Implementation Decisions
> 阶段归属：**混合**——换源/下载/解密/监控/成本记录/密钥/双供应商互备=阶段一；卡密激活/计费拦截/路由定价=阶段二（自动更新授权校验已砍，v1.66）

- **新增 TikHub 客户端模块**（`tikhub_client`），统一封装鉴权、**超时分级（v1.45：连接 5s / 红狐读 30s / TikHub 读 90s，值读 billing_config；读超时绝不重试，宁可等到干完不白丢费）**、大整数 ID 按字符串处理（`id/topic_id/live_id/object_id/comment_id`）、翻页游标（`last_buffer` 原样回传、禁止解析）、`raw=false` 精简结构。核心端点 5 个：
  - **红狐 `search_users`**（/story/api/sphAllData/searchUser，REDFOX_API_KEY）——关键词搜作者（TikHub 搜一搜 `fetch_search`+account 当前账号 400，§6.1 双供应商映射：搜作者主链路=红狐）；顺带覆盖视频搜索=`search_works`；
  - `wechat_channels/v2/fetch_user_videos` —— 作者作品列表（替代 feed 列表；红狐优先时改用红狐 `get_user_works`，见 §6.1）；
  - `wechat_channels/v2/fetch_live_history` —— 直播回放列表（替代回放列表）；
  - `wechat_channels/v2/fetch_video_detail` —— 单条详情 / 链接解析（替代详情接口；红狐 `get_work_by_link` 仅元数据无直链，贴单视频链接下载暂走本端点）；
  - `wechat_channels/v2/fetch_channel_id_to_username` —— sph 短号 → username（**v1.79/80 实测 400 平台侧确认，彻底移出主链路**；L1 主路径=share_url 解析 v1.77）。
- **增强端点（v1.75 修正：合集/主页资料/评论均已进本版，仅号内搜索预留）**：`fetch_user_collections` + `fetch_collection_videos`（合集，**进本版 v1.54**——作者页「合集」入口 → 合集内视频列表 → 按合集批量下载；数据源=TikHub 专属，红狐无合集接口；合集内视频优先查 L2 author_list_snapshot 快照，命中 0 成本，未命中页走合集端点 $0.01/页）；`fetch_user_profile`（主页资料，**进本版 v1.60**——懒触发+TTL 7 天）；`fetch_video_comments`（评论，**进本版 v1.60**——懒触发+TTL 7 天，默认 1 页 20 条）；预留：`fetch_search_channel_videos`（号内搜索，P3 后置）。
- **数据获取服务层替换**：搜索服务、视频服务、监控器的数据来源从微信客户端改为 `tikhub_client`（+ 红狐 `redfox_client`，双供应商并存、红狐优先）；返回结构做字段映射适配现有数据库模型（作者 username/nickname、视频 id/标题/media/decode_key/createtime、回放同构；红狐字段翻译：findName→username、headUrl→head_url、coverImgUrl→cover_img_url、likeCount/commentCount/favCount/forwardCount→互动数；**v1.59 新增：exportId→author_videos.export_id（TikHub 详情 export_id 直通，兜底下载免反查）、topic→话题列（JSON 数组入库存，本地筛选）、width/height→分辨率列**；短链 get_work_by_link 字段命名第二套 likeNum/commentNum 等**不接**，只取 exportId/直链相关）。
- **下载链路（v1.39 修正：红狐直链优先）**：**主链路=红狐 videoUrl 直链直接下载**（`get_user_works`/`get_work` 返回，已实测未加密可播，无需解密）；**兜底链路=TikHub media `full_url` + 同响应 `decode_key` 本地解密**（红狐直链失效/贴单视频链接时）；复用现有 task 模块（任务表/进度/状态/WebSocket），url 取红狐 videoUrl 或 TikHub full_url（官方已拼 url+url_token），key 取同响应 decode_key（**必须同响应配对**，仅 TikHub 链路需要）。
- **解密环节（v1.40 修订：Python 内嵌，移除 Go/Docker）**：解密算法=decode_key → Isaac64 PRNG → 131,072 字节密钥流 → 对视频前 128KB 做 XOR（社区公开；参考 Evil0ctal/WeChat-Channels-Video-File-Decryption 纯 Python CLI `decrypt_wechat_video_cli.py` + 本地验证样本 `D:\dev\wechat-decrypt\...\wx_encrypted.mp4` / `wx_response.json`）；decode_key 按字符串存、与 media 同响应落库、短 TTL（分层失效），不进 L5 去重键；**不引入 Go 进程、不引入 Docker、不依赖外部黑盒**（v1.40 拍板）。
- **微信连接探测替换（v1.56 拍板：状态卡片规格）**：原"探测微信是否连接"改为**双供应商状态卡片**——红狐、TikHub 各一行独立状态徽标（正常/异常）+ 错误原因一句话（401=Key 失效 / 402=欠费 / 429=限流 / 5xx=上游故障）+ **当前生效链路标注**（红狐为主，熔断切换时跟随）；**不显示余额数字**（两家上游均无余额查询 API，硬做只能编）；**刷新=启动时探测一次（TikHub 走官方计价接口 calculate_price、红狐走 search_users 顺带）+ 业务调用出错实时更新**，不做定时轮询（省成本，正常常绿不花钱、出错立即变红）；异常时给**「打开后台查看/充值」跳转入口**（user.tikhub.io / 红狐控制台）；**逆向余额接口=后续可选增强不排期**（浏览器自动化抓后台接口技术上可行，但=黑盒依赖，页面改版需重抓；阶段二商业化需要精确余额监控时再做）；前端状态卡片位置沿用原"微信连接状态"卡片位。
- **监控频率重设计**：原 30 分钟轮询按 TikHub 计价不可行（10 作者 × 48 次/天 ≈ $144/月）；改为**打开界面即同步 + 标星作者每天 2 次兜底（v1.22）**，增量只拉第一页对比 `createtime`，预计 2 作者 × 每天 2 次 ≈ $1.2/月。
- **成本记录**：每次上游调用（红狐/TikHub）写一条调用日志（端点、参数摘要、耗时、计费预估），支持对账与异常放大检测。
- **密钥与供应商**：`TIKHUB_KEY`（密钥库实际名，非契约占位 `TIKHUB_API_KEY`，2026-10-27 已核验 len=60）经 server-secrets 存储；按供应商契约纪律：先用新户赠额（约 $0.05）测通 → 充最小 $5 → 稳定后再加额（不退款红线，严禁一次大额）。
- **双供应商互备（v1.39 拍板，取代旧"双数据源开关"）**：红狐为主链路、TikHub 为备用链路（同功能红狐优先、失败自动切换）；**微信通道已移除（v0.8 拍板），不存在"微信/TikHub 通道切换"**。

## Testing Decisions
> 阶段归属：**阶段一**

- **测试准则**：只测外部行为（给定输入 → 期望输出/副作用），不测实现细节；优先在**数据获取服务层**这一个 seam 上测试，Mock `tikhub_client` 返回固定夹具，避免真实调用计费。
- **覆盖模块**：
  - `tikhub_client`：URL/参数构造、鉴权头、大整数 ID 字符串化、翻页游标透传、超时与错误映射；
  - 服务层适配：TikHub 返回结构 → 现有数据库模型的字段映射（含作者/视频/回放三张表）；
  - 监控增量逻辑：只拉第一页、按 `createtime` 判定新增、建任务去重；
  - 成本计量：调用次数记录正确、余额不足时状态卡片提示。
- **沿用现有三层测试**（单元 / 集成 / 端到端）；端到端在真实充值后用最小成本跑通 1 个作者（全量同步 ≈ $0.05），验证 media + decode_key 真实可下载。
- **先例**：现有微信通道的字段映射与监控增量测试可直接复用夹具结构。

## Out of Scope
> 阶段归属：**两阶段都不做**——短剧另行排期；号内搜索 P3 后置；评论导出 P3 后置

- **短剧嗅探（res_download / static/sniff 前端，本版本不做，后续版本合入）**；
- 公众号 / 文件传输助手相关接口（沿用或不做）；
- **评论导出（批量导出 CSV，P3 后置）**；主页资料/评论**已进本版 v1.60**，合集**已进本版 v1.54**，号内搜索 `fetch_search_channel_videos` **P3 后置**（v1.75 修正：Out of Scope 旧文"合集/评论/主页增强=阶段二后置 P3"为 v1.54/v1.60 拍板前旧口径，已随拍板回填）；
- 数据上云、多端同步、GitHub 数据后端（已探讨否决）；
- 不合规抓取数据对外售卖（v1.75 修正：阶段二商业化=卖**数据服务差价**（点数×卡型，红狐主数据源=合规 API 转售，行业=API 中转站模式）；TikHub 灰色链路不进对外承诺主链路；旧文"合规商业化阶段二也不做"表述与阶段二定义矛盾，已修正）；
- 抖音 / 其他平台（红狐通道另案，不在本文档范围）。

## 决策记录与待拍板项状态

> 2026-10-27 会话内记录；随探讨持续更新。

### 已拍板

| 项 | 决策 | 版本 |
|---|---|---|
| 方案方向 | TikHub 云端 API 作为视频号数据后端（知识库 TikHub 供应商，非 GitHub） | v0.1 |
| 目标 | 摆脱微信客户端依赖，用户无需打开微信即可搜索/浏览/下载 | v0.1 |
| Spec 载体 | 项目目录本地 MD（非在线文档） | v0.1 |
| 短剧 | **本版本砍除**，res_download 链路另行排期合入；交付物=单「号匣」（微信视频号下载器） | v0.3 |
| 前端接口 | 视频号 38 个全部复用不改（短剧 10 个不在范围） | v0.3/v0.4 |
| 收敛分析 | 12 项繁琐/重复点已统计入档；后端原语收敛 3 个 | v0.4/v0.5 |
| 可砍清单 | A 类彻底移除 6 项 / B 类换源 4 项 / C 类保留 7 项 | v0.6 |
| 微信通道 | **彻底移除**（A1–A6 全砍：前端微信 UI/检测 5 处、weixin_client.py 微信封装、微信客户端本体；监控器保留、内部数据源换 TikHub 低频轮询）；2026-10-27 用户拍板"直接移除" | v0.8 |
| 缓存攻坚节奏 | **缓存先行、定价完全搁置**（用户拍板：先把成本压到接近 0，定价才有自由空间；并行做任务量大、做不精、不闭环）；一次只攻一层，每层完成定义=可写代码+验收用例闭环再进下一层；L1 规格已落档（§4.2） | v1.12 |
| 实测收口（字段映射 7 项待实测全闭环） | 2026-10-27 一次性最小实测（$0.02+404 免费）：key 有效有余额、$0.01 固定无折扣、UA 纪律 P0、create_time 秒级、duration 详情秒/列表毫秒、file_size 有、互动驼峰转 snake_case、搜索路径文档闭环、expire_time 详情无/列表 urlValidDuration=48h | v1.13 |
| raw=false 统一（工程决策） | 列表/搜索类端点**统一传 raw=false**（TikHub 官方"推荐做媒体下载"）：返回 snake_case + `media.full_url`+`decode_key` 同响应配对 → 适配层免驼峰映射、L2 列表缓存命中即可直接下载 | v1.13 |
| TTL 观察实验（临时测试点） | 用用户提供的分享链接实测拿到的 full_url 建观察：`scripts_observe_ttl.py` + `_ttl_observation.log` + 每日 18:30 本地定时任务，探测直到过期；验证下载直链真实 TTL（用户自测 10 天 vs 列表 urlValidDuration 48h 的关系），锚定 L2/L3 TTL | v1.13 |
| L2 列表缓存规格 | **完整规格落档 §4.3**：落点 4 文件（models.py / 新 tikhub_client.py / service/video.py / routers/video.py）；channel_sync_state 表（便利贴方案 A）；TTL=60 分钟默认（48h 硬上限参考、观察实验校准）；验收 5 条；首见全量≈$0.03/作者、追更 1 次/过期 | v1.14 |
| **L2 分页策略修正** | **接口能力实锤：TikHub 无全量模式，只能游标翻页（last_buffer/cursor），$0.01/页**；**用户拍板策略 C**：首拉 3 页（≈$0.03-0.04 封顶 6 页 $0.06）+ 翻页惰性续拉（$0.01/页，成本随用户行为走，大作者永不失控）；已拉页翻回 0 成本；channel_sync_state 加 video_pages_fetched/replay_pages_fetched；验收 6 条（新增翻页验收） | v1.20 |
| **L4 搜索缓存键带页码** | **用户确认补丁**：search_cache 键 = `q\|exact\|page`；result_json 原样存（含 next_cursor 供续页）；翻页=用上一页游标续拉（1 次/页，不带页码需 2 次/页）；已缓存页翻回 0 成本；无结果仅 page=1、1h TTL | v1.20 |
| **下载引擎（待拍板 #3）** | **已拍板：自研直链下载模块**。弃用 wx_video_download（接口文档实锤 channels.available 依赖证书安装=微信生态绑定；用户规则"微信升级致失效"）；弃用 TikHub 官方下载器（README 仅 TikTok/抖音无视频号 + GPL v3 冲突商业化）；方案=full_url 直链 HTTP 下载（带浏览器 UA），复用 task 模块 + L5 file_validator，0 微信依赖、0 GPL | v1.21 |
| **监控频率（待拍板 #2）** | **已拍板：打开即同步 + 标星低频兜底**。打开主页=0 成本快照（不刷任何作者）；点开作者=惰性刷新（L2，过期单作者 $0.01）；标星作者每天 2 次兜底；主页计数显示本地快照（channel_sync_state.video_count），可选增强"X 小时前更新"标注；原 30 分钟轮询 $144/月否决 | v1.22 |
| L2 TTL | **120 分钟（用户拍板，省钱档）**：30=重新鲜度/60=平衡/120=重省钱，48h 硬上限内；观察实验出数后回填校准 | v1.15 |
| L3 详情缓存规格 | **完整规格落档 §4.4**：载体=author_videos 现有列（url 已是完整直链，不加 full_url），只加 `url_updated_at` 一列（链接年龄/可观测性）；安全窗口=实测保质期×0.8（出数前 24h 保守）；ensure_valid_url 增强为年龄判断+主动刷新；搜索命中→详情补链 $0.01；验收 5 条；事件+指标可观测性底座 | v1.16 |
| L4 搜索缓存 | **TTL 拍板：有结果 24h / 无结果 1h（惰性刷新）**；完整规格落档 §4.5：缓存对象=作者搜索结果（快照表 search_cache，非便利贴）；键=q\|exact；前端搜索框 300ms 防抖联动；验收 5 条 | v1.17 |
| L5 下载去重+前端冷却 | **完整规格落档 §4.6**：权威源=文件系统（DB 标记仅缓存）；三态判断（已下载+文件存在有效=不重复下 / 不存在或无效=自动转重下含损坏/0字节/换盘/空路径）；后端幂等锁（并发 10 点=1 任务）+ 前端按钮冷却；验收 5 条；**五层缓存规格全部收口** | v1.18 |
| 前端三路径旅程（待拍板 #5） | **已拍板进本版**：①我的作者（主页读库秒开、老数据兼容、点击直达+自动拉列表）；②搜索（L4 缓存、点开自动入库）；③导入链接=可选辅助入口（L1）。被省：同步弹窗/进度条/手动同步按钮；后端仅薄适配不做聚合接口 | v1.19 |
| **商业化授权形态** | **已拍板（2026-10-28 用户确认）**：**卡密 + 点数 + 一卡一机设备绑定，不做用户系统**（无注册/登录/账号）；卡密号=身份、服务端扣点；复用柠檬卡密系统；换绑走客服/自助（后续迭代）；定价 1 次=1 点（单价搁置）。行业对照实锤：下载器行业=授权制无差价、API 中转行业=服务端计费拦截+倍率加价（爱范儿/36氪）、本地扣点无先例必被破解；自己的拾光AI 即"卡密—点数"已验证 | v1.23 |
| **api_usage 成本计量表细化** | **v1.23 完整 DDL 落档（§2.5）**：只记真实调用（缓存命中不记）、成功失败都记（失败 cost=0）、cache_layer 标注触发层；card_id 维度（成本账+扣点合一）；对账=SUM(cost) vs SUM(points)×单价；**§508 旧表清单同步修正**（author_list_cache/video_detail_cache 已废除，禁止按旧表建） | v1.23 |
| **自动更新机制** | **已拍板（2026-10-28 用户确认）**：术语统一"自动更新"（OTA 仅留接口路径名）；客户端时机=**启动检查 + 每天一次后台静默检查**（不抄柠檬文档"仅启动一次"——该文档已偏离行业标准 Electron 启动+10min / Sparkle 24h）；服务端沿用柠檬 updates/check 不改；强制更新标记后置；柠檬 docs 文档同步修正（§2.6） | v1.24 |
| **自动更新标配防护（收敛版）** | **已拍板（2026-10-28 用户确认）**：只做行业最常见防护 9 条（后台+超时+静默+手动入口 / 下载校验+重试 / 通知条用户确认 / 点击即反馈+落盘+独立安装器 / **代码签名** / **数据目录与安装目录分离** / 提权安装器 / 失败旧版仍在 / 单实例锁）；明确不做自动回滚/强制更新/时间校验/磁盘预检/代理专项/32位（§2.6 ⑦）；运营纪律：发版发卡统一香港底座防 ADR-063 分裂（§2.6 ⑧） | v1.25 |
| **② 鉴权+扣费（柠檬对齐版）** | **已拍板（2026-10-28）**：柠檬为卡密真相源，网关只做编排。复用：redeem-by-app（幂等兑换）/ MachineBindMode.one_card_one_device + KamiDeviceBinding（一卡一机）/ consume（biz_id 幂等+min/max+自动记设备）/ get_points_balance_summary / create_user_access_token（无感用户）。**自建 card 表/幂等表/扣点事务全部废除**；网关自建只剩激活编排 + 设备指纹规范 + api_usage 成本账（§2.5 ②） | v1.26 |
| **③ 缓存两层挂载（网关化）** | **已拍板（2026-10-28）**：省钱层=网关共享三表（channel_alias / **author_list_snapshot 响应快照** / search_cache，跨用户跨机器命中=只付一次钱，不绑卡密/用户/设备，命中用户照扣 1 点我们成本 0）；用户层=客户端本地（author_videos / L3 链接列 / download_tasks / 文件校验，隐私+秒开）；**L2 便利贴→响应快照**（v1.23 便利贴是本地应用架构产物，网关化后恢复共享快照；channel_sync_state 定位改为客户端本地同步便利贴）；L3 数据存本地、刷新动作走网关先查共享快照（§2 / §4.3） | v1.27 |
| **④ 防滥用（模型自保版）** | **已拍板（2026-10-28）**：**防亏不需要限流**——时间+点数双限制=成本封顶（任何卡成本 ≤ 点数×$0.01 永远封顶）+ 扣点先于调用（余额不足 429 不调 TikHub）= 定价覆盖最大成本毛利恒正；**砍掉**卡密/设备/IP 频率限流与熔断；**只留服务器保护 2 个轻桶**：单卡并发 ≤5 + 全局 QPS 兜底；顺序=鉴权→扣点→限流→业务，超限 429 不扣点（§2.5 ④） | v1.28 |
| **③ 计费配置（配置表驱动）** | **已拍板（2026-10-28）**：配置表驱动计费=行业标准（one-api/new-api 倍率配置+Per-call 计费+Cache Billing、AWS/Azure 计费表、Stripe Product+Price 对象，3 来源族查证）；**两张表**：route_rate（路由扣点+上游美分成本）+ billing_config（汇率 7.2/点单价）；**价格永不在客户端**（客户端哑终端只显示余额，改价即时生效无需更新）；成本锚 1 点=¥0.072≈0.07；扣点规则=5 数据路由 1 点/请求+3 非数据路由 0 点+下载不额外扣+缓存命中照扣（new-api 有打折先例，我们定 1.0）；改价改表不改代码，route_rate 缺失=路由拒绝（§2.5 ③） | v1.29 |
| **④ 配置管理（Pydantic Settings 分工）** | **已拍板（2026-10-28）**：静态配置（部署参数/地址/超时/UA/环境区分）走 **pydantic-settings**（env > .env > 默认值，统一前缀 TIKHUB_/LEMON_/GATEWAY_）；动态配置（汇率/倍率/路由扣点）走**数据库表**（route_rate/billing_config）；密钥不进 .env 明文（server-secrets 动态读，通道分离）；记账字段禁止进 Settings（§2.5 ④） | v1.30 |
| **真时间卡（定制开发拍板）** | **已拍板（2026-10-28 用户确认）**：**走定制开发**（柠檬代码是我们自己的；执行人可为外包，改造点检测清单=交接单）；组合方式=**复用 points 类型 + 非空 time_value/time_unit**（不新增枚举/不改 DDL/admin 下拉）；**源码实测改造量=2 处函数级修改**：①核心 `point_ledger._expires_at_for_kami` 加 time 折算（lot 到期=min(点数到期,时间到期)，consume 经 _active_lots 自动生效零改造）②一致性 `sdk.calculate_expire_time` 加组合判断；发卡层已支持（kamis.py:1092 无条件写 time_value）、兑换层已放行（points 卡校验）、无需新增列；验收=双限制并行先到先失效+存量卡不回归（详见《柠檬真时间卡开发方案.md》v1.31） | v1.31 |
| **⑤ 用户提示文案** | **已拍板（2026-10-28 用户确认）**：用户提示一律**从用户视角——只告知事实（当前状态）+ 给购买通道，不替用户做决定（不指定卡型/价格）**；卡型列表展示=砍掉；两条模板落档：余额不足（点数不足 X/Y 点→购买卡密→联系客服）/ 授权过期（授权已过期→购买新卡密）（§2.5 ⑤） | v1.32 |
| **卡型规格定稿** | **已定稿（2026-10-28 用户确认）**：4 档卡为唯一真相源——1天体验 3 点 ¥0.9 / 3天 10 点 ¥1.9 / 7天 25 点 ¥2.9 / 30天月卡 100 点 ¥9.9；每点卖价 0.30/0.19/0.116/0.099 全 > 成本 0.07 毛利恒正；量大优惠；缓存命中纯赚使真实毛利 ≥ 账上（§2.5 拍板结论·卡型规格表） | v1.33 |
| **⑥ 客户端激活交互** | **已拍板（2026-10-28 用户确认）**：行业标准落定（激活入口=主界面 tab / 单面板输入 / 错误分类提示 / **首次激活即绑定本机=无感** / 成功即展示卡信息+状态区常驻 / 到期锁功能不锁软件）；**单卡规则**——同一用户同一时间只能一张卡生效（网关 activate 前查 available_balance，>0 拒绝；到期/用完后可换新卡）；**文案清单全量落档**（成功/无效/已使用/已冻结/已过期/设备不匹配/已有卡生效中/未激活/状态区常驻，从用户视角告知事实+给出口）（§2.5 ⑥） | v1.34 |
| **换机解绑规则（延后）** | **已拍板（2026-10-28 用户确认：本期不做，延后）**：不做换绑规则（限次/客服判断/自助反激活）**本期全部不做**；柠檬原生已支持 `release-device`/`unbind` 端点，客户端能力已具备；后续需要时再定规则（§2.5 ⑥ 第 6 条） | v1.35 |
| **客户端自助解绑（进本版）** | **已拍板（2026-10-28 用户确认）**：换机解绑从"延后"改为**进本版**——入口=第三 tab「我的卡」区域（已激活时显示当前卡信息+[解绑本机]按钮）；流程=点解绑→确认弹窗（告知后果）→调网关 unbind→成功提示→本机回未激活；技术=客户端→网关新增 unbind 路由（卡密路由 2→3）→柠檬 `/sdk/unbind`，客户端哑终端不直连 SDK；**规则=一张卡限解绑 2 次**（网关计数防转卖，超限提示联系客服）（§2.5 ⑥ 第 6 条） | v1.36 |
| **架构边界与统一货币** | **已拍板（2026-10-28 用户确认）**：网关=**单产品起步**（只服务 downloader，垂直切片不变），表结构**预留 product_id 维度**（route_rate/billing_config/api_usage 带 product 列，默认 downloader，将来加产品=加行配置）；**基础设施共用一套、卡密+点数按产品隔离**（隔离原因=各产品成本/定价策略不同，防便宜点数跑贵服务亏钱）；**统一货币=星尘（Stardust/SD，暗宇宙星夜微光意象）**——全链路统一叫法不引第二货币，1 星尘=1 次调用（下载器），各产品 1 星尘价值由各自 route_rate 扣点决定；卡密跨产品通用=柠檬层大工程本期不碰（§2.5 ⑦） | v1.37 |
| **客户端 UI 规范** | **已拍板（2026-10-28 用户确认）**：客户端视觉**遵循暗宇宙设计系统**（tokens 取色取字体 + 星夜微光氛围层 + 品牌语气），**操作区实用优先**（工具类软件不游戏化不重装饰，品牌只做氛围层点缀）；实施纪律=前端动手前必读公司前端规范 + tokens 正本，参考 ADR-042（§2.5 ⑧） | v1.38 |
| **双供应商映射（红狐优先）** | **已拍板（2026-10-28 用户确认）**：TikHub 与红狐**并存**，同一功能红狐能覆盖的**尽量先走红狐**（红狐 ¥0.02/次起 < TikHub $0.01≈¥0.07，且红狐直链**免解密**）。红狐端点全实测 200：search_users（搜作者，返回 findName=username）、search_works（搜作品）、get_user_works（nickname 拉列表，**带 videoUrl 直链+互动数**）、get_work（详情直链）、get_work_by_link（短链解析，仅元数据无直链）；**直链实测可播**（ffprobe：H.264/720×1280，未加密）。**下载双链路并存**：主=红狐直链直下（免解密）、备=TikHub full_url+decode_key 本地解密（必保能力）；作者主键统一=username（findName）；TikHub 独有：主页统计/评论/合集/直播/号内搜索/生成分享链接/短号映射/账号信息（见 §6.1 全表） | v1.39 |
| **解密载体（Go 进程移除）** | **已拍板（2026-10-28 用户确认）**：**Go 进程太重，整体移除**。解密=**Python 后端内嵌模块**（Isaac64 PRNG 生成 131072B keystream + 前 128KB XOR，公开算法；本地参考=Evil0ctal 开源 decrypt_wechat_video_cli.py + 验证样本 wx_encrypted.mp4/wx_response.json decode_key=2136343393）；进程形态=**前端壳 + Python 后端两件套**；`/api/service/start\|stop\|restart` 路由下线；**P0 验收✅ 已验证（2026-10-28）**：scripts_probe_python_decrypt.py 实测解密成功、ffprobe 52.31s 可播放，TikHub 备用链路端到端可用 | v1.40 |
| **收/支分离（行业对齐）** | **已拍板（2026-10-28 用户确认）**：行业标准=**收支持分离**（one-api/new-api 渠道维度独立定价：用户侧倍率=分组×模型与供应商无关，上游成本=各渠道实际价；快米兔"先向上游采购再按自己倍率结算"；我们 ADR-010 网关计量前置）。**对客 route_rate 表不动**（红狐接入不改扣点/售价，价格永不在客户端）；**新增 `supplier_cost` 表**（route×supplier→成本，人民币分：红狐广域库=4/实时=6/字幕submit=30、TikHub 微信系=7.2）；**api_usage 加 supplier 列**（实际走了哪家，漏记=对账失真 P0）；**路由优先级**=同路由选 active=1 且成本最低者（红狐优先/TikHub 兜底），供应商失败熔断置 active=0 自动切换，不搞权重轮询（2 家无必要）；route_rate.upstream_cost_cents 标注弃用兜底。**成本锚更新**：核心数据路由红狐 ¥0.04（阶梯最低 ¥0.02）vs TikHub ¥0.072，防亏上限更低更稳；字幕端点 ¥0.3/次主线排除（见 §6.1） | v1.41 |
| **前端大整数（缺口 #4）** | **已闭环（2026-10-28 用户确认"统一用 string"）**：前端**零改造、不引 json-bigint**——行业标准=API 层 ID 一律字符串（Twitter id_str / GitHub node_id / Stripe）；Python 后端 tikhub_client 已字符串化且实测确认 → 前端拿到的已是字符串。**全链路统一字符串 P0**：响应模型 id 类字段一律 str（含 decode_key）、DB 存 TEXT、缓存键原样、解密入参 str（§6 #4） | v1.42 |
| **TTL 单一事实源治理（缺口 #5）** | **已闭环（2026-10-28）**：根因=旧段落未随拍板回填。权威口径以 §4 缓存表为准（L1=1 年/L2=120min/L3=decode_key 不缓存+年龄窗口/L4=24h\|1h/L5=永久）；**回填 9 处旧残留**（总表 L3、P1 表名、P1 TTL×3、service 路由、fetch_search_videos×5、create2）；新纪律 P0=每轮拍板必须同步回填受影响旧段落（§6 #5） | v1.43 |
| **定价形态收敛（废弃 A/B/C）** | **已拍板（2026-10-28 用户确认）**：收费策略=**点数 × 时长卡型唯一**（1天3点/3天10点/7天25点/30天100点，v1.33 唯一真相源）；**不做单作者月卡、不做按条计费、不做打包档**（早期「A 单作者月卡 + C 按条 + B 打包」讨论稿废弃，回填 §6 待拍板#6 与 P3 定价表实施行） | v1.44 |
| **超时/重试计费防护（缺口 #6）** | **已拍板（2026-10-28）**：**超时分级 + 失败分类重试（本版做）**——连接 5s / 红狐读 30s / TikHub 读 90s（值进 billing_config，改表不改代码）；连接失败/429/5xx → 指数退避 3 次（2s→4s→8s+jitter）；401/402/400 不重试；**读超时绝不重试**（状态未知防双计费）；api_usage 加 duration_ms（P95 观测驱动调参）。**熔断切换（供应商级、网关服务器级、对客户端透明：连续 3 次失败→熔断 60s→半开探测 1 个请求）后置阶段二**，细节已落档 §2.5；失败返还（柠檬 refund）+ biz_id 幂等利用=阶段二商业化（§6 #6） | v1.45 |
| **本地 key 注入通道（缺口 #7）** | **已拍板（2026-10-28）**：key=静态配置走 Pydantic Settings——**阶段一自用版=.env 文件**（REDFOX_API_KEY/TIKHUB_KEY，项目根，打包排除、不入 git）；**阶段二=key 上收服务器 env（server-secrets 落库），客户端零 key**（防用户拿 key 绕过网关直连上游；与"价格永不在客户端"同原则）；key 有效性检测走接口级全局熔断（401/402 提示）（§6 #7） | v1.46 |
| **阶段一自动更新源（缺口 #8）** | **已拍板（2026-10-28）**：**复用 ADR-022 静态存储发布模式**（拾光 v0.6.7 生产验证）——更新源=`lemon-kami-artifacts` 公共读桶 `…/haoxia/updates/latest.json`（指针人控切换）；目录 `haoxia/releases\|updates/{版本}/` 双产物；**产品定名「号匣」**（OSS 目录 haoxia，撞名初判通过）；**客户端版本号 v0.1.0 起步**（与 Spec 版本号独立）；发布走本机脚本（ADR-021 本地化，`-PublishPointer` 人控 + release_record.py 登记）；阶段二同机制零改造、自动更新本身不收费（§6 #8） | v1.47 |
| **封面/头像 URL 过期兜底（缺口 #10）** | **已拍板（2026-10-28）**：行业标准版——签名 URL 不存库当永久地址（存 URL 同时存过期时间、提供前检查、过期重取）；**复用 L3 机制零额外成本**：authors 表加 `cover_updated_at`，浏览作者页检查年龄（TTL 按天计），过期走 L2 列表刷新顺带更新 headUrl/coverImgUrl（无独立调用）；客户端失败→占位图+重试≤3+超限稳定占位图防循环（§6 #10） | v1.48 |
| **自用成本统计视图（缺口 #12）** | **已拍板（2026-10-28）**：**阶段二实施项、阶段一跳过**——`api_usage` 计量在网关侧（客户端经网关转发时顺手记 endpoint/supplier/count/cost/duration_ms），成本统计视图=网关侧内部报表接口按日期/端点/供应商聚合、仅运营看；阶段一无网关（客户端直连上游）不计量不报表，不阻塞阶段一闭环；阶段二定价前必做（真实成本基准支撑毛利严谨性）（§6 #12） | v1.49 |
| **断点续传（缺口 #9）** | **已拍板（2026-10-28）**：**阶段一实施，A 方案（单连接 Range 自动续传）**——红狐直链实测支持 Range（206 + Accept-Ranges，`scripts_probe_range_support.py`）；**TikHub 权限先搁置（用户拍板，不开工单）**，红狐主链路为准；下载器**通用探测设计**（恢复时探测 Accept-Ranges→支持续传/不支持重下），下载完成后 Content-Length 对齐→统一解密；TikHub 备用链路待权限开通后同设计自动生效（§6 #9） | v1.50 |
| **多 Key 轮换（缺口 #11）** | **已拍板（2026-10-28）：不做**——平台口径不支持：TikHub 限流=账号级 RPS（提速=账号级月付，多 token 无独立配额承诺）；红狐限流粒度未公开（无 key 级承诺）；已有 429 退避重试+双供应商互备覆盖，多 key 无平台依据；仅未来实测发现 key 级限流再启用（§6 #11） | v1.51 |
| **阶段一架构冲突审查（2026-10-28）** | **A 类 5 处已修复**：①L4 规格"现状走 2022 微信搜索"→红狐 searchUsers 主/TikHub 备（2022 已弃用 v1.21）；②L4 落点"未命中调 TikHub"→红狐主/TikHub 备；③L4 落点 TikhubClient 提供搜索端点→供应商客户端（红狐主/TikHub 备）；④D 域总账"网关侧共享表+客户端本地表"→**客户端本地 SQLite（阶段一，无服务器）**，网关共享=阶段二；⑤Solution/交付物"TikHub 后端版"→红狐主/TikHub 备双供应商。**B 类已拍板（2026-10-28）：统一**——Spec 内 7 处产品标识（51 柠檬应用/779 网关边界/784 product_id 默认/818-820 key 前缀/901 网关服务对象/905 卡密隔离）已全部改为 `haoxia`；代码文件名 `downloader.py`（下载引擎模块）保留不动（非产品标识）；**柠檬后台应用已实际改名完成（2026-10-28 执行）**：admin 端点 `PUT /api/v1/admin/apps/{app_id}?name=号匣`（源码 admin/apps.py:276 实锤，admin 鉴权、query 参数 name、只改 name 无级联），name downloader→「号匣」，app_id 不变；两层口径收敛=柠檬后台 name 用「号匣」（对外名）、Spec/OSS 目录/product_id 用 `haoxia`（内部标识） | v1.52 |
| **旧库废弃不迁移（缺口 #2 数据迁移）** | **已拍板（2026-10-28 用户确认）**：微信版 `data/app.db` **不做迁移**。实锤依据=①数据量极小（authors 6 行、author_videos 457 行、download_tasks **0 行**、task_log 3 条）；②author_videos.url 为 `finder.video.qq.com` 老直链，TTL 10 天级早已过期（TTL 观察实验佐证），封面/头像同为签名链接大概率过期（v1.48 兜底机制要处理的正是这类）；③主键体系不兼容（旧 `source_author_id=v2_...@finder` / `id=doc_author_*` vs 新 username=红狐 findName），映射要写转换脚本；④无下载记录可迁。**处置**：新库从零开始（schema 按本版设计，不为老数据保留兼容列）；作者重新搜索一次即回（L4 搜索缓存，成本极低）；旧 app.db 保留原地不删（非自产文件，1.1MB 无害）；User Story #17 与功能总账 G 域已回填 | v1.53 |
| **合集接入进本版（增强端点 #4 拆分）** | **已拍板（2026-10-28 用户确认"可以啊"）**：合集从"待拍板 #4 / Out of Scope 后置"拆出，**进本版（阶段一）**。能力=作者页加「合集」入口（作者建了合集才显示）→ 合集内视频列表 → 按合集批量下载；数据源=**TikHub 专属**（红狐无合集接口；微信合集=作者自己在视频号助手后台建的分组，我们只读不写）：`fetch_user_collections`（合集列表，返回 topic_id，$0.01/次）+ `fetch_collection_videos`（合集内视频，带 media 直链可下载，last_buffer 翻页，$0.01/页）；**下载路径复用 L2**：合集内视频优先查 author_list_snapshot 快照（命中 0 成本），未命中页走合集端点续拉；评论 / 主页资料 / 号内搜索仍后置 P3；同步回填=功能总账 A 域 / Implementation Decisions 增强端点段 / Out of Scope / 待拍板 #4 | v1.54 |
| **合集列表缓存（v1.54 补充）** | **已拍板（2026-10-28 用户确认"可以啊"）**：**合集列表搭 L2 顺风车**——与作者视频列表同取、同存、同过期（点开作者页 L2 刷新时一并调 fetch_user_collections，塞进 author_list_snapshot 结构承载，TTL=120min 同 L2），不新建缓存机制、边际成本 0；合集 tab 命中即展示 0 成本、无网络等待；合集内视频下载仍按 v1.54（优先查快照、未命中页走合集端点 $0.01/页） | v1.55 |
| **状态卡片规格（监控口径回填）** | **已拍板（2026-10-28 用户确认"可以啊"）**：①**监控频率口径回填**——"每天 2–4 次"旧残留 6 处全部统一为 v1.22 权威口径"打开界面即同步 + 标星作者每天 2 次兜底"（总账 C 域/成本受控/接口映射/监控器/P1 表/Implementation Decisions）；②**状态卡片**——双供应商各一行独立状态徽标+错误原因（401/402/429/5xx 语义映射）+当前生效链路标注；**不显示余额**（上游无余额查询 API）；刷新=启动探测一次+业务出错实时更新，不做定时轮询；异常时给「打开后台查看/充值」跳转入口；**逆向余额接口=后续可选增强不排期**（浏览器自动化抓后台接口可行但=黑盒依赖，页面改版需重抓；阶段二需要精确余额监控时再做） | v1.56 |
| **播放器 / 任务管理 UI 沿用** | **已确认（2026-10-28 默认值落档）**：播放器、下载任务管理（进度/状态/速度实时、取消/删除/清空、批量去重）**沿用现有前端现成能力**，无新开发（前端 38 接口复用不改；SSE 进度通道保留）；User Story #9/#10 已覆盖，功能总账 B 域不变 | v1.57 |
| **合集数据建模（1:N，方案 A）** | **已拍板（2026-10-28）**：关系基数**官方实锤=一个视频只能挂一个合集**（微信小店成长中心 FAQ"目前只能挂一个"+ 微信开放社区"合集不能交叉，一个视频只能加入一个合集"，两源互证）→ **1:N，方案 A**（初稿曾建议 B 关联表，那是基数未查证时的保守兜底；查证后按事实建模，不搞过度设计）。**DDL**：新增 `collections` 表（topic_id PK=微信合集 ID、topic 名、topic_type、author username FK、封面、video_count、fetched_at）+ `author_videos` 加 `collection_id` 列（FK→collections.topic_id，可空=未入合集）；合集视图=`WHERE collection_id=X`；下载仍走 L2 快照命中优先（0 成本），未命中页走合集端点补；若未来微信放开多合集（当前官方口径否），再升关联表（迁移可控） | v1.58 |
| **互动数展示 + 上游字段接入（少写代码）** | **已拍板（2026-10-28 用户确认"可以啊"）**：①**互动数展示规格**——列表卡片=点赞+评论 2 项、详情页=全 5 项（read/like/fav/forward/comment）、过万缩写（1.2万）、0 值正常显示、随 L2 快照刷新（120min 级）+ 详情页实时；搜索列表不显示互动数（搜索命中项不带互动数，不为此加详情调用）；②**上游字段接入 4 个（零额外调用，列表响应自带）**：`exportId`→author_videos 存列（TikHub fetch_video_detail 入参支持 export_id，兜底下载免反查 object_id，**待 TikHub 权限开通后验证 export_id 格式直通**）；`topic`（话题标签 JSON 数组）→存列，本地按话题筛选，省自提取；`width/height`→存列，详情页画质/横竖屏展示；`headUrl`→authors 表列表刷新顺带更新；③**不接**：短链 get_work_by_link 互动数（字段命名第二套 likeNum/commentNum/collectNum/shareNum，第二套映射=负资产）、location（无价值） | v1.59 |
| **TikHub 风控解除实测 + 作者维度/评论接入 + 数据来源路由（统一缓存 TTL 表）** | **已拍板（2026-10-28 用户确认"接呗全接上"+"可以啊"）**：①**风控状态更新（2026-10-28 实测，scripts_probe_tikhub_channels.py）**：v1.50 记录的"账号级风控 400/403 1010"**已解除**——fetch_user_videos / fetch_user_profile / fetch_video_comments **全 200 计费成功**；fetch_search 仍 400（响应明示"核对参数用 demo 测试、不扣费"=参数问题非风控，待 demo 参数核对）；连带 v1.50 搁置项（断点续传 TikHub 链路、export_id 直通验证）**重新可验证**；②**作者维度数据接入**：authors 加列 follower_count/following_count/like_total，来源=`fetch_user_profile`（TikHub 独有，红狐 search_users 仅昵称/头像/封面/简介/uid，无统计）；**懒触发**（用户点开作者详情才查缓存，同步流程不预拉）+ **TTL 7 天**（展示性慢变量；24h 预拉方案否决=100 作者 ¥216/月 vs 7 天懒触发≈实际点开量，下载用户不看粉丝数）；③**评论接入**：新表 video_comments，来源=`fetch_video_comments`（TikHub 独有；object_id=纯数字，object_nonce_id 格式 422 已实测）；**懒触发**（点「查看评论」才调，列表 comment_count 计数提示 0 成本）+ **TTL 7 天** + 默认 1 页 20 条（加载更多再翻页）；④**详情 read/spec/file_size 补全**：懒触发（打开详情页，L3 无缓存才调 fetch_video_detail $0.01）+ 入 L3 media TTL 4-12h；⑤**数据来源路由原则（红狐便宜字段少 vs TikHub 贵字段全的平衡）**：**按数据类型路由，不二选一**——同一数据谁便宜谁主（红狐 ¥0.04 vs TikHub ¥0.072，差价 80%）、贵的只兜底；TikHub 独有能力（read/作者统计/评论/合集）=**低频+懒触发+缓存**，不进入高频路径；浏览/下载/搜索全走红狐 0 接触 TikHub；⑥**统一缓存 TTL 表**（数据+fetched_at+TTL+来源一张表，过期判断统一，重新拉时谁便宜谁先上）：主路径同步预取=作者列表 120min（48h 硬上限）/详情 media 4-12h/合集 120min（顺风车）/搜索 24h\|1h；展示性懒触发=作者 profile **7 天**/评论 **7 天**；⑦**第一次边界**：冷启动"全字段"=作者档案层（profile 必调一次 $0.01 建全档案）；视频层 read/评论**不批量拉**（100 条视频首次全拉=$1+，成本爆炸），永远按需；⑧**风控=长期常态架构原则**：三层风险（供应商被上游风控/TikHub 现状→红狐互备+熔断切换；我们的 key 被供应商风控→401/402 全局熔断+状态卡片；我们被平台风控风险最低），架构吸收=双供应商互备+熔断+缓存兜底（**已有数据永续可用、实时数据尽力而为**），不是"等一次解封一劳永逸" | v1.60 |
| **定价毛利恒正确认 + 缓存命中扣点改免费（用户感知）** | **已拍板（2026-10-28 用户确认"定价没问题是赚的"+"不能太暴力，考虑用户感受"）**：①**定价核查结论（复核 v1.28）**：**毛利恒正，定价不动**——核心保证=点数即成本上限（任何卡密对上游成本 ≤ 卡点数×¥0.072 保守上界）+ 扣点先于调用（余额不足 429 不调上游）；全档倍率 1.4x-4.3x；1 天 3 点全用满成本 ¥0.22<¥0.9；30 天 100 点 ¥7.2<¥9.9（毛利 27.3%，红狐优先后实际更高）；"重度用户 ¥30-50/月 vs ¥9.9"为伪矛盾——30 天卡 100 点=成本封顶 ¥7.2，用完断提示购新卡，用户消耗多=买卡多=收入多；②**缓存命中扣点策略：A→B**——**缓存命中 0 成本 0 扣点**（v1.28 的"照扣 1 点=差价最大化"否决=用户感知差"点数虚耗"、太暴力；new-api Cache Billing 打折做法的更彻底版）；规则=**扣点只在真实调用上游时发生**，用户为"新数据"付费、看旧数据永远免费；对账更精确（点数消耗=真实调用数，毛利率恒定 1.4x-4.3x）；重度用户新内容消耗不降，仅"虚耗"消失；③**汇率风险标注（v1.61 后续待聊）**：$ 计费 ¥ 售卖，人民币贬值时 TikHub 成本涨（¥0.072=7.2 汇率假设），30 天卡毛利 27.3% 会缩水；billing_config.fx_usd_cny 可调表（§6 汇率） | v1.61 |
| **缓存层扣点分级（修订 v1.61 全免；v1.62 后二次修订命中值 0.5→0.1）** | **已拍板（2026-10-28 用户"不能太暴力，但也不代表全部免费；用户察觉不到的可以合理收"；命中值用户再拍=0.1 象征性"赚少点也行"）**：**原则=扣点只随用户主动操作触发上游，按"操作频率×感知度"分级**——①**高频易察觉（耗点快）**：作者列表 L2/视频详情 L3/搜索 L4/短号 L1/作者主页/评论/直播，**缓存命中=0.1 象征性**（真实调用仍 1 点；0.1 点≈¥0.01 用户几乎无感，纯赚部分缩水但成本 0 仍全毛利）；②**后台自动行为 0 扣点**：标星每日同步/监控/合集列表顺风车（用户未发起任何操作，扣点=暴力中的暴力；成本记运营账由售价毛利覆盖）；③**0 成本复用 0 扣点**：下载直链复用、L1 旧数据纯本地读；④**翻页=1 点/页全价**（真实拉新页）；⑤**落地=route_rate 表加 `cache_points` 列（REAL，0/0.1/1 逐路由显式配）**+ billing_config.cache_discount=0.1 兜底（新路由未配防白嫖）；行业对照=new-api Cache Billing 全局比例/one-api 配置表，我们路由少（个位数）显式列更清晰可审计；⑥修订链：v1.28"命中照扣 1 点"（暴力）→ v1.61"命中全免"（放弃收入）→ v1.62"0.5 半价"→ **v1.62 二次修订"0.1 象征性"**（用户感知最优、纯赚保留）；**汇率风险（v1.61 标注）仍待拍板**，下一轮讨论 | v1.62 |
| **汇率风险处置（$ 计费 ¥ 售卖）** | **已拍板（2026-10-28 用户确认"可以"）**：三层消化，**不改定价**——①**常规机制**：`billing_config.fx_usd_cny` 运营定期更新（周/月，人工或脚本抓价，改表即生效不动代码）；②**天然对冲**：红狐优先路由=人民币/港币计价不随美元动，TikHub 仅低频懒触发（详情/评论/作者页/合集）——重度用户月 500 次调用（红狐 400+TikHub 100），汇率 7.2→8.5 总成本仅 +5.6%（¥23.2→¥24.5）；③**极端预案**：人民币持续贬值超 **8.5** → 上调卡价或降 30 天卡点数（改表即可）；④**明确不做**：定价按 $ 锚定（国内用户不现实）、客户端改价（违反"价格永不在客户端"）——成本侧 fx_usd_cny 单独调、收侧 route_rate 单独调，互不影响 | v1.63 |
| **阶段二对账——收入侧闭环（收/支分离完整落地）** | **已拍板（2026-10-28 用户确认"可以啊，没什么了吧"）**：**收入子系统不开发**——收入天然在柠檬后台（批次/卡密状态/售价，销售系统本身记账），月末导出"**已激活**"卡密金额=收入（口径：未激活卡=库存不是收入，行业=实际售出/消耗才算）；**成本侧必须自建**——api_usage 计量（v1.23 已落档 DDL）：柠檬不知道我们调上游花了多少钱（红狐 ¥0.04/TikHub ¥0.072 是网关花的钱），只能自己记；**毛利 = 柠檬收入（已激活导出）− api_usage 成本**；**阶段归属（v1.49 边界确认）**：阶段一客户端直连上游无网关→**不计量不报表**（不阻塞自用闭环）；阶段二上网关后计量（转发顺手记）+ 柠檬导出对账=商业闭环必做；成本计量用途=对账/供应商观测/定价严谨性（定价前必做）/P95 超时调参；**api_usage 不是用户扣点记录**（points 余额是用户侧，api_usage 是运营侧成本账） | v1.64 |
| **TikHub 链路验证通过（风控解除后实测，scripts_verify_tikhub_export.py）** | **已验证（2026-10-28 实测 200/206）**：①**export_id 直通 ✅**——红狐列表 exportId（`export/UzFfBgAA...`）直接喂 TikHub `fetch_video_detail` 的 `export_id` 入参 → **HTTP 200 返回完整详情**（id/object_nonce_id/read_count/like_count/fav/forward/comment/media 全字段）→ **兜底下载免反查 object_id 成立**，v1.59"待 TikHub 权限开通后验证"解除，红狐→TikHub 兜底链路闭合；②**TikHub 断点续传 ✅**——media full_url（wxapp.tc.qq.com CDN）Range 探测 → **HTTP 206 + Accept-Ranges: bytes + Content-Range: 0-1023/3504612** → **支持 Range，断点续传 TikHub 链路可用**（v1.50 搁置项解除，与红狐 206 同设计）；③**read_count 确认在详情**——v1.60"详情页 read 懒触发"数据源实测可用；④验证脚本保留（scripts_verify_tikhub_export.py 可复用） | v1.65 |
| **自动更新授权校验：砍掉（不做）** | **已拍板（2026-10-28 用户确认"根本不用做不用管"）**：**不做自动更新授权校验**——①**为什么行业里别人做**：软件本体收费（新版=新授权价值）/版本带新功能（新版=付费点）/防旧版破解蔓延/授权续期提醒——4 场景全基于"新版=钱"；②**我们模型全不适用**：软件本体免费分发（安装包人人可下，无授权价值）、功能锁由**激活校验+点数**管（跟版本无关，新版功能照样锁）、破解用户不走正规更新渠道拦不住、续费提醒软件内可做；③**真正防线**=激活校验（卡密服务端校验，非本地）+ 一卡一机绑定，与更新无关；④更新保持 v1.47 定案：公开静态桶 latest.json、人人可更新、本身不收费；⑤避免"第二道没必要闸"（多一层=多一个故障点=更新失败差评，用户曾担心更新卡死） | v1.66 |
| **fetch_search 400 根因核对（非参数问题，搜索备胎暂缓）** | **已核对（2026-10-28 实测，scripts_probe_tikhub_search.py 4 组参数全 400）**：最简 `{keyword}` 单参也 400 → **非参数问题**（契约入参 keyword 必填已验证；business_type/sort/publish_time 枚举组合全试均 400），亦非风控（微信视频号通道 fetch_user_videos/fetch_user_profile/fetch_video_comments 均 200，仅 wechat_search 域 400）= **TikHub 搜索域服务侧状态问题**；**处置：搜索主链路=红狐 search_work（¥0.04 实测 200），TikHub fetch_search 备胎暂缓不接入，不阻塞**；后续若需重试（TikHub 侧修复后）用 scripts_probe_tikhub_search.py 复验 | v1.67 |
| **挂起项审查 + 自动更新授权校验残留清理** | **已清理（2026-10-28 用户"剩下挂起的有些是旧的不需要的，都看一下"）**：审查挂起项结论——**旧的**：功能总账/阶段二新增表/阶段归属注释 3 处"自动更新授权校验/加授权校验"残留（v1.66 已砍未同步）→ 已全部修正为"不加授权校验、更新保持 v1.47 公开免费"；**要等**：TTL 观察实验（存活 2 天，10-27/28 两次 206 VALID，观察到过期）；**上线前必做**：柠檬正式 4 档规格（1天3/3天10/7天25/30天100 星尘，v1.33/v1.44 定价已定稿）+ 关闭 downloader 3 个用户接口（注册/登录/me，与"不做用户系统"一致）；**可选**：红狐直链 TTL 实测（用户实测约 10 天，可等 TikHub 观察过期后合并）；**用户动作**："号匣"商标/域名/社交账号核实（无 Spec 落点，用户最终核实） | v1.68 |
| **缺口全清 + decode_key 实测 + 旧标注清理** | **已收口（2026-10-28 实测 + 清理）**：①**decode_key 类型实测 = str（9 位纯数字，`58175253...`）**——契约 §4"大整数按字符串处理"规范实测确认，Python 解密模块按字符串读（v1.40 Go 透传已不存在），列类型无碍（统一 TEXT）；②**旧标注清理**："增强 4（后续迭代）"与"评论导出/主页资料增强"2 处过时——主页资料/评论 **v1.60 已接入本版**、合集 **v1.54 已进本版**，已改标注，真正后置仅剩 `fetch_search_channel_videos`（号内搜索 P3）+ 评论导出（P3）；③**仅剩 2 个运营侧小实测点（标"上线前实测"，不阻塞）**：日阶梯折扣（0–1k 起）是否覆盖微信系端点（calculate_price 需 token）、live_history read_count 是否返回 | v1.69 |
| **端到端解密验证通过（阶段一核心闭环全绿）** | **已验证（2026-10-28 实测，scripts_verify_e2e.py + scripts_probe_python_decrypt.py）**：①**Python 解密算法**（ISAAC-64 keystream + 前 128KB XOR，1:1 翻译自 Go 开源 Hanson/WechatSphDecrypt）本地样本验证通过（ftyp + ffprobe 52.3s 可播）；②**端到端全链路实测通过**：TikHub fetch_video_detail 拿真实素材（full_url + decode_key='1536631228'）→ HTTP 下载 3,504,612 bytes → Python 解密 → **ffprobe 出片 18.27s 可播**（mov/mp4）→ **"搜索→下载→解密→出片"阶段一核心闭环成立**；③**观察点（落档）**：下载长度 3,504,612 vs `file_size` 字段 9,580,439 不一致——下载长度以 HTTP Content-Length/Content-Range 为准（两次探测均 3,504,612 一致），`file_size` 字段仅作参考（口径存疑，实施时校验）；④解密=纯 Python 本地（无 Go 进程、无微信依赖，符合项目规则），decode_key 字符串→int 喂算法 | v1.70 |
| **可观测性四件套补全（日志/指标/告警/追踪最小骨架）** | **已拍板（2026-10-28 用户"可观测性就是打日志/指标那些东西，要搞成规格吗"）**：写，但**只写最小骨架防过度设计**——日志=api_usage（v1.23 DDL）+event_bus（已有，地基）；指标=api_usage 聚合（L1 缓存指标已有 + 供应商维度：错误率/P95/双供应商占比，聚合查询不新建设备）；告警=**最小 3 条阶段二启用**（成本超周预算/错误率突增/熔断触发，运营侧日志+巡检人工看，不建独立告警平台）；追踪=request_id 贯穿 客户端→网关→柠檬→上游（复用 api_usage.biz_id）；**明确不做**：独立监控看板/告警系统（阶段一自用=日志+报表足够）——落地位置：527 行可观测性节 | v1.71 |
| **日志埋点规范（分层分级必埋点清单）** | **已拍板（2026-10-28 用户"哪些地方必须加警告日志/error 日志"）**：补全 527 行可观测性节——**分级**：INFO=正常 / WARNING=可恢复异常（有兜底）/ ERROR=失败需处理（必带 request_id+参数摘要+耗时，不打卡密/key 明文）；**必埋点清单**：上游调用层（单次 5xx/超时/429/401/402→WARNING，重试仍失败/熔断→ERROR）、网关计费（**扣点失败/幂等冲突→ERROR**，钱相关必查）、柠檬对接（5xx→WARNING，兑换/绑定/token 失败→ERROR）、下载解密（中断→WARNING，**最终失败/解密失败/文件损坏→ERROR**=用户拿不到文件最高优先级）、缓存层（刷新失败→WARNING，event_bus 兜底）、自动更新（检查失败→WARNING 静默，更新包下载失败→ERROR）、全局兜底（未捕获异常→统一 handler ERROR+traceback） | v1.72 |
| **异常处理纪律（try/catch 不空等）** | **已拍板（2026-10-28 用户"try catch 里面不能空等"）**：补全 527 行可观测性节——①**禁止空等/空转**：catch 后必须三选一落地（降级返回/有上限重试/熔断切换），**禁止静默吞异常后继续等待**（无感知空等=最差，用户卡住不知情）；②**等待必带上限**：重试=固定次数+退避（仅明确瞬时错误才重试，同动作失败 2 次换通道），超时=连接 5s/读 30s/90s（v1.45），禁止无限等待/空转轮询；③**读超时不重试**（宁可等到干完不白丢费，v1.45）；④**禁止裸 catch 不打日志**（按 v1.72 分级必打） | v1.73 |
| **阶段一遗留端点补测（风控解除后，主旅程 3 条链路）** | **已补测（2026-10-28 实测，scripts_verify_phase1_leftovers.py）**：①**A. `fetch_channel_id_to_username`（L1 短号映射）= 422 入参格式确认**：channel_id 必须 `^sph[A-Za-z0-9_-]+$`（模式校验明示，端点活非风控非挂）——**真实有效 sph ID 的 200 验证缺样本（分享短链短码 ≠ channel_id；v1.77 已化解：L1 主链路=share_url 直达 username，此端点降级可选，不再阻塞）**；②**B1. `fetch_live_history` = 200 ✅**：人民日报回放列表返回（id=displayid=object_id 15036563919475050632、readCount 字段存在）→ **之前"live_history read_count 待实测"项闭环**；③**B2. `fetch_live_detail` = 端点活（200 计费）但当前样本不可用（v1.76 深化补测修正）**：人民日报"回放"条目 liveInfo=null=**普通视频对象非真直播回放**（objectType=0），其 object_id 喂 fetch_video_detail 亦 bad_input（条目已失效/私密）→ **fetch_live_detail 需真直播条目 live_id（liveInfo 非空），非直播回放下载必经环节**（详见 v1.76）；④**C. `fetch_video_detail(share_url)` = 200 且真实解析闭环（v1.77 升级）**：真实短码 As68wzqwSd → **200 REAL-DATA**（id/username/nickname/media 全返回，username=v2_...@finder）——**贴单视频链接链路端到端可用**——**阶段一主旅程全部端点链路实测收口，两个实施时调试点均已化解（A=v1.77 非必经、B2=v1.76 非必经）** | v1.74 |
| **全文一致性审查（早期/后期矛盾 25 处全部回填）** | **已收口（2026-10-28 全文通读 1459 行 + 批量回填）**：**A 类事实矛盾 21 处修复**——①顶部状态行 v1.39→v1.75；②§3 定价表草案标注"已废弃（v1.44），唯一真相源=§2.5 卡型规格"；③日阶梯折扣"待实测"→已实测不覆盖（v1.13 allow_discount=false）；④L3 口径矛盾（4-12h vs 24h×0.8）→拆两参数并存：详情 media 短 TTL 4–12h（v1.60）+ 下载前安全窗口=实测×0.8 出数前 24h 保守（v1.16），总账同步；⑤L1"链路全实测可用"→"入参格式 422 实测确认，真实 sph ID 200 待实施样本"；⑥合规定位"不进对外付费产品链路"→红狐主=合规 API（对外商业化主数据源）/TikHub 灰=内部备用（不对外承诺）；⑦Out of Scope"合规商业化阶段二也不做"与阶段二定义矛盾→修正为卖数据服务差价（API 中转站模式）；⑧§2.6 更新源"接柠檬 updates/check"→OSS 桶（v1.47）；⑨json-bigint 前端改造残留→v1.42 前端零改造已闭环；⑩⑪Docker 解密残留 2 处→v1.40 Python 内嵌；⑫⑬⑭decode_key"待实测"3 处→v1.69 已实测 str 回填；⑮⑯read_count"待实测"2 处→v1.74 已实测回填；⑰密钥"不进 .env"旧口径→按 v1.46 阶段区分（阶段一 .env/阶段二 server-secrets），前缀补 REDFOX_；⑱⑲L4 决策流程"调 TikHub"2 处→红狐主；⑳商业模式段/流程"TikHub 泛指"2 处→双供应商；㉑P3 实施 21"每次 TikHub 调用"→上游调用。**B 类陈旧措辞 4 处**：增强端点归属（3 个已进本版仅号内搜索 P3）、1276 行"预留 profile/comments"回填、app 名「视频号下载器」→「号匣」4 处、Further Notes"剩余：充值金额需实调确认"→v1.13 双 200 已闭环、字段映射核对表 7 项待实测标注→收口总注。**新纪律延续 v1.43**：旧段落必须随拍板同步回填，本轮 25 处全部为同类根因 | v1.75 |
| **B2 深化补测（fetch_live_detail 定性修正：非直播回放下载必经环节）** | **已补测（2026-10-28，scripts_probe_live_scene.py + scripts_probe_live_id_field.py，成本 $0.07≈¥0.5）**：①**scene 枚举 5 组合全 200 计费但 data=bad_input**——scene=0/1/2/3 × ±finder_username 全试，错误提示"无效的文章 URL/finder username/视频 object_id"（无效参数被微信处理后仍计费）；②**lives[] 完整字段打印=id=displayid=15036563919475050632（v1.74 推断正确）但 liveInfo=null、objectType=0**——人民日报"回放"条目实为**普通视频对象、非直播回放条目**；③该 object_id 喂 `fetch_video_detail` 亦 bad_input（条目已失效/私密，sessionBuffer 含 deletetime 语义）→ **当前样本无法验证 fetch_live_detail 真实返回，无论 scene 取何值**；④**架构修正（重要）**：直播回放下载**不依赖 fetch_live_detail**——`fetch_live_history` 列表条目（契约 lives[N] 自带 media 直链）→ 复用普通视频下载/解密链路（v1.70 已验证）；`fetch_live_detail`=直播间详情可选能力（需真直播条目 live_id，即 liveInfo 非空条目才有），阶段一无此需求 → **降级为可选能力、不排期**；⑤**调试点收敛**：A（真实 sph ID 样本）为唯一剩余实施时调试点；B2 从"实施时确认 scene 枚举"降级为"遇真实直播回放账号再验，不排期"；⑥脚本保留（scene 枚举/live_id 字段打印可复用） | v1.76 |
| **A 调试点实质化解（L1 主链路=share_url 直达 username，fetch_channel_id_to_username 降级可选）** | **已收口（2026-10-28 实测，scripts_verify_l1_channel_id.py + scripts_probe_l1_link_path.py，成本 ¥0.04+$0.01≈¥0.52）**：①**红狐 uid 排除**——searchUser 返回 uid=32 位 MD5 风格哈希（5d94e58a…），**非 sph 前缀**，喂 fetch_channel_id_to_username 422 模式拒绝（红狐 uid ≠ TikHub channel_id）；②**真实短码解析闭环**——`fetch_video_detail(share_url='https://weixin.qq.com/sph/As68wzqwSd')` → **200 REAL-DATA**：id=15041290733490477116、username=`v2_060000…708@finder`（棋虎南厦）、nickname、media 全返回 → **share_url 链路从 v1.74"入参接受"升级为"真实解析闭环"，且直接返回作者 username**；③**红狐 workLinkDetail 同短码 200**——返回元数据+exportId（`export/UzFfBgAA…`）+nickname，**无 channel_id 字段**（仅作资料/export_id 入参用）；④**架构修正（L1 简化）**：用户贴链接（分享短码）→ TikHub fetch_video_detail(share_url) 拿 username → 红狐 get_user_works(username) 拉列表 → 直链下载——**不再依赖 fetch_channel_id_to_username**；该端点降级为可选辅助（仅处理含 sph 前缀 ID 的主页链接场景，无真实样本验证不影响主链路，实施时遇主页链接再做兜底=链接页取昵称→红狐 searchUser）；⑤**调试点清零**：A（v1.77 非必经）+ B2（v1.76 非必经）双双化解，**阶段一主旅程全部端点链路实测闭环**；⑥脚本保留（红狐 uid/短链解析/红狐 workLinkDetail 均可复用） | v1.77 |
| **隐形接口盘点（红狐全端点实测定位，L1 双路径+入参修正）** | **已收口（2026-10-28，scripts_probe_redfox_dl_link.py / _redfox_list_url.py / _redfox_playable.py / _redfox_dl_playable.py，红狐 9 次≈¥0.4，TikHub 0 次）**：①**红狐 `videoDownload/sph`（parseWork/videoDownload/sph，入参 url=分享链接）= 单端点直给下载直链**：downloadUrl=finder.video.qq.com/stodownload?encfilekey=…，**实测未加密可播**（ftyp isom，ffprobe 310.13s）→ **贴链接直接下载=红狐 1 次 ¥0.04 免解密**（原设计走 TikHub share_url ¥0.072+解密）；②**红狐 `get_user_works` 列表 videoUrl 实测可播**（ftyp isom，ffprobe 18.27s）——**encfilekey 仅是 CDN 防盗链签名参数，不代表内容加密** → v1.39"红狐直链免解密"获实证补强（列表源+链接源均验证）；③**queryWorkList 入参=nickname（昵称精准匹配）**：username/findName 入参实测 total=0、nickname 入参 12781 条 → **v1.77 链路修正**：share_url 拿的是 nickname（棋虎南厦）→ `get_user_works(nickname)`，不是 username；④**时效**：红狐广域库 T+1，当天新发布作者列表 total=0（棋虎南厦 10-27 发布 10-28 查 0 条）→ 列表兜底 TikHub `fetch_user_videos(username)`（实时）；链接直接下载不受影响（parseWork 实时）；⑤**nickname 不唯一风险**：精准匹配可能命中重名账号 → 缓存"链接解析所得 nickname↔findName"配对，列表场景以链接解析作者为准校对；⑥**红狐微信视频号端点盘点完毕**（searchWork/queryWorkDetail/queryWorkList/workLinkDetail/searchUser/videoDownload/transcript）：videoDownload 判定接入（贴链接直接下载主端点）、transcript 维持不采用（v1.13 已拍板）；⑦脚本保留（红狐直链可播性/列表入参/下载端点均可复用） | v1.78 |
| **便利接口排查（平台便利设计 vs 服务侧故障定性，fetch_channel_info 认证信息接入）** | **已收口（2026-10-28，scripts_probe_convenience.py + scripts_verify_l1_channel_id_real.py，TikHub 3 次 $0.03 + 红狐 1 次 ¥0.04 ≈ ¥0.26）**：①**`fetch_search_videos`（跨号搜视频，带 duration/sort/publish_time 筛选）= 400 实测**——与 fetch_search 同形态（"Request failed...不扣费"）→ **TikHub 搜索域（fetch_search + fetch_search_videos）均服务侧不可用，跨号搜索唯一来源=红狐 searchWork/searchUser**（v1.67 定性补全）；②**`fetch_channel_info` = 200 实测（便利发现）**——返回 **Channels ID（sph 前缀，sphi9BjV8GK0Zsl=人民日报，username→channel_id 反向映射）** + 认证主体（服务单位=人民日报社，官媒认证标记）+ IP 归属地/资料所在地 → **接入为作者资料可选增强**（认证标记/官媒筛选/可信度展示，懒触发 TTL 7 天，与 profile 互补）；③**`fetch_channel_id_to_username` 终极定性 = 400 服务侧不可用**：用 fetch_channel_info 拿到的**真实 sph ID（sphi9BjV8GK0Zsl）**喂入=400（"Request failed...不扣费"，与搜索域同形态）→ 从"可选辅助（缺样本）"改为"**实测 400 彻底移出**"；v1.74 的 sph1dWScuVJkYKw 400 亦非样本问题；主页链接兜底=链接页取昵称→红狐 searchUser；④**红狐 `parseWork/parse`（通用下载）= 200 但无增益**：返回 videoUrl 直链但 title=""/duration=null/**无作者信息** → 不接入（videoDownload/sph 已覆盖且带 desc）；⑤**平台便利设计总结**：TikHub `fetch_video_detail` 三入参（object_id/export_id/share_url）一步拿 media+decode_key=便利到位；红狐 `videoDownload/sph` 链接直下=便利到位；**真正难受的是搜索域+channel_id 域三个端点 400（平台侧故障，非设计问题）**；⑥脚本保留（便利排查/channel_info/真实 sph 验证可复用） | v1.79 |
| **400 官方确认（平台侧定性落锤，TikHub 文档实据）** | **已确认（2026-10-28，官方文档 tikhub.apifox.cn README + tikhub.io/zh/wechat-api）**：①**官方对 HTTP 400 的定义**：`400 Bad Request - The request format is incorrect or parameters are invalid. Sometimes occurs due to server internal errors`——**官方明确 400 含"服务器内部错误"情形**，且 400 不计费（错误响应自带 "You won't be charged"）；②**我们 3 端点 6 次实测全同形态**：fetch_search（4 组参数含最简 keyword 单参）、fetch_search_videos（标准 keyword）、fetch_channel_id_to_username（2 个真实有效 sph ID）→ 参数不可能全错（含文档演示级入参）→ **属官方定义的"服务器内部错误"类 400**；③**背景**：微信系 2026-06-13 经历 V1→V2 全量迁移（wechat_channels/* → wechat_channels/v2、wechat_search/v2），部分端点迁移后服务侧不稳；④**平台侧无"维护中"标注**（apifox 端点页照常展示参数），但错误响应提供支持通道（Discord + user.tikhub.io 工单）→ 需要时可提单反馈；⑤**影响面**：搜索域（fetch_search/fetch_search_videos）已被红狐 searchWork/searchUser 完整替代、channel_id 域已被 share_url 直达替代——**三处 400 均不影响阶段一主链路**；⑥状态记录：可观测性-平台故障台账挂起（若平台恢复，搜索/短号端点可重新评估） | v1.80 |
| **前端安全修复（P0 XSS + P1 状态收敛 + 门禁上线）** | **已拍板并执行（2026-10-28 用户"我们进行修复吧"）**：①**行业标准核实**（OWASP Web Frontend Security "innerHTML with extreme caution/textContent 替代/禁 eval"、Electron 官方 CSP 禁 inline、WebView2 "Treat all web content as insecure"、Redux 单一数据源）→ 4 类问题分级：**P0 XSS**（8 处内联 onclick 引号拼接 + innerHTML 直插外部数据）/ **P1 状态双源**（State 层 vs app.js 全局变量）/ **P1 无 CSP + 内联 onclick 泛滥** / **P2 可维护**；②**修复**：内联 onclick 引号拼接**全改 `data-action` + document 级事件委托**（app.js `initGlobalDelegation()`，覆盖 cancel/retry/open-video/open-author/remove-author/toggle-select/history/confirm-remove，为 CSP 铺路）；innerHTML 直插外部数据（视频标题/作者昵称签名/日志消息/toast/删除对话框/error 弹窗/头像 URL）**全加 `escapeHtml` 转义**；**根因修复=utils/html.js 的 escapeHtml 存在但 index.html 从未加载**（已补到所有脚本最前）；状态写路径**禁直改 State._data**（app.js pollNewVideos 改走 `State.videos.setAuthorVideos` 合并插入，保持反向索引+事件一致；全项目扫描直改残留=0）；清理手写转义死代码（escapeAttr/escAttr 反斜杠式不可靠）；③**验证**：node --check 12 文件全过；FastAPI 起服务实测 4 资源 200；浏览器实测页面 0 console error、日志 200 行 escapeHtml 渲染成功、委托链路注入测试（data-action cancel → cancelDownload → toast）全通；④**门禁上线**：`scripts_check_frontend.py`（L0=全量 node --check；L1=R1 内联 onclick 外部字段插值/拼接、R2 innerHTML 直插外部数据未转义、R3 setAttribute(onclick)/手写转义复活）——**首次运行即抓出 2 个真漏网**（videoListRender:633 缩进漏网、doc_sync_monitor:384 error 弹窗 title/message 直插，均已补修）；自证通过（注入违例 FAIL→还原 PASS）；**纪律=前端改动必跑该脚本，退出码 0 才可过**；⑤**遗留（独立排期）**：CSP 响应头 + index.html 静态内联 onclick 迁移（switchModule 等，无数据拼接无注入风险，需先清 inline 才能上 script-src 'self'）；低危项=视频封面 cover_url/video.id 属性上下文未转义（id 后端生成，记录不误伤）；状态别名（_currentPageNum 等）保留为只读视图 | v1.81 |
| **下载链路三连环·环3收口：L5 校验标准修正（file_size 口径存疑定案，v1.70 观察点升级为拍板）** | **已拍板（2026-10-28 用户"按你的想法去做吧"，v1.82）：A 方案——L5 校验=下载字节权威**。事实依据：①v1.70 端到端实测下载长度 3,504,612 bytes（两次探测一致）vs `file_size` 字段 9,580,439（差近 3 倍，口径存疑——推测为不同码率/duplicateFileSize 兜底口径，与 CDN 实际吐出字节对不上）；②既有设计（v1.18/v1.21）L5 校验"对照 file_size"若照旧实施→文件完整（Content-Length 对齐）却被判校验不过=误判。**决策**：①L5 完整性=**HTTP Content-Length/Content-Range 字节对齐为权威**（下载完成字节数入库作校验基准）；②`file_size` 字段**降级为纯 UI 展示**，不做校验依据（入库纪律 v1.13 不变：列表 duplicateFileSize/详情兜底，仅展示用）；③解密后 ffprobe 抽查可播性（仅异常时排查）；④file_validator 有效性判定=stat 存在性 + 大小>0 + 与下载记录字节数一致；⑤同步回填 632/637 行校验描述（对照 file_size→对照下载 Content-Length）；⑥断点续传（v1.50）不受影响：续传完成后同样以最终 Content-Length 对齐校验 | v1.82 |
| **实施前风险逐项拍板统一落档（①成本感知转备 ②解析防御五件套 ③红狐 T+1 方案 A+空确认标记+total=0 三态区分）** | **①供应商故障无自动切换→成本感知转备（2026-10-28 用户拍板，复杂度 100-150 行、零新依赖）**：按失败类型分类处置——**连接失败/5xx→转备 1 次**；**429→指数退避不转备**（上游会自愈，v1.45 延续）；**401/402→转备**；**400→按端点判断**（搜索域 400=平台侧故障 v1.80，转备无益不转；参数类 400 同）；**读超时→不转备不重试**（防双计费，v1.45 延续）；+ **端点粒度主备映射表**（有备才转、无备快速报错）+ **连续失败 ≥3 →熔断 60s 快速转备**（**修正 v1.45"熔断切换后置阶段二"：供应商级熔断提前到阶段一**，计费级熔断仍后置）+ `fallback_enabled` 布尔开关（默认开）+ 状态卡片显示生效链路。**②上游结构漂移→解析防御五件套（阶段一最低配置）**：行业四层防线（防腐层/契约测试/宽容解析/运行期监控+弹性降级）裁剪为五件——(L1)防腐层=适配层自然形态；(L2a)宽容解析=`.get()` 链+关键字段清单+缺失校验告警（新写几百行）；(L2b)契约快照=复用已有 `_tikhub_openapi_snapshot.json`+`scripts_check_tikhub_schema.py` 手动 diff；(L3a)状态卡片+日志埋点=既有设计落地；(L3b)弹性降级=成本感知转备（①）。**明确不做**：正式契约测试（阶段二）、定期快照任务、独立监控平台（v1.71 已否）。**③红狐 T+1→方案 A+空确认标记+total=0 三态区分（2026-10-28 拍板，官方依据+实测）**：**官方口径**：红狐官方 skill 文档（OOMOL RedFoxHub）明示所有 curated/broad 数据库接口 "Data is updated on a T+1 schedule, not in real time"——含 `list_wechat_channel_user_works` / `search_wechat_channel_users` / `search_wechat_channel_works`（搜索同 T+1）；TikHub 官方实时无 T+1（tikhub.io/zh/wechat-api）。**决策=方案 A**：新作者（列表 total=0）自动补一次 TikHub 实时列表 ¥0.072；老作者当天视频贴链接路径兜底（红狐 workByUrl 未标 T+1=实时）；搜索接受 T+1 不补（成本面大）；UI 阶段一不加时效标注。**空确认标记**：补拉结果为空→本地存 author+空确认时间戳，**7 天免补**（防真空账号每次点开白补，每空账号最多浪费一次 ¥0.072）。**total=0 三态区分实测（2026-10-28，scripts_probe_total0_distinguish*.py，成本≈¥0.5）**：红狐响应**无区分字段**（不存在作者也 code 2000+空 list+"成功"同形）；**TikHub 有 `empty_reason` 字段**——`bad_input`=作者不存在/无效（官方 message 明示"无效参数的请求被微信处理后仍会计费"）、items 空且无 empty_reason=真空账号 → 补拉三态处理（items 非空=赚 / bad_input=标"无效作者" / 空=标"已确认空"，均 7 天免补）。**执行注意**：①TikHub 官方"客户端请求超时设约 30 秒，超时过小可能在未返回响应的情况下仍计费"→ 印证 v1.45 读超时 90s 决策；②export_id 官方标注"很快过期，请搭配 object_nonce_id 提高命中率"→ 兜底入参 **object_id 优先**、export_id 配 object_nonce_id。**回填**：§6 缺口#6 熔断切换表述修正（供应商级提前阶段一）；§6.1 贴链接段落时效注意补"空确认标记"引用 | v1.83 |
| **实施前风险逐项拍板统一落档（⑤环境固化 ⑥打包两件套+分支策略 ⑦前端集成回归 ⑧nickname重名 ⑨SQLite并发 ⑩大整数核查 ⑪自动更新替换权限）** | **⑤开发环境未固化→uv 接管（2026-10-29 执行完成）**：项目原无项目级依赖管理（裸 requirements.txt + 指向已删 F 盘解释器的坏 .venv）→ `uv init --bare --name haoxia` 生成 pyproject.toml（requires-python≥3.13，15 项依赖=requirements.txt 全量迁移无增删——AST 扫描 core/gui/build+38 个 scripts 实锤：工具脚本零第三方、tikhub vendored 不进运行时）+ `.python-version`(3.13) + `uv sync` 重建 .venv（49 包，uv.lock 锁死 59 传递树，阿里云镜像）+ `scripts_scan_deps.py`（可复用盘点工具）；**统一入口 `uv run python`，系统 python 退役**；验证=核心导入 15/15 + 前端门禁 PASS + TTL 探测 206。**⑥打包两件套+分支策略（2026-10-29 拍板）**：**分支策略**——master=旧项目「微信号视频短剧下载器」存档冻结（依赖微信客户端+外部开源二进制 wx_video_download/res_download）；新分支 **`feature/haoxia`=号匣 V1 全新产品**（**非旧项目 V2，全新独立产品**：纯红狐/TikHub API、零外部二进制、零微信客户端依赖）。**新架构无旧链路**：res_download(8899 嗅探+系统代理)/wx_video_download(2022/2023)/gopeed.db/global.js **全不进新分支**——不存在"下线"动作（新分支不引入）；本地仅「壳+FastAPI」单端口，数据纯 API HTTPS。**打包清单**：PyInstaller 打 Python 后端+static+`.env.example` 模板首启生成（用户配置不进产物，更新不覆盖；.env 永不进包 v1.46 延续）+WebView2 引导；VERSION 单一事实源沿用但号匣从 **1.0.0** 独立起步；产物名"号匣"；零外部二进制。**打包验收**=解压直启冒烟+真实旅程（搜索→下载→解密→出片）+断点续传+失败转备+门禁。**⑦前端集成回归（2026-10-29 拍板）**：三层——L0 语法+安全门禁已有（scripts_check_frontend.py）；**L1 功能回归必做**（前端对接完成后 10 项手测：模块切换/搜索/作者列表/详情/下载/合集/评论/互动数/作者资料/日志面板，逐项验证「渲染→点击→委托→响应」，含 v1.81 事件委托迁移覆盖边界检查）；L2 Playwright 自动化冒烟**阶段二再补**。**⑧nickname 重名配对（2026-10-29 拍板）**：微信视频号昵称可重名（唯一=sph ID/TikHub username），红狐按 nickname 精准匹配可能拉错作者→**锚定唯一 ID**（链接解析/详情返回 channel_id/username 为权威锚，拉回列表与锚比对，不一致告警"重名疑似"）+ **配对缓存**（nickname↔channel_id/username，冲突标记）+ **重名兜底 TikHub username**（¥0.072 贵但准）；**实施实测点**：红狐 queryWorkList 响应是否含唯一 ID 字段（v1.78 只测入参未测重名响应）。**⑨SQLite 并发写锁（低危防御，2026-10-29 拍板）**：SQLite=**客户端本地库**（服务器端存储无关）→ 影响面=单机单进程多线程（下载+SSE+缓存+监控），触发频率低→新架构建库默认 **WAL + busy_timeout(5000) + check_same_thread=False 线程安全连接 + 统一 DAO 写入口**（v1 已有 task/video/author_dao），零额外设计。**⑩大整数角落遗漏（落地核查项，2026-10-29 拍板）**：方案 v1.42 已定（全链路 string + json-bigint 兜底），⑩=**实施核查**——export_id/decode_key/互动数三类 64 位大整数全链路 grep 排查（后端 int 直发/前端 Number( 隐转/SQLite INTEGER 字段定义），列清单逐个确认；存储 TEXT + API string（"截断"实为精度舍入：JS Number 53 位有效位就近舍入）。**⑪自动更新替换 exe 权限（2026-10-29 拍板）**：Windows 运行中 exe 文件锁+安装目录写权限→行业标准 A（**退出后替换**）+落地 **A3（阶段一：下载→提示重启→重启时替换）+ 装用户目录保写权限**；阶段二升级 A2（launcher 引导程序自动替换）。**回填**：§2.6 自动更新段补替换机制（A3）；六项均进 PingCode 阶段一实施工单 | v1.84 |

### 待拍板（阻塞或影响实施范围）

| # | 项 | 现状 | 影响 | 卡点 |
|---|---|---|---|---|
| 1 | **TikHub 充值 / Key 状态** | **已实测解决（v1.13）**：calculate_price 与 fetch_video_detail 双 200 计费成功 → key 有效、账户已开户且有付费余额；微信系端点 $0.01 固定、allow_discount=false（无阶梯折扣）、allow_free_credit=false（不吃赠额）；契约"未开户/未充值/key 未建"三条全部过时 | 决定联调节奏 | ✅ 已解决 |
| 2 | 监控频率 | **已拍板（v1.22）打开即同步 + 标星低频兜底**：①打开下载器主页 = 0 成本，读本地库显示快照（不刷任何作者）；②点开作者 = 惰性刷新（L2 判断，过期才 $0.01 单作者，不过期 0 成本）；③标星监控作者 = 每天 2 次兜底（默认少，≈$0.6/月/作者）；④可选增强：主页计数旁标注"X 小时前更新"（快照语义可观测性）。原 30 分钟轮询 ≈$144/月 否决；"打开就全刷所有作者"否决（10 作者=$0.1/次） | 成本可控（惰性+低频+收敛监控对象） | ✅ 已拍板（进本版） |
| 3 | 下载引擎 | **已拍板（v1.21）自研直链下载模块**：弃用 `wx_video_download`（接口文档实锤 `channels.available` 依赖证书安装=微信生态绑定，微信升级即失效，且为黑盒外部依赖）；弃用 TikHub 官方下载器（README 实锤仅支持 TikTok/抖音、**无微信视频号**，且 **GPL v3** 传染性协议冲突商业化）；**最终方案：后端拿 full_url 直链直接 HTTP 下载**（实测 CDN 206 可下，带浏览器 UA），复用现有 task 模块（任务表/进度/状态不变）+ L5 文件校验（file_validator），全链路 0 微信依赖、0 GPL 风险 | 下载链路改造（新增直链下载逻辑，弃用 2022 端口） | ✅ 已拍板（进本版） |
| 4 | 增强端点 | **合集已进本版（v1.54 拍板，TikHub 专属）；合集列表缓存搭 L2 顺风车（v1.55 拍板：随 author_list_snapshot 同取同存同过期，TTL=120min，边际成本 0）**；**评论 + 主页资料已进本版（v1.60 拍板，用户"接呗全接上"：懒触发 + TTL 7 天，风控已解除实测 200）**；号内搜索（fetch_search_channel_videos）仍后置 P3 | 范围 | ✅ 已拍板（除号内搜索） |
| 5 | **前端旅程对齐 TikHub 端点粒度（非聚合接口）** | **已拍板（v1.19）三路径并存**：①「我的作者」主页（已存作者，读本地库 0 成本秒开，老数据兼容）→ 点击直达 + L2 自动拉列表；②搜索关键词 → 点开自动入库 + 自动拉列表（L4 缓存）；③导入链接为**可选辅助入口**（非主路径，走 L1 短号映射）。被省的=同步配置弹窗/4 步进度条/手动同步按钮（数据后台自动刷新）。后端仅薄适配（不做聚合接口）：~~fetch_channel_id_to_username~~（v1.79/80 已 400 移出）、fetch_user_videos、fetch_live_history、fetch_video_detail 一一暴露为内部路由 | 成本：首次全量 ≈ $0.02–0.03/作者、过期增量 $0.01/次（L2 已缓存）；搜索同词 24h 内 0 成本 | ✅ 已拍板（进本版） |

## Further Notes

- **待核实（部分已解决）**：知识库《TikHub 供应商契约》与台账写"评估中 / 未充值 / key 未建"，但《真人掼蛋视频素材源清单》文档写"已充值 $10 已实测（fetch_live_history 返回 full_url + decode_key）"。**已核验闭环（v1.13）**：密钥库存在 `TIKHUB_KEY`（len=60）→ key 已建；calculate_price + fetch_video_detail 双 200 且"将被计费" → **key 有效、已开户、有付费余额**（契约"未开户/未充值/key 未建"三条全过时，v1.75 回填：原"剩余：充值金额与实测状态需后台或实调确认"已由双 200 计费实测闭环，不再剩余）。
- **降级路径**：TikHub 不可用时 → 提示并走**红狐备用链路**（双供应商互备，v1.39）；微信通道已移除（v0.8），不存在"切回微信"。
- **合规定位（v1.75 修正，取代旧"仅限个人调研"提示）**：**红狐=正规付费数据 API（有 ToS/商业授权）→ 对外商业化主数据源走红狐，合规**；**TikHub 抓取违反平台 ToS（灰色）→ 仅内部备用链路（阶段一自用可用；阶段二对外主链路=红狐，TikHub 不对外承诺）**；文档与 UI 明示"抓取类数据仅限个人调研/内部分析"。
- **关联文档**：知识库 `content/common/providers/tikhub-契约.md`（端点清单/计费/风险真相源）、本项目 `weixin_exe/接口文档.md`（现状接口）。
- **短剧排期**：短剧嗅探（res_download 链路）另行排期合入；本版本交付物为单「号匣」（微信视频号下载器），不再保留二合一形态。
- **TikHub 能力核实（2026-10-27，契约 §1）**：TikHub 为**纯 API 数据服务商**（结构化 JSON 数据端点 + MCP 990+ 工具 + Chrome 扩展 + 控制台 user.tikhub.io），**无现成「搜索→浏览→下载」完整前端**。前端旅程不能整体外包给 TikHub；但 `fetch_video_detail` 返回 media+decode_key（契约已核实）→ 支持「链接直下」，前端可简化为「贴链接→下载」默认旅程，复杂作者管理降级为可选页。

## 实测闭环与缓存设计更新（v1.13，2026-10-27）

> 本轮完成：① 一次性最小实测（$0.02 + 404 免费）把字段映射 7 项待实测全部收口；② 挖出 `raw=false` 推荐模式与 `urlValidDuration` 字段，升级 L2 缓存设计；③ 建 TTL 观察实验（临时测试点 + 每日任务）。

### 1. 实测结果（脚本：`scripts_probe_share_url_full.py`、`scripts_probe_search_live.py`；输出留底：`_probe_full_out.txt`、`_probe_search_live_out.txt`）

| 项 | 实测结果 | 结论/处置 |
|---|---|---|
| 403 真相 | urllib 默认 UA 被 Cloudflare 拦截（错误码 1010）；带浏览器 UA → 200 | **P0 工程纪律：所有 TikHub 调用必须带浏览器 User-Agent** |
| Key 状态 | calculate_price + fetch_video_detail 双 200 且"将被计费" | key 有效、已开户、**有付费余额**；契约三条过时 |
| 单价 | fetch_video_detail base_price=$0.01、allow_discount=false、allow_free_credit=false | 微信系端点固定 $0.01/次、无阶梯折扣、不吃赠额 → 成本模型简化 |
| expire_time | 详情 data 无任何 expire/valid/ttl 键 | 详情无过期字段；列表有 `urlValidDuration=172800`（48h） |
| create_time | 详情=秒级 Unix 时间戳（1793061582） | 适配层转 ISO；列表（raw=false）为 create_time snake_case |
| duration | 详情 media.duration=310（**秒**）；列表 media.spec[].durationMs=12393201（**毫秒**） | **两处单位不同，适配层必须归一** |
| file_size | 详情 media.file_size=119621849（字节）有 | 直接映射；列表无（用 duplicateFileSize 或详情） |
| media_type | 详情 media_type=4（视频语义一致） | 过滤逻辑可保留 |
| 互动 5 项 | 详情 read/like/fav/forward/comment 全带（873/1165/641/11）；列表 raw=true 为驼峰 readCount 等（实测=0） | 官方命名收口；raw=false 转 snake_case |
| 搜索字段路径 | **文档明确（未再实测）**：`fetch_search_channel_videos`（号内搜索，真实端点）raw=false 返回 items[].type/doc_id/title/desc/thumb_url/username/nickname；**命中项不含 media** | 搜索→详情链路；搜索缓存只省搜索调用；注意我们曾拼错路径 `/wechat_channels/v2/fetch_search_videos` 404（不扣费） |
| live_history read_count | 有（raw=true readCount 实测=0） | 收口 |
| 大整数 | id=15041290733490477116 等按字符串返回 | json-bigint 纪律确认 |

### 2. 重大发现：`raw=false` 统一模式（对 L2 缓存是升级）

- 列表类端点（fetch_user_videos / fetch_live_history / fetch_collection_videos）**默认 raw=true**（微信原生驼峰结构，url 为半成品、fullUrl 空、decodeKey 在 objectDesc.media[0]）；
- **raw=false 是 TikHub 官方标注的"推荐做媒体下载"模式**：返回 snake_case，列表项带 `media.url / url_token / full_url（已拼好可直接下载）/ decode_key（同响应配对）`；
- **工程决策：所有列表/搜索调用统一 raw=false** → 适配层免驼峰映射；
- **L2 缓存升级**：列表缓存命中 = 浏览 + **下载双省**（下载直链在列表响应里，无需再调详情）；decode_key 仍按"与同响应 full_url 配对"纪律缓存；
- **L3 详情缓存职责收窄**：仅服务「搜索命中项→详情」链路 + 过期刷新兜底。

### 3. 新锚点：`urlValidDuration=172800`（48 小时）

- 列表项自带该字段（微信原生），疑似播放/分享 URL 官方有效期；
- 与用户自测"下载直链 10 天+"的关系待观察实验验证（可能不同链路不同时效）；
- **对 L2 的约束参考**：列表数据官方有效期 48h → L2 TTL 上限参考 48h，真实锚以观察实验为准（不高于官方值）。

### 4. TTL 观察实验（临时测试点 + 每日任务）

- 链接来源：用户提供分享链接 `https://weixin.qq.com/sph/As68wzqwSd` 实测返回的 media.full_url（wxapp.tc.qq.com CDN 直链）；
- 脚本 `scripts_observe_ttl.py`：HTTP Range 探测（零成本），幂等（当天已记录跳过），结果追加 `_ttl_observation.log`（格式：日期时间 | HTTP 状态 | VALID-仍有效 / EXPIRED-已过期）；
- 基线：2026-10-27 23:19 HTTP 206 仍有效；
- **每日定时任务**（本地，每天 18:30，下次 2026-10-28 18:30）：运行脚本直到发现过期 → 报告首个过期日期 → 实验完成；
- 验收：得到实测 TTL 天数，回填本表与 L2/L3 设计。

### 5. 端点路径清单（含本次修正）

- 号内搜索：`POST /api/v1/wechat_channels/v2/fetch_search_channel_videos`（username+keyword+cursor+raw）⚠️ 非 `/wechat_channels/v2/fetch_search_videos`（该路径不存在）；
- 全局搜索：`/api/v1/wechat_search/v2/fetch_search`、`/wechat_search/v2/fetch_search_videos`（本版不涉及）；
- 其余 26 个 wechat 路径已在 v0.2 映射表收敛；公众号（wechat_mp）与本版无关。
