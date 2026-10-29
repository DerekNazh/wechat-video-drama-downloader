# 翻写规格：wx_channels_download → 号匣/legacy 自研（微信视频号域）

> 状态：v0.4 二次缺漏审查 · 2026-10-29（v0.3 后补查 download_task 依赖链，发现 adapter/wxchannels 业务适配层为真实缺漏）
> 目的：把 `research/wx_channels_download`（MIT+Commons Clause，禁 Sell）微信视频号核心逻辑**按块翻写为自有代码**（参考逻辑、不复制源码），供 legacy 分支自研版使用。
> 合规铁律：只读参考**逻辑/算法/协议**，禁止整文件复制进主代码；翻写代码为全新实现，不受 Commons Clause 约束。
> 源码位置：`D:\setup_temp\剪辑合成拆散\新_二合一总下载器\research\wx_channels_download\`

---

## 〇、全量源码盘点（微信视频号域，缺漏审查完成）

**审查方法**：wxchannels 包全部 .go + internal/services + internal/api + internal/interceptor + pkg/{cookies,cache} + frontend/inject 逐目录列全，对照功能域归类。**遗漏修正**：v0.1/0.2 漏了 ①yuanbao.go（独立链接解析器）②证书模块 ③cookies/cache 支撑包 ④下载任务 WS 进度推送 ⑤scraper_job 批量抓取 ⑥content/data_query 内容查询服务。**v0.3 后二次审查**：补查 download_task 依赖链（adapter/events/hermes/database-model），发现 **internal/adapter/wxchannels 业务适配层（postprocess.go 98.3KB 为全仓最大单文件之一）** 未纳入——这是 B5 能力的对外门面，必须补。

### 模块树（翻写/参考/弃用 三态）

```
wx_channels_download（微信视频号域）
├── 【翻写】解密链路
│   ├── B1 解密核心 ISAAC-64          decrypt.go        171行   L0 无依赖
│   ├── B2 流式解密 Reader            reader.go          74行   L1 依赖B1
│   └── B3 解密服务                   decryptor.go      378行   L2 依赖B1+B2
├── 【翻写】数据与模型
│   └── B4 数据结构/常量              types.go+util.go  30.7KB  L0 无依赖
├── 【翻写】客户端（直连协议）
│   └── B5 API 客户端                 client.go         15.1KB  L3 依赖B4+cookies
├── 【翻写】业务适配层（v0.4 新增）
│   └── B10 业务适配门面               adapter/wxchannels/* (adapter+postprocess 110KB+)  L4 依赖B3+B5
├── 【翻写】链接解析
│   └── B8 元宝链接解析器             yuanbao.go         独立  L3
├── 【参考】协议与逆向
│   ├── B6 JS 逆向解析器              interceptor.go    24.6KB  独立  (只产接口清单)
│   └── B9 微信侧 Cookie 支撑         pkg/cookies/*      14.9KB  支撑B5
├── 【对齐】业务层
│   └── B7 下载任务管理                download_task*.go + handler 176KB+  对齐号匣 YZPQ-307
├── 【弃用】注入/代理（号匣不实现）
│   ├── (弃) internal/interceptor/*    Sunny代理 MITM    34KB
│   ├── (弃) pkg/certificate/*         证书生成/安装       22KB
│   ├── (弃) frontend/inject/*         页面注入 JS        94KB
│   └── (弃) internal/workers/*        Cloudflare worker  部署层
├── 【评估】内容与任务服务
│   ├── (评) content.go + data_query.go  内容查询/展示    81KB  与号匣DB重叠，评估复用字段
│   ├── (评) scraper_job.go             批量抓取任务      33KB  号匣"批量添加作者"可比对
│   ├── (评) cache.go + provider.go     缓存             8.4KB  号匣缓存设计已定，仅对照
│   ├── (评) events.go + hermes/*        事件总线/下载引擎  通用支撑层，号匣已有等价物（事件系统/任务引擎），不翻写
│   └── (评) database/model/*             DB 模型          号匣已有自研 DB 表，仅对照字段
```

---

## 一、块清单（完整，按依赖序）

| 序 | 层 | 块 | 名称 | 上游源码 | 依赖 | 优先级 |
|---|---|---|---|---|---|---|
| 1 | L0 | **B1** | 解密核心 ISAAC-64 | decrypt.go（171行） | 无 | P0 |
| 2 | L0 | **B4** | 数据结构/常量 | types.go+util.go | 无 | P1 |
| 3 | L1 | **B2** | 流式解密 Reader | reader.go（74行） | B1 | P0 |
| 4 | L2 | **B3** | 解密服务 | decryptor.go（378行） | B1+B2 | P0 |
| 5 | L3 | **B5** | API 客户端（HTTP+WS） | client.go（15.1KB） | B4+B9 | P1 |
| 6 | L3 | **B8** | 元宝链接解析器 | yuanbao.go | 独立 | P1 |
| 7 | L3 | **B9** | 微信 Cookie 支撑 | pkg/cookies/* | 独立 | P1 |
| 8 | L3 | **B6** | JS 逆向接口清单 | interceptor.go | 独立 | P2 |
| 9 | L4 | **B10** | 业务适配门面 | adapter/wxchannels/*（110KB+） | B3+B5 | P1 |
| 10 | L4 | **B7** | 下载任务状态机 | download_task*.go+handler | B3 | P2 |

## 二、各块要点

### B1 解密核心（ISAAC-64）——L0 首块
- 算法：golden=0x9e3779b97f4a7c13，256 状态，4+2 轮 mix，8 字节大端 keystream，前 encLen 字节 XOR。
- 依赖仅 encoding/binary。号匣已有 Python 版（v1.70 实测）→ 逐行对照验证等价。
- 产出 `core/decrypt/isaac64.py`；验收：同 key 前 8 keystream 一致 + 实测文件可播。

### B4 数据结构——L0（与 B1 并行）
- types.go 全量模型（feed/作者/直播/评论 30.7KB）+ util.go。
- 产出 `core/models/wxchannels.py`（Pydantic，对齐号匣 DB 表）。

### B2 流式解密 Reader——L1
- NewDecryptReader(reader,key,offset,limit)：断点偏移（跳过 offset/8 块 + offset%8 续解）。
- 产出 `core/decrypt/decrypt_reader.py`；验收：offset=0 vs offset=1024 拼接一致。

### B3 解密服务——L2
- DecryptOnly（Range 透传流）、ConvertWithDecrypt（ffmpeg 转 mp3）、DecryptFile、SimpleProxy。
- 产出 `core/decrypt/decrypt_service.py`；验收：Range 请求返回已解密流。

### B5 API 客户端——L3
- **双通道**：share_url 解析 + **WebSocket 直连**（ServeWebsocket/RequestFrontend 走前端 WS 桥）。
- **方法清单（client.go 实锤）**：SearchChannelsContact / FetchChannelsFeedListOfContact / FetchChannelsLiveReplayList / FetchLiveProfile / FetchChannelsInteractionedFeedList / FetchChannelsFollowList / FetchChannelsPlayHistory / FetchFeedPage / CheckSphCookie。
- **关键依赖**：yuanbao.tencent.com cookie（身份凭据）。
- 产出 `core/api/wxchannels_client.py`；验收：拉作者主页/作品列表字段与红狐/TikHub 对齐。

### B8 元宝链接解析器——L3（v0.3 新增）
- POST `yuanbao.tencent.com/api/weixin/get_parse_result`（yuanbao.go:108 实锤）。
- 作用：share_url → 视频详情直链的**另一条解析通道**（对应号匣 L1 链接解析）。
- 产出 `core/api/yuanbao_parser.py`；验收：share_url 解析出直链+key。

### B9 微信 Cookie 支撑——L3（v0.3 新增）
- pkg/cookies：HeaderForDomain（读指定域名 cookie）/ 持久化（persistent.go）。
- 号匣已有 server-secrets 管密钥 → 翻写为 `core/security/cookie_store.py`（结构化存取+持久化）。
- 验收：能读/写 .tencent.com 域 cookie。

### B6 JS 逆向接口清单——L3（仅参考，不实现注入）
- interceptor.go 正则提取 20+ 接口签名（finderGetCommentList/finderUserPage/finderPcFlow/finderGetLiveInfo/finderPCSearch 等）。
- 产出 `core/protocol/wxchannels_api_map.py`（接口清单+参数+响应形状）。
- 验收：接口清单与红狐/TikHub 字段比对，找出未用字段。

### B10 业务适配门面——L4（v0.4 新增）
- `internal/adapter/wxchannels/adapter.go`（12.8KB）+ **postprocess.go（98.3KB）**+ model.go（51.6KB）+ routes.go（12.8KB）。
- **作用**：B5 客户端方法（SearchChannelsContact/FetchChannelsFeedListOfContact/FetchChannelsLiveReplayList/FetchChannelsFeedProfile/FetchChannelsFeedCommentList/FetchChannelsFeedShareUrl）的业务封装 + **响应后处理（postprocess）**——把微信原始响应清洗/裁剪/重组成对外统一模型，是全仓最大单文件之一。
- **产出**：`core/api/wxchannels_service.py`（业务门面：统一方法 + 响应后处理管道）。
- **验收**：与红狐/TikHub 同场景输出字段可比对一致；含全部 6 个对外方法。

### B7 下载任务状态机——L4
- download_task.go（115.9KB）+ handler_download_task.go（60.4KB）+ **handler_download_task_ws.go（26.4KB，进度推送）**+ download_task_delete/view.go。
- **不整块翻**：号匣已有 YZPQ-307 状态机设计 → 差异比对补缺口（含 WS 进度推送是否纳入号匣）。
- 产出：差异报告 + YZPQ-307 补充项。

## 三、弃用边界（明确不做，防缺漏假象）

| 上游模块 | 理由 |
|---|---|
| internal/interceptor（Sunny MITM 代理） | 号匣纯 API 零注入零代理 |
| pkg/certificate（根证书生成/安装） | 无 MITM 即无证书需求 |
| frontend/inject（页面注入 JS 94KB） | 号匣自研 WebView2 前端 |
| internal/workers（Cloudflare worker） | 部署层，号匣本地应用不需要 |

## 四、执行纪律

- 严格依赖序：B1→B2→B3 硬链；B4/B9 可并行；B5/B8 等 B4+B9；B6 独立；B7 等 B3。
- 每块独立验收；上层验收包含下层已过。
- 翻写代码禁止上游版权标识/原注释/变量名照抄（全新命名）。
- 上游源码仅在 research/ 参考，不入主代码路径。
- 新增许可证依赖（ffmpeg）登记《开源依赖合规约束.md》。

## 五、待办（按依赖序）

- [ ] **B1** 解密核心对照验证（L0，首块）
- [ ] **B4** 数据结构（与 B1 并行）
- [ ] **B9** Cookie 支撑（并行）
- [ ] **B2** 流式 Reader（依赖 B1）
- [ ] **B3** 解密服务（依赖 B1+B2）
- [ ] **B5** API 客户端（依赖 B4+B9）
- [ ] **B8** 元宝解析器（独立）
- [ ] **B6** JS 逆向接口清单（独立）
- [ ] **B10** 业务适配门面（依赖 B3+B5）
- [ ] **B7** 状态机差异比对（依赖 B3）
- [ ] 评估项：content/data_query、scraper_job、cache、events/hermes、database-model 对照（不阻塞，深入时再看）
