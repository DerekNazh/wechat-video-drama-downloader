# 翻写规格：wx_channels_download → 号匣/legacy 自研（微信视频号域）

> 状态：v0.2 依赖重排 · 2026-10-29（v0.1 拆块后按源码 import 依赖审查重排）
> 目的：把 `research/wx_channels_download`（MIT+Commons Clause，禁 Sell）微信视频号核心逻辑**按块翻写为自有代码**（参考逻辑、不复制源码），供 legacy 分支自研版使用。
> 合规铁律：只读参考**逻辑/算法/协议**，禁止整文件复制进主代码；翻写代码为全新实现，不受 Commons Clause 约束。
> 源码位置：`D:\setup_temp\剪辑合成拆散\新_二合一总下载器\research\wx_channels_download\`

## 〇、依赖分层总图（底层→高层，源码 import 实锤）

```
L0 无依赖（纯算法/纯数据）
   B1 解密核心 ISAAC-64          ← decrypt.go（零依赖，仅 encoding/binary）
   B4 数据结构/常量              ← types.go / util.go（零依赖）
        │
L1 单依赖（依赖 L0）
   B2 流式解密 Reader            ← reader.go（依赖 B1：CreateISAacInst）
        │
L2 组装层（依赖 L0+L1）
   B3 解密服务（HTTP流/断点/转码） ← decryptor.go（依赖 B2：NewDecryptReader）
        │
L3 协议层（依赖 L4 才有意义）
   B5 API 客户端（WS/请求协议）    ← client.go（依赖 cookies/cache 包）
   B6 JS 逆向解析器（拦截器）      ← interceptor.go（依赖 frontend/正则规则）
        │
L4 业务层
   B7 下载任务管理（状态机）       ← download_task.go + handler（对齐号匣 YZPQ-307）
```

**依赖规则**：下层必须先翻写完成并验收，上层才能动。L0→L1→L2 是硬链（解密链路），L3/L4 与 L2 弱耦合（可并行）。

---

## 一、块清单（按依赖顺序重排）

| 序 | 层 | 块 | 名称 | 上游源码 | 依赖 | 优先级 |
|---|---|---|---|---|---|---|
| 1 | L0 | **B1** | 解密核心 ISAAC-64 | decrypt.go（171行） | 无 | P0 |
| 2 | L0 | **B4** | 数据结构/常量 | types.go（30.7KB）+ util.go | 无 | P1 |
| 3 | L1 | **B2** | 流式解密 Reader | reader.go（74行） | B1 | P0 |
| 4 | L2 | **B3** | 解密服务（HTTP流/Range/转码） | decryptor.go（378行） | B1+B2 | P0 |
| 5 | L3 | **B5** | API 客户端（WS 协议/请求） | client.go（15.1KB） | B4+cookies/cache | P1 |
| 6 | L3 | **B6** | JS 逆向解析器（接口发现） | interceptor.go（24.6KB） | 独立 | P2 |
| 7 | L4 | **B7** | 下载任务状态机 | download_task.go（115.9KB）+ handler（60.4KB） | B3 | P2 |

---

## 二、B1 解密核心（ISAAC-64）——首块，L0 底层

**上游逻辑要点**（decrypt.go 逐行读毕）：
- ISAAC-64 keystream：`CreateISAacInst(encKey)` → `rand64Init`（golden=0x9e3779b97f4a7c13，256 状态，4+2 轮 mix）→ `isAAC64`（AA/BB/CC 演进）→ `ISAacRandom()` 8 字节大端。
- `DecryptData(data, encLen, key)`：从偏移 0 起每 8 字节 XOR 一个 keystream 块；**只有前 encLen 字节加密**。
- 依赖：仅 `encoding/binary`——**纯算法，无任何包依赖，最底层**。

**与号匣已有实现对照**：master 已有 Python 内嵌解密（ISAAC-64 + 前 128KB XOR，v1.70 实测通过）→ B1 = 逐行对照验证 keystream 等价。

**验收**：①`core/decrypt/isaac64.py` 纯 Python 无外部依赖；②同一 encKey 前 8 个 keystream 值与 Go 一致；③实测视频文件解密可播放。

## 三、B2 流式解密 Reader——L1

**依赖**：B1（`NewDecryptReader` 内部调 `CreateISAacInst`）。
**上游逻辑要点**（reader.go 读毕）：`NewDecryptReader(reader,key,offset,limit)` 支持断点偏移——offset>0 预跳过 offset/8 完整块，从 offset%8 续解；逐字节 XOR，`consumed` 限解密区。
**产出**：`core/decrypt/decrypt_reader.py`（流式 XOR，适配 httpx/requests 流）。
**验收**：offset=0 全量解 vs offset=1024 断点解 → 拼接一致。

## 四、B3 解密服务——L2

**依赖**：B1+B2。
**上游逻辑要点**（decryptor.go 读毕）：`DecryptOnly`=代理请求→解析 Content-Range→流式透传；`ConvertWithDecrypt`=ffmpeg 转 mp3（`-vn -acodec libmp3lame -ab 192k`）；`DecryptFile`=本地落地；支持 HEAD/Range/状态码透传。
**产出**：`core/decrypt/decrypt_service.py`（FastAPI 中间层或纯函数管道；mp3 转码对接 ffmpeg CLI）。
**验收**：本地起服务，Range 请求返回已解密字节流，断点正确。

## 五、B4 数据结构——L0（与 B1 并行）

**依赖**：无。
**上游**：types.go 定义视频号全量模型（feed/作者/直播/评论等 30.7KB）+ util.go。
**产出**：`core/models/wxchannels.py`（Pydantic 模型，对齐号匣 DB 表）。
**验收**：字段名/类型/嵌套结构与上游一致；能被 B5 使用。

## 六、B5 API 客户端——L3

**依赖**：B4 + 上游 `pkg/cookies`/`pkg/cache`（翻写为自有 cookie 读取+缓存）。
**上游逻辑要点**（client.go 读毕）：
- 双模式：`fetch_profile_with_share_url`（share_url 解析）+ `fetch_profile_with_channels_client`（**WebSocket 客户端协议**——微信视频号页面与后端走 WS，client.go 封装了 WS 请求/响应映射）；
- **关键依赖：yuanbao.tencent.com cookie**（client.go:119 实锤）——这是微信侧的身份凭据；
- `FetchFeedPage` / `CheckSphCookie` / `resolve_sph_cookie`。
**产出**：`core/api/wxchannels_client.py`（HTTP+WS 双通道）。
**验收**：能拉作者主页/作品列表（与红狐/TikHub 同字段对比）。

## 七、B6 JS 逆向解析器——L3（仅协议参考）

**依赖**：独立（正则解析，不依赖其他块）。
**上游逻辑要点**（interceptor.go 前 75 行读毕）：**正则逆向微信前端 JS**，从源码提取接口签名——`finderGetCommentList`/`finderUserPage`/`finderPcFlow`/`finderGetLiveInfo`/`finderPCSearch` 等 20+ 接口正则；这是"无文档接口发现"能力。
**注意**：号匣纯 API 架构**不实现注入**，但 B6 提取的**接口清单/请求形状**可校验红狐/TikHub 字段完整性（对应之前"接口字段没用上"讨论）。
**产出**：`core/protocol/wxchannels_api_map.py`（接口清单+参数+响应形状，纯文档/常量）。
**验收**：列出全部接口签名，与红狐/TikHub 现有字段比对，找出未用字段。

## 八、B7 下载任务状态机——L4

**依赖**：B3（解密）+ 号匣现有 YZPQ-307 设计。
**上游**：download_task.go（115.9KB，最大单文件）+ handler_download_task.go（60.4KB）。
**处理**：**不全翻**——号匣 master 已有任务状态机设计（YZPQ-307 票），B7 = 抽上游状态流转（新建/排队/下载中/暂停/完成/失败/删除+断点续传）与号匣设计**差异比对**，仅补缺口。
**产出**：状态机差异报告 + 号匣 YZPQ-307 补充项。
**验收**：号匣状态机覆盖上游全部状态迁移。

---

## 九、执行纪律

- **严格依赖序**：B1→B2→B3 硬链必须顺序完成；B4 与 B1 并行；B5/B6 等 B4；B7 等 B3。
- 每块独立验收（验收标准见上），**上层块验收包含下层块已过**。
- 翻写代码**禁止**上游版权标识/原注释/变量名照抄（全新命名）。
- 上游源码仅在 `research/` 参考，不入主代码路径。
- 新增许可证依赖（ffmpeg）登记《开源依赖合规约束.md》。

## 十、待办（按依赖序）

- [ ] **B1** 解密核心对照验证（首个执行块，L0）
- [ ] **B4** 数据结构（与 B1 并行）
- [ ] **B2** 流式 Reader（依赖 B1）
- [ ] **B3** 解密服务（依赖 B1+B2）
- [ ] **B5** API 客户端（依赖 B4）
- [ ] **B6** JS 逆向接口清单（独立）
- [ ] **B7** 状态机差异比对（依赖 B3，对齐号匣）
