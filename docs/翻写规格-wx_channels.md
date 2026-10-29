# 翻写规格：wx_channels_download → wechat-downloader 自研（微信视频号域）

> 状态：**v0.18 B1-B11 全部执行级 · 2026-10-29（v0.15 补 B11 浏览器注入桥；v0.16 投放方式改进程级代理；v0.17 定主方案=WebView2 单实例代理；v0.18 最小测试 PASS 落档——单实例 --proxy-server 实测可行 22 条请求全走代理/系统代理未动，微信代理独立性查证：上游依赖微信'使用系统代理'设置，本方案独立不受微信配置影响，理论 100% 确认）**
> **v0.19 全局语言/排期决策（2026-10-29 用户拍板）**：①全仓 Python 单语言——产品代码永远 Python，Go 只留 research/ 当参考源，禁止双栈（用户明确否决"全仓 Go"与"Go域+HTTP混合"：前者需重写几十万行现有 Python 产品=天价，后者永久双运行时/进程管理/双打包）；②短剧（res-downloader，Apache 2.0 可商用）**二期翻写**（理由：黑盒系统代理体验差，翻写=拔系统代理+纯 Python 集成；基座用 mitmproxy 比逐行翻 proxy.go 省力）——短剧源码已 clone 到 research/res-downloader/（core/ 2847 行 Go，23 文件，plugins 仅 default+qq.com）；③代理统一 WebView2 单实例（B11 已定），系统代理全部淘汰；④一期=微信视频号 B1-B11（替代 wx_video_download.exe），二期=短剧翻写（替代 res_download.exe）。
> 目的：把 `research/wx_channels_download`（MIT+Commons Clause，禁 Sell）微信视频号核心逻辑**按块翻写为自有代码**（参考逻辑、不复制源码），**落 wechat-downloader 分支**（活跃开发的商业化产品线，含 res_download.exe/wx_video_download.exe 依赖）——**目标：用 Python 自研实现替代 exe 依赖，达成可商业化自研版**。
> 合规铁律：只读参考**逻辑/算法/协议**，禁止整文件复制进主代码；翻写代码为全新实现，不受 Commons Clause 约束。
> 源码位置：`D:\setup_temp\剪辑合成拆散\新_二合一总下载器\research\wx_channels_download\`

---

## 〇.6、落点决策（2026-10-29 拍板）

**翻写产物落点 = `wechat-downloader` 分支**（当前工作区，不是 master 号匣）：

| 分支 | 角色 | 与翻写关系 |
|---|---|---|
| **wechat-downloader**（当前） | 活跃商业化产品线：二合一下载器（短剧嗅探 res_download.exe + 微信视频号 wx_video_download.exe + TikHub/红狐 API 链路 + 柠檬卡密商业化） | **翻写落地分支**——Python 自研替代 exe 依赖 |
| master | 号匣 haoxia（纯 API 零成本版，独立产品线） | 不承接本翻写；其 127.0.0.1:2022 Go 后端依赖是号匣自身架构项，另行处理 |

**为什么落 wechat-downloader**（用户拍板依据）：
1. "这个分支我们还要的，相当于另一个产品版本，后面要商业化"——活跃开发，非研究用；
2. 开源合规（MIT+Commons Clause 禁 Sell）→ 必须按逻辑自研 → 产物进这个分支；
3. 分支现有结构实锤：`core/`（Python）+ `res_download/`+`weixin_exe/`（exe 依赖）+ 30 个探测脚本 + 商业化文档——**翻写就是把 exe 的解密/下载能力替换为 core 内 Python 模块**。

**B1 生产化的具体目标（替代对象实锤）**：
- `core/api/app.py` 自动启动 `res_download.exe`（短剧嗅探）+ `wx_video_download.exe`（微信视频号下载）——翻写完成后**微信视频号域不再启动/依赖 wx_video_download.exe**，由 Python 自研下载+解密链路替代；res_download（Apache 2.0，可商用）按需保留。
- `core/api/routers/base_service.py` 管理 exe 启停——微信视频号相关部分移除。

---

## 〇.5、技术栈基线（2026-10-29 拍板：Python）

**选型结论**：翻写语言 = **Python**，全部 10 块统一。理由 = 约束推导（不是偏好）：
1. **嵌入目标**：翻写产物进号匣代码库（master = Python/FastAPI），语言不匹配无法落地；
2. **已有资产**：B1 解密已用 Python 实现且实测通过，换语言=推倒重来；
3. **性能**：解密热路径=128KB keystream+XOR，Python 毫秒级，瓶颈在网络/磁盘非 CPU；
4. **生态**：逆向/爬虫社区 Python 参考实现最厚（Evil0ctal/Hanson 均有 Python 版）；
5. **行业惯例**：翻写目标语言=落地产品语言，不跟随参考源（Go）。

**基线（对齐号匣 master pyproject.toml 实锤）**：

| 项 | 值 |
|---|---|
| 语言 | Python **3.13**（requires-python >=3.13） |
| 包管理 | **uv**（[tool.uv] 已配置，阿里云镜像） |
| HTTP | httpx 0.28 + requests 2.33 |
| WS 客户端 | websocket-client 1.9 |
| 数据模型 | pydantic 2.13 |
| 服务 | FastAPI 0.136 + uvicorn 0.44 |
| 前端容器 | pywebview 6.2（WebView2） |
| 打包 | pyinstaller 6.19 |

**语言差异落地要点（翻写时必须处理）**：
- Go uint64 自动回绕 → Python 需 `& 0xFFFFFFFFFFFFFFFF` 掩码（B1 已实现，`MASK` 常量）；
- decode_key 大整数 → Python int 无限精度无截断风险，接口层按字符串读入（对齐 master 大整数规范）；
- ffmpeg 转码 → subprocess 调用（B3 用）。

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
├── 【翻写】浏览器注入桥（v0.15 补——此前误弃用，B5 命根子）
│   └── B11 注入 JS + 投放方式        frontend/inject/* 94KB + static_asset.go  L3 依赖B5
├── 【参考】协议与逆向
│   ├── B6 JS 逆向解析器              interceptor.go    24.6KB  独立  (只产接口清单)
│   └── B9 微信侧 Cookie 支撑         pkg/cookies/*      14.9KB  支撑B5
├── 【对齐】业务层
│   └── B7 下载任务管理                download_task*.go + handler 176KB+  对齐号匣 YZPQ-307
├── 【弃用】代理/证书/UI（号匣不实现，投放方式另选）
│   ├── (弃) internal/interceptor/*    Sunny代理 MITM    34KB   (注入逻辑已在B6/B11翻写，仅弃MITM具体实现)
│   ├── (弃) pkg/certificate/*         证书生成/安装       22KB   (CDP注入无需证书)
│   ├── (弃) frontend/inject model.js+view.js 下载面板UI 119+80KB (号匣自研WebView2前端，注入JS本体B11翻写)
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
| 11 | L3 | **B11** | 浏览器注入桥（v0.15 补） | frontend/inject/*（94KB）+ static_asset.go | B5 | P1 |

## 二、各块要点

### B1 解密核心（ISAAC-64）——L0 首块
- 算法：golden=0x9e3779b97f4a7c13，256 状态，4+2 轮 mix，8 字节大端 keystream，前 encLen 字节 XOR。
- 依赖仅 encoding/binary。号匣已有 Python 版（scripts_probe_python_decrypt.py，v1.70 实测 ftyp+ffprobe 通过）→ **算法级已 100% 完成**。
- **生产级缺口（2026-10-29 实测发现）**：wechat-downloader 分支解密由 **wx_video_download.exe（Go 二进制）** 完成（`core/api/app.py` 自动启动），Python 侧无解密实现。**B1 翻写 = 把验证脚本升格为生产模块，微信视频号域下载链路本地解密，不再启动/依赖 wx_video_download.exe。**
- 产出（落 wechat-downloader 分支 core/）：
  - `core/decrypt/isaac64.py`（生产模块，由 scripts_probe_python_decrypt.py 升格）；
  - `core/decrypt/decrypt_reader.py` 起点（与 B2 衔接：本地解密读流的接口预留）。
- 验收标准（完整）：
  1. 算法等价：同 key 前 8 keystream 与 Go 一致 + 实测文件可播（已过）；
  2. 生产模块化：`core/decrypt/isaac64.py` 为正式模块（非 scripts 脚本），纯 Python 无外部依赖；
  3. 链路接入：微信视频号下载任务**不经 wx_video_download.exe**，由 Python 下载+解密+落盘，输出可播放文件；
  4. 单元测试：keystream 序列回归 + 样本文件解密断言。

### B4 数据结构/常量——L0（执行级，2026-10-29 落档）

**上游源码**：`pkg/scraper/wxchannels/types.go`（881 行，逐行读毕）+ `pkg/util/util.go`（67 行，逐行读毕）

**上游逻辑（逐函数/逐类型）**：
- **flexibleString（types.go:270-288）——核心机制**：微信接口把 `DecodeKey/ID/DocId/LiveId/AnchorStatusFlag` 等字段有时返回**数字**、有时返回**字符串**。Go 侧自定义 `UnmarshalJSON`：数字原样转字符串、字符串原样、null/空置空。涉及：`ChannelsMediaItem.DecodeKey`（types.go:96-109）、`ChannelsMusicInfo.DocId`（types.go:119-132）、`ChannelsObject.ID`（types.go:255-268）、`ChannelsLiveInfo.AnchorStatusFlag`（types.go:172-185）、`ChannelsFollowLiveInfo.AnchorStatusFlag`（types.go:648-661）、`JoinLiveInfo.LiveId`（types.go:753-766）。
  - **这正是"大整数角落遗漏"的官方解法**：ID 是 uint64，超出 JS/JSON 安全整数，必须按字符串处理，**翻写时 ID/DecodeKey 一律用 str 类型**（Pydantic 加 BeforeValidator 兼容 int/str）。
- **Base64↔uint64（util.go:15-67）**：`EncodeUint64ToBase64` / `DecodeBase64ToUint64String`——分享链接里的 `oid/nid` 是 **base64url 无填充编码的 8 字节大端 uint64**，转回十进制字符串（util.go:31-52：补 padding → Std 解码 → 左补 0 到 8 字节 → BigEndian → 十进制）。
- **ParseFeedURL（types.go:781-808）**：解析 `channels.weixin.qq.com/web/pages/feed` 链接，取 `oid/nid/eid`；oid/nid 若可 base64 解码则转十进制字符串（`utilpkg.DecodeBase64ToUint64String`）。非该域名/路径 → `ErrUnsupportedURL`。
- **ParseSphShareURL（types.go:860-881）**：解析两种形式——`weixin.qq.com/sph/{id}` 或 `channels.weixin.qq.com/finder-preview/pages/sph?id=`，取 id；其余 → ErrUnsupportedURL。
- **模型家族（按用途分组）**：
  - 通用包装：`ChannelsRequestResp[T]`（errCode/errMsg/data）、`BaseResponse`（Ret/ErrMsg）。
  - 媒体：`ChannelsMediaItem`（URL/ThumbUrl/MediaType/VideoPlayLen/Width/Height/FileSize/Spec[]/CoverUrl/**DecodeKey**/URLToken——**下载核心**）、`ChannelsMediaSpec`（**上游只用了 FileFormat/Width/Height/DurationMs，其余字段注释掉**）、`ChannelsMusicInfo`、`ChannelsCodecInfo`、`ChannelsScalingInfo`、`ChannelsMediaCdnInfo`。
  - 视频对象：`ChannelsObject`（ID/Contact/ObjectDesc/ObjectNonceId/SourceURL/CreateTime/Type/Spec/LiveInfo/Files/AnchorContact）、`ChannelsObjectDesc`（Description/Media[]/MediaType/FollowPostInfo）。
  - 作者/关注：`ChannelsContact`（Username/Nickname/HeadUrl/Signature/CoverImgUrl）、`ChannelsFollowContact`（+FollowFlag/FollowTime/SpamStatus/ExtInfo/LiveInfo/ReferenceInfo）、`InfoListItem`。
  - 直播：`ChannelsLiveInfo`、`ChannelsLiveMicSetting`、`JoinLiveInfo`、`JoinLivePayload`（LiveCdnUrl——**直播流地址**）。
  - 各接口 Resp：`ChannelsContactSearchResp`（搜索）、`ChannelsFeedListOfAccountResp`（作者主页 feed 列表，含 FinderUserInfo/FeedsCount/AnchorStat/IPRegionInfo）、`ChannelsSharedFeedProfileResp`（分享链接）、`ChannelsFeedProfileResp`（单条 feed 详情）、`ChannelsFeedCommentListResp`（评论列表，含 FeedCommentInfo/CommentCountInfo/CountInfo）、`ChannelsFollowListResp`（关注列表）、`ChannelsPlayHistoryResp`（播放历史）、`ChannelsFeedShareUrlResp`（feed H5 链接）。
  - 请求体：`ChannelsAccountSearchBody`（keyword/next_marker）、`ChannelsFeedListBody`（username/next_marker）、`ChannelsLiveReplayListBody`、`ChannelsLiveInfoBody`（username/oid/nid/id）、`ChannelsFeedProfileBody`（url/oid/nid/eid）、`ChannelsFeedCommentListBody`（oid/nid/comment_id/next_marker）、`ChannelsSharedFeedProfileBody`（url）。
  - 分页游标：所有列表 Resp 的 `LastBuffer/ContinueFlag`——**next_marker=LastBuffer**（B5 分页依据）。
  - 分享结果：`SphProfile`（share_url/sph_id/export_id/video_url/origin_video_url/...）、`FeedURLParts`、`SphURLParts`。
  - Interceptor 系列（B6 用，snake_case 字段）：`InterceptorMediaSpec`、`InterceptorContact`、`MediaProfile`。

**Python 翻写设计**：
- 模块：`core/models/wxchannels.py`（Pydantic v2）+ `core/utils/wx_url.py`（URL 解析，独立于 models）。
- **Pydantic 关键设计**：
  - 所有 ID/DecodeKey 字段类型 `str`，加 `BeforeValidator(flexible_str)`（数字→str、str→str、None→""）——对应 Go flexibleString。
  - `extra="ignore"`（微信响应字段远多于模型，未知字段丢弃）。
  - `ChannelsMediaItem` 提供 `decode_key_int() -> int`（B3 解密要 uint64 key，str→int）。
  - `ChannelsObject.id` 即 DB `author_videos.video_id`；`ObjectDesc.Media[0].URL/DecodeKey/FileSize` → 下载三要素。
- `core/utils/wx_url.py`：
  - `parse_feed_url(raw) -> FeedURLParts`（Python：urlparse → 校验域名/路径 → oid/nid base64 解码转十进制）。
  - `parse_sph_share_url(raw) -> SphURLParts`。
  - `base64_to_uint64_str(s) / uint64_str_to_base64(s)`（对齐 util.go:31-67，base64url 无填充 + 8 字节大端）。
- **对齐现有 DB（core/utils/database/base.py 已实读）**：
  - `author_videos` 表（video_id/author_id/object_nonce_id/url/decode_key INTEGER/cover_url/duration/create_time/video_type...）——B4 模型映射到该表：`ChannelsObject.ID→video_id`、`Media[0].URL→url`、`Media[0].DecodeKey→decode_key`、`Spec[0].DurationMs→duration`、`Contact.Nickname→作者名`。
  - **决策点**：DB `decode_key` 是 INTEGER（存 uint64），模型是 str——落库前转 int（`decode_key_int()`），出库显示按 str。B4 不改表结构（保持兼容）。
  - `download_tasks` 表（task_id/video_id/url/key INTEGER/status/progress/downloaded/total_size...）——B3 下载管道落此表，字段已齐。

**与现有代码接入点**：
- `core/utils/database/crud/models.py`（Author/AuthorVideo/DownloadTask）为 DB 层模型（现有，不动）；**新增的 `core/models/wxchannels.py` 是上游响应模型**（序列化层），两者分工：响应模型→DB 模型由 B5/B10 转换。
- B5（client.go）反序列化响应直接 `WxModel.model_validate_json(data)`。
- B6（interceptor）用 `MediaProfile/InterceptorMediaSpec`（snake_case）——**与主模型命名体系不同，翻写时保留 snake_case 独立类，不合并**。

**风险/决策点**：
- **大整数截断**（对应"大整数角落遗漏"讨论）：ID/DecodeKey 超过 2^53（JS 安全整数）——Pydantic int 会截断，**必须 str**。已通过 flexibleString 实锤。
- **uint64 范围**：`decode_key` 是 uint64，Python int 无上限，但 JSON 里可能以字符串给出大数——BeforeValidator 兜住。
- base64 解码失败/长度不足：util.go 静默返回 ""（util.go:37-42）——翻写同规则，不抛异常（ParseFeedURL 里 oid 解码失败就用原样字符串）。

**验收细则**：
1. `model_validate_json`：用 B5 实测响应样例（或 scripts_probe 抓取的 JSON）反序列化 → `object.id`/`media[0].decode_key` 为 str 且与原 JSON 一致（数字字段无截断）。
2. `flexible_str`：`decode_key: 2136343393`（数字）与 `"2136343393"`（字符串）→ 都解析为 `"2136343393"`。
3. URL 解析：`channels.weixin.qq.com/web/pages/feed?oid=<base64>&nid=<base64>&eid=x` → oid/nid 十进制一致；`weixin.qq.com/sph/xxx` → id=xxx；非法 URL → 抛 UnsupportedURLError。
4. `base64_to_uint64_str`：util.go 的 8 字节大端样例往返一致。
5. 验证命令：`python -m unittest core.models.tests.test_wxchannels` + `core.utils.tests.test_wx_url`。

**工作量**：2 个子块（核心模型+URL 解析 ~300 行；全量 Resp/请求体模型 ~250 行），1-1.5 天。

### B2 流式解密 Reader——L1（执行级，2026-10-29 落档）

**上游源码**：`pkg/scraper/wxchannels/reader.go`（74 行，逐行读毕）

**上游逻辑（逐函数）**：
- `DecryptReader` 结构体：`reader io.Reader`（底层数据源）+ `ctx *RandCtx64`（B1 实例）+ `limit uint64`（加密区长度）+ `consumed uint64`（已消费字节）+ `ks [8]byte`（当前 keystream 块）+ `ksPos int`（块内偏移）。
- `NewDecryptReader(reader, key, offset, limit)`（reader.go:18-45）：
  - 创建 ISAAC 实例；limit>0 时对齐 offset——`offset >= limit` 则 `consumed=limit`（整个跳过，不解密）；否则跳过 `offset/8` 个完整 keystream 块（reader.go:34-37 循环 `ISAacRandom()`），生成当前块后 `ksPos = offset%8`（reader.go:39-41）。
  - **关键**：这是"断点续解"核心——不用从头流式重放，直接快进到 offset 对应的 keystream 位置。
- `Read(p []byte)`（reader.go:47-73）：
  - 先读底层（`n, err := dr.reader.Read(p)`）；`n<=0` 直接返回。
  - `limit==0 || consumed>=limit` → 原样返回（**未加密区透传**，reader.go:52-54）。
  - `toDecrypt = min(n, limit-consumed)`（reader.go:56-59）；逐字节 `p[i] ^= ks[ksPos]`，`ksPos>=8` 时重新 `ISAacRandom()` 装块（reader.go:63-68）；`consumed += toDecrypt`（reader.go:71）。
  - **注意**：只解密前 encLimit 字节，超出透传——视频文件 128KB 后原样输出。

**Python 翻写设计（代码级，2026-10-29 用户确认接口形态：类 + read(n)）**：
- 模块：`core/decrypt/decrypt_reader.py`；类：`DecryptReader(source: BinaryIO, key: int, offset: int = 0, limit: int = 0)`，方法 `read(n: int = -1) -> bytes`。
- 内部字段：`_source`（底层流）、`_ctx`（B1 RandCtx64，**不重复实现 ISAAC**）、`_limit`（加密区长度，0=全透传）、`_consumed`（已消费）、`_ks`（当前 8 字节块）、`_ks_pos`（块内偏移，8=已用完）、`_offset`。
- `_skip_to(offset)` 初始化快进：`limit==0` 直接返回（全透传）；`offset>=limit` 置 `consumed=limit`（整个跳过不解密）；否则 `consumed=offset`，**逐块循环** `ctx.random()` 跳过 `offset//8` 块（keystream 必须连续生成，不能乘算跳），`struct.pack(">Q", rand & MASK)` 装当前块，`ks_pos = offset % 8`。
- `read(n)`：`data = _source.read(n)` → 空则返回 `b""`；`limit==0 or consumed>=limit` 原样透传；`to_decrypt = min(len(data), limit - consumed)` 逐字节 `out[i] ^= ks[ks_pos]`（`ks_pos>=8` 时 `ctx.random()` 重装块）；`consumed += to_decrypt`。
- 断点续传用法：`httpx.stream("GET", url, headers={"Range": f"bytes={pos}-"})` + `DecryptReader(stream, key, offset=pos, limit=131072)` + `open(dest, "ab")` 追加写 → 续传部分从 pos 处解，拼接正确（`shutil.copyfileobj(reader, f)` 即可，因 read(-1) 读到 EOF）。
- 生成器版 `iter_decrypt(stream, key, offset, limit)`：按需再补（用户确认类形态优先，文件落盘更通用）。

**与现有代码接入点**：
- B1 的 `scripts_probe_python_decrypt.py` 目前是"整体读入+解密"（generate_keystream 一次性 128KB）——B2 把它升级为"边读边解"，是 `core/decrypt/decrypt_reader.py` 的雏形，不新增外部依赖。

**风险/决策点**：
- Go `io.Reader.Read` 是"读尽量多，可能 n<len"语义；Python `read(n)` 同样可能少读——**不能用 while 假设一次读满**，必须按实际返回长度处理（与上游一致：`n, err := dr.reader.Read(p)` 后按 n 算 toDecrypt）。
- offset 快进要**逐块 skip**（上游 reader.go:34-37 是循环），不能用 `offset/8` 一次乘算——keystream 必须连续生成，跳块=状态不对。翻写时保留逐块循环。

**验收细则**：
1. 同一加密文件：`offset=0` 全量解 vs `offset=1024` 断点解 → 两结果拼接后字节级一致（`python -c` 对比 sha256）。
2. 边界：`offset >= limit` → 输出与原文件一致（完全透传）；`limit=0` → 全透传。
3. 未加密区透传：加密文件第 131072 字节之后内容原样保留。
4. 验证命令：`python -m unittest core.decrypt.tests.test_decrypt_reader`（含 4 条断言）。

**工作量**：1 个子块（~90 行实现 + ~60 行单测），0.5-1 天。

### B3 解密服务——L2（执行级，2026-10-29 落档）

**上游源码**：`pkg/scraper/wxchannels/decryptor.go`（378 行，逐行读毕）

**上游逻辑（逐函数）**：
- `ChannelsVideoDecryptor` 结构体：`client *http.Client`（Transport 禁 HTTP/2、MaxIdleConns=100、IdleConnTimeout=90s，decryptor.go:21-31）。
- `ConvertWithDecrypt(w, targetURL, key, encLimit, filename)`（decryptor.go:37-86）：GET 上游 → `NewDecryptReader(body,key,0,encLimit)` → **ffmpeg 转 mp3**（`-i pipe:0 -vn -acodec libmp3lame -ab 192k -f mp3 pipe:1`，decryptor.go:52-59）→ `io.Copy` 流式输出；保证 `.mp3` 后缀（decryptor.go:73-77）。
- `DecryptOnly(w, r, targetURL, key, encLimit, filename)`（decryptor.go:88-130）：透传请求方法/Range 头 → 上游响应**解析 `Content-Range` 得 startOffset**（decryptor.go:101-113）→ `NewDecryptReader(body,key,startOffset,encLimit)` → 透传上游全部 header + 强制 `Content-Type: application/octet-stream` + `Accept-Ranges: bytes` → `HEAD` 只回头部、`GET` 流式输出（decryptor.go:116-129）。
- `DecryptOnlyInline`（decryptor.go:133-170）：同 DecryptOnly 但无 attachment 头（**内嵌播放**用）。
- `ConvertWithDecryptInline` / `ConvertOnly` / `ConvertOnlyInline`（decryptor.go:172-307）：转 mp3 的变体；`ConvertOnly` 系列**不解密只转码**（format!=mp3 时回落 SimpleProxy）。
- `prepareRequest(method, targetURL, header)`（decryptor.go:309-324）：只允许 GET/HEAD，透传 Range 头。
- `SimpleProxy(targetURL, w, r)`（decryptor.go:326-355）：纯透传（不带解密）。
- `DecryptFile(inputPath, outputPath, key, encLimit)`（decryptor.go:357-377）：本地文件解密落盘。

**Python 翻写设计**：
- 模块：`core/decrypt/decrypt_service.py`。
- **决策（2026-10-29 自决留痕）**：上游 6 个 HTTP 处理器中有 4 个是"HTTP 中间层/内嵌播放/转 mp3"形态——**号匣核心产品是"下载视频文件"，不是"代理播放/音频提取"，故只翻写 2 个核心能力**，其余标注"按需扩展"：
  - `download_and_decrypt(url: str, key: int, enc_limit: int, dest: Path, offset: int = 0, headers: dict | None = None) -> dict`：httpx 流式下载 + `DecryptReader` 边解边落盘。返回 `{status, downloaded, total, path}`。对应上游 `DecryptFile` + `DecryptOnly` 的下载侧。
  - `decrypt_file(src: Path, dest: Path, key: int, enc_limit: int) -> dict`：本地文件解密落盘，对应上游 `DecryptFile`（decryptor.go:357）。
  - 按需扩展（不阻塞）：`proxy_decrypt`（内嵌播放/流式透传）、`convert_to_mp3`（ffmpeg 转码，`subprocess` 调 ffmpeg，需登记 ffmpeg 依赖）。
- 依赖：httpx（号匣已有 0.28）、B1 `isaac64.py`、B2 `decrypt_reader.py`。**不引入新包**。

**与现有代码接入点**：
- `core/service/task.py` 下载链路当前把任务交给 `wx_video_download.exe`（Go）——B3 完成后，微信视频号下载路径改为 `core/decrypt/decrypt_service.download_and_decrypt`（Python 自研），`core/api/app.py` / `core/api/routers/base_service.py` 中微信视频号 exe 启停逻辑逐步移除（与 B1/B7 联动）。

**风险/决策点**：
- **Range 断点**：上游解析上游 `Content-Range` 得 startOffset——前提是上游 CDN 支持 Range（已实测：微信视频号直链支持，scripts_probe_range_support.py）。翻写时若上游返回 200（不支持 Range），offset 直接置 0 全量下载。
- **Content-Range 解析健壮性**：上游只处理 `bytes a-b/c` 形态，其余忽略（decryptor.go:102-113）——翻写同规则。
- **超时/重试**：上游 http.Client 无显式超时；号匣侧需加（httpx timeout=30s + 重试策略，对齐已讨论的"重试时间+熔断切换"）。

**验收细则**：
1. `decrypt_file`：用 scripts_probe_python_decrypt.py 样本（D:\dev\wechat-decrypt\...\wx_encrypted.mp4，key=2136343393）解密 → ftyp 存在 + ffprobe 可解析（复用现有验证脚本断言）。
2. `download_and_decrypt`：对实测 TikHub 直链（wxapp.tc.qq.com）下载+解密 → 落盘文件 sha256 与已知解密结果一致。
3. 断点：Range 请求 offset=1024 → 解密拼接一致。
4. 验证命令：`python -m unittest core.decrypt.tests.test_decrypt_service`。

**工作量**：2 个子块（下载解密管道 + 单测），1-1.5 天。

### B5 API 客户端（HTTP+WS）——L3（执行级，2026-10-29 落档）

**上游源码**：`pkg/scraper/wxchannels/client.go`（530 行，逐行读毕）+ `util.go`（70 行，逐行读毕）

**核心架构认知（重要）**：B5 **不是**直接调微信 HTTP API 的客户端——它是**通过 WebSocket 连接"已打开微信视频号网页的前端页面"（浏览器注入 agent），向页面发送 `api_call` 消息，由页面 JS 调真实微信 API 并把结果经 WS 回传**。即"前端转发代理"模式：
- 浏览器页面持有微信登录态（Cookie），页面内注入的 agent JS 注册了 `key:channels:*` 的 API 处理函数。
- Go 服务端 WS 升级浏览器连接（client.go:135-203 `ServeWebsocket`），页面里 agent JS 作为 WS 客户端连上来。
- `RequestFrontend(endpoint, body, timeout)`（client.go:253-305）：分配自增 id → 封装 `APIClientWSMessage{Type:"api_call", Data:{ID,Key,Body}}` → 写入 WS → 等页面回 `ClientWebsocketResponse{Id, Data}`（用 map[id]chan 匹配，client.go:192-202）→ 超时返回 "request timed out"。

**上游逻辑（逐函数）**：
- 消息结构（util.go:50-69）：`APIClientWSMessage{type,data,error}`、`ClientWebsocketRequestBody{id,key,data}`、`ClientWebsocketResponse{id,data}`（data 为 json.RawMessage 原样透传）。
- `Client` 结构（client.go:48-61）：`ws_clients`（连接集合）、`requests`（id→chan 待响应表）、`cache`（响应缓存）、`req_seq`（原子自增）、`cookie_reader`、`sph_cookie`、三个回调 `OnConnected/OnDisconnected/OnMessage`。
- `Fetch(params)`（client.go:75-85）：URL 分派——`^https://weixin\.qq\.com/sph/...` → `fetch_profile_with_share_url`（走元宝 Cookie，B8）；`channels.weixin.qq.com/web/pages/feed`（oid+nid 齐）→ `FetchFeedPage`；否则 `ErrUnsupportedURL`。
- `resolve_sph_cookie`（client.go:100-122）：元宝 Cookie 解析优先级：cookies.Reader（.tencent.com 域）→ 配置 fallback `sph_cookie` → 报错。**这是 B5 与 B9 的接缝**。
- `ServeWebsocket`（client.go:135-203）：WS 升级（允许任意 Origin）→ 注册客户端 → `write_pump`（心跳 5s Ping + 10s 写超时，util.go:15-48）→ 可选 `refresh_interval` 周期 `ReloadChannels()`（client.go:152-170）→ 读循环：页面回包按 id 投递到 chan（client.go:186-202）。
- `RequestFrontend`（client.go:253-305）：核心 RPC——注册 id → 挑一个 client 发消息（Send 缓冲满即报错）→ select 等响应或超时。
- **9 个业务方法**（全部 `RequestFrontend("key:channels:xxx", body, timeout)` + 缓存）：
  | 方法 | key | 请求体 | 缓存 |
  |---|---|---|---|
  | `SearchChannelsContact` | contact_list | {keyword,next_marker} | 5min |
  | `FetchChannelsFeedListOfContact` | feed_list | {username@finder,next_marker} | 5min |
  | `FetchChannelsLiveReplayList` | live_replay_list | {username@finder,next_marker} | 5min |
  | `FetchLiveProfile` | live_profile | {username,oid,nid,id} | 无 |
  | `FetchChannelsInteractionedFeedList` | interactioned_list | {flag,next_marker} | 5min |
  | `FetchChannelsFollowList` | follow_list | {next_marker} | 5min |
  | `FetchChannelsPlayHistory` | play_history | {next_marker} | 5min |
  | `FetchChannelsFeedProfile` | feed_profile | {url,oid,nid,eid} | 60min |
  | `FetchChannelsFeedCommentList` | fetch_feed_comment_list | {oid,nid,comment_id,next_marker} | 60min |
  | `FetchChannelsFeedShareUrl` | feed_share_url | {oid} | 60min |
  | `ReloadChannels` | reload | nil | 无 |
  - **username 规范化**：FeedList/LiveReplay 自动补 `@finder` 后缀（client.go:330-333, 350-353）。
  - 缓存 key 格式 `channels:<endpoint>:<params>`，Ttl 5min/60min 两档。
  - 超时：搜索 20s，其余 10s，reload 5s。

**Python 翻写设计**：
- 模块：`core/protocol/ws_client.py`（WS 连接+消息协议）+ `core/service/channels_api.py`（9+ 业务方法，对应 B10 门面的数据来源）。
- 依赖：`websocket-client`（号匣已有，对齐 master pyproject）、B4 模型、B9 Cookie。
- `class ChannelsClient`：
  - `connect(ws_url)` / `disconnect()`；`on_message` 回调里按 `id` 匹配 pending chan。
  - `request(endpoint: str, body: dict, timeout: float) -> dict`：对应 RequestFrontend——自增 id、发 `{"type":"api_call","data":{"id","key","data"}}`、等响应/超时（`asyncio.wait_for` 或 `queue.Queue` + 超时）。
  - 9 个业务方法同名翻写（`search_contact`/`fetch_feed_list_of_contact`/`fetch_live_replay_list`/`fetch_live_profile`/`fetch_interactioned_feed_list`/`fetch_follow_list`/`fetch_play_history`/`fetch_feed_profile`/`fetch_feed_comment_list`/`fetch_feed_share_url`/`reload`），返回 B4 Pydantic 模型（`model_validate_json`）。
  - 缓存：`functools.lru_cache` 或 dict + TTL（5min/60min 两档，key 与上游一致）。
- `class WsConnectionManager`：连接生命周期、心跳（ping_interval=5s）、重连（与已讨论的熔断/重试策略联动）。

**与现有代码接入点**：
- `core/utils/weixin_client.py`（现有，微信客户端 exe 通信）与 `core/utils/socket_client.py`（现有）——B5 的 WS 通道**替代/并行**现有 exe 启停逻辑：视频号数据获取从"问 exe"改为"问页面 WS"。具体替换边界由 B10 门面定。
- B3 的 `download_and_decrypt` 拿到的直链 URL + `DecodeKey` 来自 B5 的 feed_profile 响应（`ChannelsObject.ObjectDesc.Media[0]`）。

**风险/决策点**：
- **依赖浏览器登录态**：B5 必须有一个"已登录微信视频号的浏览器页面"开着（agent 注入）——**这是号匣客户端现有架构**（core/api/app.py 启 exe + 页面）。翻写保持同架构：Python 端只做 WS 转发，不自己发微信 HTTP（微信 API 签名/加密在页面 JS 里，无法 Python 复刻——**这是不翻写 HTTP 直连的原因，与 B6 逆向清单区分**）。
- **超时语义**：上游 10s/20s 超时——翻写保留，超时视为接口失败（触发重试/熔断）。
- **并发安全**：Go 用 map+chan+mutex；Python 用 `asyncio.Queue` + `dict[id]=Future`（或线程版 `queue.Queue`），注意 WS 消息回调线程与等待线程的解耦。
- **缓存失效**：微信视频号数据 5min/60min 缓存——对齐已讨论的"低频按需缓存"策略。

**验收细则**：
1. 本地起 WS echo server（mock 页面），`request()` 发 api_call → 回包 id 匹配 → 返回 data；超时路径返回错误。
2. `fetch_feed_profile("", "", url, "")` 对实测分享链接 → 返回 B4 `ChannelsFeedProfileResp` 模型（oid/nid 非空）。
3. 9 个业务方法签名与上游一致（参数校验：keyword 非空、oid 非空、nid/comment_id 至少一个）。
4. 缓存：同参数二次调用不触发 WS 发送（mock 计数）。
5. 验证命令：`python -m unittest core.protocol.tests.test_ws_client` + `core.service.tests.test_channels_api`。

**工作量**：2 个子块（WS 协议层 + 业务方法层），1-1.5 天。

### B9 微信 Cookie 支撑——L3（执行级，2026-10-29 落档）

**上游源码**：`pkg/cookies/cookies.go`（376 行，逐行读毕）+ `persistent.go`（157 行，逐行读毕）

**上游逻辑（逐函数）**：
- `Cookie` 结构（cookies.go:23-32）：name/value/domain/path/secure/httpOnly/sameSite/expires（-1=会话）。
- `Jar`（cookies.go:91-221）：线程安全 cookie jar——`NewJar`/`SetCookies`/`Cookies`/`SetCookieFromHeader`/`SetCookieFromString`/`SetAllCookies`/`SaveToJSON`/`LoadFromJSON`/`LoadFromNetscape`。**注**：`SaveToFile`（Netscape 格式）实际只写注释占位（cookies.go:158-182 坑：cookiejar 无法枚举全部 cookie，主保存格式是 JSON）。
- `ParseCookieHeader`/`ParseSetCookies`/`FormatCookieHeader`/`FormatSetCookie`/`ExtractFromResponse`（cookies.go:260-321）。
- **持久化 Reader（persistent.go:23-126）——B5 直接依赖**：`NewPersistentReader(work_dir)` → 读 `<work_dir>/cookies.json`；`HeaderForDomain(domain)`（按域+过期过滤，persistent.go:34-59）；`HeaderForURL(raw_url)`（域+路径+secure+过期匹配，长 path 优先排序，persistent.go:64-107）。**每次调用重读文件**（新同步的 cookies.json 即时生效，persistent.go:61-63 注释）。
- 域匹配规则（persistent.go:128-156）：`normalize_persistent_domain`（去首 `.` 小写）→ 子域匹配（cookie 域带 `.` 前缀 = 通配子域）；路径匹配（RFC 规则：`/foo` 匹配 `/foo/bar`）。
- 错误：`ErrCookieNotFound`（persistent.go:19）。

**Python 翻写设计**：
- 模块：`core/security/cookie_jar.py`（Jar + 解析）+ `core/security/cookie_reader.py`（持久化 Reader）。
- 依赖：Python 标准库（`http.cookiejar` 有 Netscape/JSON 支持但枚举受限——**直接用 stdlib `http.cookiejar.MozillaCookieJar`/`LWPCookieJar` 或自写 JSON 存储**；为对齐上游 JSON 格式（CDP/Chrome 风格字段），**自写 JSON 存取**更直接）。
- `class PersistentCookieReader`：
  - `__init__(work_dir)`；`header_for_domain(domain) -> str`；`header_for_url(url) -> str`（域/路径/secure/过期过滤 + 长 path 排序，逐行对齐 persistent.go）。
  - **每次调用重读 `cookies.json`**（保持上游"新同步即时生效"语义）。
- `class CookieJar`：parse/format 工具（ParseSetCookies/FormatCookieHeader/ExtractFromResponse）+ 线程安全读写。
- 接入点：B5 `ChannelsClient` 构造传 `cookie_reader`；元宝 Cookie 由 B8 用 `header_for_domain(".tencent.com")`。

**与现有代码接入点**：
- 号匣现有 Cookie 来源（浏览器登录态）在 `core/utils/weixin_client.py`/前端注入——B9 提供**统一 Cookie 读取层**（cookies.json 落盘路径对齐号匣 work_dir）。

**风险/决策点**：
- **Cookie 过期**：微信 Cookie 有有效期——HeaderForDomain 已按 expires 过滤；过期=接口失败（触发重新登录流程，B10 处理）。
- **JSON 格式**：上游字段是 CDP/Chrome 风格（httpOnly 驼峰）——Python 存储沿用同 schema，兼容上游导出文件。

**验收细则**：
1. `cookies.json`（含 .tencent.com 域 cookie）→ `header_for_domain(".tencent.com")` 返回正确 `name=value; name2=value2`。
2. 过期 cookie 被过滤；域不匹配返回 ErrCookieNotFound 语义（空+异常）。
3. `HeaderForURL`：https 请求过滤 secure=false 的 cookie、长 path 优先排序。
4. 验证命令：`python -m unittest core.security.tests.test_cookie_reader`。

**工作量**：1 个子块（~200 行），0.5-1 天。

### B8 元宝链接解析器——L3（执行级，2026-10-29 落档）

**上游源码**：`pkg/scraper/wxchannels/yuanbao.go`（260 行，逐行读毕）

**核心作用**：B5 `Fetch` 分派中"分享链接通道"的另一半——**`weixin.qq.com/sph/{id}` 链接无法用 ParseFeedURL 解析（无 oid/nid），走元宝 API 解析**。两步管道：元宝解析 share_url → 得 playable_url（含 token/eid）→ 再调微信 get_feed_info 拿完整 feed 数据。

**上游逻辑（逐函数）**：
- **ParseShareUrl(share_url, cookie)（yuanbao.go:104-164）**：
  - POST `https://yuanbao.tencent.com/api/weixin/get_parse_result`，payload `{"type":"video_channel_url","url":"<share_url>","scene":1}`（yuanbao.go:107）。
  - **全量请求头实锤（yuanbao.go:113-143）**：`accept/origin/referer/user-agent(Chrome 148 macOS)/sec-ch-ua/t-userid/x-agentid/x-commit-tag(72282a0d)/x-device-id/x-hy92/x-hy93/x-id/x-instance-id/x-language/x-os_version/x-platform/x-requested-with/x-source/x-web-third-source/x-webdriver/x-webversion(2.69.0)/x-ybuitest` + **cookie（身份凭据）**。
  - 返回 `ParseResponse{code,msg,data:{wx_export_id,cover_url,author,author_icon,desc,playable_url,author_certification_icon}}`（yuanbao.go:18-32）。
  - **关键**：这些 x-* 头（x-commit-tag/x-hy92/x-hy93/x-id/x-webversion 等）大概率是**客户端指纹/风控参数**——直接照搬可能失效，需实测（风险点）。
- **get_feed_info(export_id, general_token)（yuanbao.go:166-211）**：
  - POST `https://channels.weixin.qq.com/finder-preview/api/feed/get_feed_info?_rid=<rid>&_pageUrl=...`，payload `{"baseReq":{"generalToken":"<token>"},"exportId":"<export_id>"}`（yuanbao.go:170-171）。
  - `_rid` = `generate_rid()`（yuanbao.go:48-55）：hex 时间戳 + "-" + 8 位随机 hex（非 crypto 随机，math/rand）。
  - Referer 含 token/eid（yuanbao.go:183）；**无需 cookie**（纯 preview API）。
  - `parse_feed_info_error`（yuanbao.go:75-102）：errCode 非 0 / data.errMsg 非空 → 提取 `plain_text_from_html` 清洗后的错误消息（去 HTML 标签 + html.UnescapeString + 折叠空白，yuanbao.go:57-73）。
- **FetchVideoProfileWithShareUrl(share_url, cookie)（yuanbao.go:213-248）**——两步管道：
  1. `ParseShareUrl` → 从 `playable_url` query 提取 `token`（general_token）+ `eid`（export_id）（yuanbao.go:227-230）；缺失仅 warn 不报错（yuanbao.go:231-236，容错）。
  2. `get_feed_info(export_id, general_token)` → 返回 json.RawMessage（B4 `ChannelsFeedProfileResp` 形状）。
- **CleanVideoURL(video_url)（yuanbao.go:250-259）**：删除 query 中 `X-snsvideoflag` 参数（微信防重放 flag，直链转存时需清掉）。

**Python 翻写设计**：
- 模块：`core/protocol/yuanbao.py`（对应 B8 落点；早期 v0.3 要点写过 `core/api/yuanbao_parser.py`——**落 core/protocol/ 与 B5 的 ws_client 同层**，api 层留给 B10 门面）。
- 函数签名：
  - `parse_share_url(share_url: str, cookie: str) -> ParseResponse`（httpx POST + 全量头；返回 B4 或本地 dataclass——`ParseData` 6 字段）。
  - `get_feed_info(export_id: str, general_token: str) -> dict`（httpx POST + `_rid`；返回 dict 给 B4 `ChannelsFeedProfileResp.model_validate`）。
  - `fetch_video_profile_with_share_url(share_url: str, cookie: str) -> dict`（两步管道，对应 B5 `Fetch` 的 share_url 分支）。
  - `clean_video_url(video_url: str) -> str`。
  - `_generate_rid()`：对齐 generate_rid——`format(time.time_ns//1e9, "x")` + 8 位 `secrets.choice` 或 rand 16 进制（**用 secrets 更稳，但为对齐上游行为可先用 rand**）。
- 依赖：httpx、B4 模型；**复用 B9 `cookie_reader.header_for_domain(".tencent.com")` 取 cookie**（B5 `resolve_sph_cookie` 已封装此逻辑，B8 直接用）。

**与现有代码接入点**：
- `core/api/routers/base_service.py`（现有 exe 启停）——B8 完成后，分享链接解析路径 `fetch_video_profile_with_share_url` 替代 exe 的同类能力（与 B5/B10 联动）。
- B5 `ChannelsClient.fetch()` 的 share_url 分支直接调用 B8。

**风险/决策点（重要）**：
- **x-* 头风控风险**：上游硬编码了 `x-commit-tag=72282a0d`、`x-webversion=2.69.0`、`x-hy92/x-hy93/x-id/x-device-id` 等指纹头（yuanbao.go:125-142）——**这些值会随元宝版本更新失效**（平台侧主动防爬）。翻写策略：**头参数集中成配置常量 + 可覆盖**；实测失效时按"行业通用做法"换新头（对齐偏好"查行业标准+自身约束"）。**不做逆向推导指纹生成算法**（成本高收益低，超出翻写范围）。
- **cookie 依赖**：元宝 API 强依赖 `.tencent.com` Cookie（B9 提供）；无 cookie → 报"no yuanbao cookie"（B5 resolve_sph_cookie 语义）。
- **不翻写 headless 浏览器自动化**：用户曾讨论"浏览器自动化找接口"——B8 是**纯 HTTP 解析**（上游已确认可行），不需要浏览器。

**验收细则**：
1. 用实测分享链接 + `.tencent.com` cookie → `fetch_video_profile_with_share_url` 返回可解析的 feed 数据（exportId 非空，get_feed_info 成功）。
2. `clean_video_url`：带 `X-snsvideoflag` 的 URL → 参数被删除，其余不变。
3. 错误路径：无效 share_url / 空 token → 返回明确错误（对齐 parse_feed_info_error 语义）。
4. 验证命令：`python -m unittest core.protocol.tests.test_yuanbao`。
5. **注意**：真实链路验收需真实分享链接 + 有效 cookie（运行时/登录态依赖）——单元测试用 mock 响应覆盖解析逻辑，端到端标注"待 B10 联调"。

**工作量**：1 个子块（~200 行 + 单测），0.5-1 天。

### B9 微信 Cookie 支撑——L3（v0.3 新增）
- pkg/cookies：HeaderForDomain（读指定域名 cookie）/ 持久化（persistent.go）。
- 号匣已有 server-secrets 管密钥 → 翻写为 `core/security/cookie_store.py`（结构化存取+持久化）。
- 验收：能读/写 .tencent.com 域 cookie。

### B6 JS 逆向接口清单——L3（执行级，2026-10-29 落档）

**上游源码**：`pkg/scraper/wxchannels/interceptor.go`（605 行，逐行读毕）

**上游逻辑（逐函数）**：
- 文件本质是 **MITM 响应改写插件**（echo 库，interceptor.go:73-605）——两个 plugin：
  - plugin_1 `channels.weixin.qq.com`（interceptor.go:109-273）：改 HTML——注入 `__d_config`、timeless 库、`/inject/*.js` 脚本、按页面路径（home/feed/live/profile）注入对应 channels.*.js。
  - plugin_2 `res.wx.qq.com`（interceptor.go:274-601）：改 JS——**用正则包装微信页面内的 finder* 接口函数，注入 `WXU.emit(...)` 事件**（这正是 B5 WS 桥的页面侧数据来源）。
- **接口清单（正则实锤，页面 JS 暴露的全部接口函数）**：

  | 接口函数（页面 JS） | 触发事件 | 对应 B5 key / 用途 |
  |---|---|---|
  | `finderInit` | channels:Init | 首页初始化 |
  | `finderGetCommentDetail` | channels:OnFeedProfileLoaded | **feed_profile（feed 详情）** |
  | `finderGetCommentList` | channels:FeedCommentListLoaded | **fetch_feed_comment_list（评论）** |
  | `finderPcFlow` | channels:PCFlowLoaded | 关注流 |
  | `getRecommendTabsFromService` | channels:RecommendFeedsLoaded | 推荐 tabs |
  | `finderGetRecommend` | channels:RecommendFeedsLoaded | 推荐 feeds |
  | `finderGetLiveInfo` | channels:OnLiveProfileLoaded | **live_profile（直播信息）** |
  | `finderLiveUserPage` | channels:LiveUserFeedsLoaded | 直播用户页/回放列表 |
  | `joinLive` | channels:JoinLive | **直播流地址（LiveCdnUrl，B4 JoinLivePayload）** |
  | `finderUserPage` | channels:UserFeedsLoaded | **feed_list（作者作品列表）** |
  | `finderPCSearch` / `finderSearch` | — | **contact_list（搜索）** |
  | `finderGetFollowList` | — | **follow_list（关注列表）** |
  | `finderGetPlayHistory` | — | **play_history（播放历史）** |
  | `finderGetInteractionedFeedList` | channels:InteractionedFeedsLoaded | **interactioned_list** |
  | `finderGetFeedH5Url` | channels:GetFeedH5Url | **feed_share_url（H5 链接）** |
  | `loadLocalPlaylist` / goToPrevFlowFeed / goToNextFlowFeed | channels:HomeFeedChanged / GotoPrev/NextFeed | 流内切换（辅助） |
  | `decodeBase64ToUint64String` / `createAdapterFromGlobalMapper` / `finderJoinLiveMapper` | channels:UtilsLoaded | 工具（B4 已翻写 base64 解码） |

- **关键结论**：B5 的 9 个业务 key **全部能在页面 JS 中找到对应接口**——B6 确认"页面侧数据源完整覆盖"，B5 无需补接口；B6 真正价值是**字段级比对**（下方验收）。
- **不翻写部分（明确）**：MITM 代理、证书、HTML/JS 改写注入、WXU 事件桥——号匣纯 API 零注入（已在弃用边界）。

**Python 翻写设计**：
- 产出：`core/protocol/wxchannels_api_map.py`——**静态清单模块**（接口名 → 参数形状 → 响应形状 → 对应 B5 key → 对应 B4 模型），注释标注 interceptor.go 行号。
- 结构：`API_MAP = { "finderUserPage": {...}, ... }` + 两个函数：
  - `find_unused_fields(provider_resp: dict) -> list[str]`：给定红狐/TikHub 响应，比对 B4 模型已覆盖字段，列出未用字段（"接口里很多数据没用上"的直接产出）。
  - `api_coverage_report() -> dict`：输出"页面接口 ↔ B5 key ↔ B4 模型"覆盖矩阵。
- **不实现注入/改写**：纯清单+比对，供 B10 门面参考。

**与现有代码接入点**：
- B5 `ChannelsClient` 的 9 个 key 与 B6 清单交叉验证（B5 已实现的方法是否覆盖页面全部接口）。
- B10 门面按 B6 覆盖矩阵决定暴露哪些能力（如"直播流地址"是否要暴露）。

**风险/决策点**：
- **接口名会随微信前端更新变化**：interceptor.go 正则基于当前页面 JS 结构——清单标注"抓取日期 + 版本"（参考 B8 的 x-* 头版本风险，同属"上游变动需实测"）。
- B6 仅参考不执行：**不写正则注入代码**（号匣无 MITM），清单维护在 B10 需要时再校验。

**验收细则**：
1. `api_coverage_report()`：输出矩阵含上表全部 15+ 接口，每个标注对应 B5 key / B4 模型 / 是否已用。
2. `find_unused_fields`：用红狐/TikHub 实测响应样例 → 列出未入 B4 模型的字段（如粉丝数/关注数/作品数——对齐"作者维度数据抓全"讨论）。
3. 验证命令：`python -m unittest core.protocol.tests.test_wxchannels_api_map`。
4. **比对输出**：与红狐/TikHub 字段差异表（B10 联调时更新）。

**工作量**：1 个子块（~150 行清单 + 比对逻辑），0.5-1 天。

### B10 业务适配门面——L4（执行级，2026-10-29 落档）

**上游源码**：`internal/adapter/wxchannels/` 四件套——adapter.go（12.8KB）+ model.go（51.6KB）+ routes.go（12.8KB）+ postprocess.go（98.3KB，全仓最大单文件），全部逐行读毕。

**上游架构（四件套分工实锤）**：
- **adapter.go（薄门面）**：`ChannelsAdapter` 实现 8 个适配器接口（PlatformAdapter/RuntimeAdapter/Postprocessor 等），7 个业务方法**全部转发 B5 client**（SearchChannelsContact/FetchChannelsFeedListOfContact/FetchChannelsLiveReplayList/FetchChannelsFeedProfile/FetchChannelsFeedCommentList/FetchChannelsFeedShareUrl/Fetch），本身无逻辑（adapter.go:86-176）。平台状态 2 键：`wxchannels:page`（视频号页面连接）+ `wxchannels:sph`（分享链接 cookie）。
- **model.go（清洗转换层，B10 真正价值）**：把微信原始响应转成对外模型——
  - `ToAccount`（211-233）：ChannelsObject → model.Account（昵称/签名/头像）。
  - `ToContent`（247-373）：→ model.Content + 扩展（直播/图片/视频三型分派，Type=live/album/video）。
  - `BuildDownloadTask`（731-988）：**B10 心脏**——content_json → 下载任务 + 资源四元组（Task/Resources/Account/Content）。三分支：直播（LiveCdnUrl 校验，749/754）、图片（每图一资源 + BGM，820-912）、视频（下载 URL + 解密 extra，914-987）。
  - `parse_channels_object_for_download`（1167-1192）：**输入归一化**——依次尝试 ChannelsObject 直解 → feed_profile 响应（ErrCode≠0 报错）→ 分享 profile 转换（shared_feed_profile_to_channels_object，1204-1220，视频/图片分派）。
  - 辅助：`clean_media_url`（删 CDN 路由参数 hy/idx/m/uzid，44-56）、`BuildDownloadURLWithSpec`（642）、`build_resource_extra_json`（1482，含 decode_key）、`BuildDownloadTaskUniqueID`（1464）、`sanitize_filename` 族、`format_bgm`（1442）。
- **routes.go（18 个 HTTP 端点）**：`/api/channels/status|parse_sph|decrypt|contact/search|contact/feed/list|feed/profile|live/profile|live/replay/list|interactioned/list|follow/list|play/history|postprocess/flows|feed/share_url|shared_feed/profile|feed/comment/list` + `/ws/channels` + `/play` + `/rss/channels`（routes.go:47-64）。
- **postprocess.go（下载后文件处理流水线）**：**flowengine 编排**——三个 FlowDefinition（wxchannels_postprocess_flow/main_flow/output_flow，648/1044/1335）+ 节点（DecryptNode/ConvertMP3Node/FinalizeMP3Node/StreamConvertNode/FinalizeStreamNode/ZipResourcesNode/TaskJobUpdateNode，1572-1796），入口 `Postprocess`（1798-1821）。

**翻写取舍（B10 决策，用户确认"逻辑用他的、字段用咱们的"）**：
1. **翻写 model.go 的响应→模型转换逻辑**：ToAccount/ToContent/BuildDownloadTask/parse_channels_object_for_download 的思路照上游（微信响应特有的清洗规则，号匣 master 无此逻辑），**输出字段按 B4 Pydantic 模型 + Spec.md 表结构**（author_videos 的 export_id/share_url 列、decode_key TEXT、video_id=object_id 字符串）。
2. **翻写 adapter.go 的薄门面形态**：`core/api/wxchannels_service.py` 统一方法封装（7 个业务方法 + 输入归一化 parse），不含上游 runtime 注册/状态总线（号匣无 MITM 运行时）。
3. **postprocess.go 不翻写 flowengine**：解密由 B3 `decrypt_service` 承接、mp3 转码已在 B3 标"按需扩展"、zip 打包号匣无需求——flowengine 编排是"多格式转码+打包"场景的产物，号匣单流直链 + 解密落盘不需要。
4. **routes.go 不照搬 18 端点**：号匣已有自有路由体系（core/api/routers/*），B10 只取 7 个业务方法映射到号匣路由（对应 YZPQ-310 API 薄路由 38 接口）。

**落点/接入点**：
- `core/api/wxchannels_service.py`（业务门面：7 方法 + 响应后处理管道）。
- `core/models/wxchannels.py`（B4）供输出；`core/service/channels_api.py`（B5）供输入。
- 与 Spec.md 路由映射：`/api/channels/contact/search` → 号匣 `/api/v1/...`（按 YZPQ-310 路由表定）。

**风险/决策点**：
- **输入归一化是关键**：同一 content_json 可能是 ChannelsObject / feed_profile 响应 / 分享 profile 三形态（parse_channels_object_for_download 1167-1192）——翻写必须保留三态探测顺序，漏一个形态就解析失败。
- **decode_key 传递**：build_resource_extra_json 把 decode_key 塞进资源 Extra（1482）→ B3 解密时从 Extra 取——号匣同样把 decode_key 落 download_tasks（B4 已定 decode_key_int 转换），两处口径要一致。
- **图片/直播分支**：号匣主场景是视频，图片（album+BGM）和直播（LiveCdnUrl 校验）分支**保留实现但验收可降级**（号匣自用版先视频通路）。
- **文件名清洗**：sanitize_filename 族（换行符/非法字符）号匣 Spec 已有 safe_title 实践（含 \n\r\t），以号匣为准。

**验收细则**：
1. 三种输入形态（ChannelsObject/feed_profile/分享 profile）各用实测响应 → 统一输出 B4 模型（字段与 Spec.md 表结构逐字段对齐）。
2. 视频任务：BuildDownloadTask 输出 Task(Waiting) + 1 资源（mp4，含 decode_key extra）+ Account + Content，验收"下载入口三态"衔接。
3. 7 个业务方法均可达（路由映射通）；直播/图片分支按需验收。
4. 验证命令：`python -m unittest core.api.tests.test_wxchannels_service`。
5. 端到端：真实分享链接 → B8 解析 → B10 门面 → B3 下载解密 → 文件落盘（标"待 B1-B9 完成后联调"）。

**工作量**：2-3 个子块（门面 7 方法 + 响应后处理管道 + 输入归一化 + 单测），2-3 天。

### B11 浏览器注入桥——L3（执行级，2026-10-29 补档——此前误弃用，B5 命根子）

**上游源码**：`frontend/inject/*`（JS 资产 94KB，注入内容）+ `frontend/static_asset.go`（静态资产服务）+ `pkg/scraper/wxchannels/assets.go`（资产挂载）+ `interceptor.go` plugin_1/2（投放机制，已读）。

**为什么补这块（用户质疑触发，核查实锤）**：
- B5 `client.go` 的 WS 桥（client.go:135-203 ServeWebsocket）是**服务端**：它等浏览器连上来发 `api_call` 请求。**浏览器侧必须有注入的 JS 才会连 WS、才会调页面内的 finder* 接口**——没有注入 JS，B5 就是空壳。
- 上游官方用法（README 实锤）：首次运行自动装证书 → 启动 Sunny 代理 → 拦截 `channels.weixin.qq.com` HTML + `res.wx.qq.com` JS → 改写注入 `<script src="/__assets/wxchannels/inject/...">` → 注入 JS 建 WS 连本地。
- 之前规格把 frontend/inject 标"弃用（号匣自研 WebView2 前端）"是**错误的架构套用**（master 号匣走红狐/TikHub API 才零注入；wechat-downloader 零成本版必须从页面拿数据，注入不可少）。**v0.15 修正**。

**上游逻辑（逐模块）**：
- **注入 JS 资产（frontend/inject，94KB，核心内容）**：
  - `channels.ws.js`（WS 桥核心）：页面内建立 WebSocket → 连本地 `/ws/channels` → 处理 `api_call` 消息 → 调 `window.__channels_api__`（页面 JS 暴露的 finder* 函数）→ 回包按 id 匹配。
  - `channels.events.js` / `channels.utils.js`：WXU 事件桥 + 工具（decodeBase64ToUint64String 等，B4 已翻写）。
  - `channels.home.js` / `channels.feed.js` / `channels.live.js` / `channels.profile.js`：按页面（home/feed/live/profile）注入的页面逻辑。
  - `eventbus.js` / `utils.js` / `components.js` / `model.js`（119KB）/ `view.js`（80KB）/ `panel.js` / `fetch.js` / `file.js`：下载面板 UI + 业务——**UI 部分号匣不翻**（号匣自研 WebView2 前端）。
- **静态资产服务（frontend/static_asset.go:20-135）**：`MockStaticAsset` 供给 `/__assets/public|inject|src` + **用户全局脚本 `/__assets/user/global.js`**（GlobalScriptPath 机制，static_asset.go:64-67 + config.go:894 `inject.globalScript`）——**这是免 MITM 的第二条投放路**（用户手动/自动化把 JS 放进浏览器）。
- **投放方式（interceptor.go plugin_1/2，已读）**：MITM 改写 HTML 注入 script 标签 + 改写 res.wx.qq.com JS 包装 finder* 接口。

**翻写取舍（B11 决策，v0.16 修正：进程级代理取代系统代理）**：
1. **注入 JS 内容必翻**（channels.ws.js 桥 + channels.utils.js/events.js 桥接部分）——数据命根子，Python 侧无法替代（必须在浏览器页面环境里跑 JS）。
2. **投放方式 = 进程级代理（不碰系统代理）**——用户拍板优化：不用系统代理去 2023 劫持全机流量（污染其他软件、代理挂则全机断网），改用进程级。
   - **主方案（v0.17 修正：WebView2 单实例代理，用户成本最低）**：软件内嵌 WebView2（pywebview 现有技术栈）打开视频号页面，`AdditionalBrowserArguments="--proxy-server=http://127.0.0.1:2023"` —— Microsoft Learn 官方实锤：该参数 **override 系统设置、只影响本 WebView2 实例的 HTTP/HTTPS 请求**。用户点"打开视频号"→ 内嵌窗口 → 扫码登录一次 → 零操作；其他软件零影响；不设系统代理；零驱动。可选叠加 CDP 注入 JS 桥。
   - **备选方案（微信客户端内嵌页面场景，待用户拍板）**：mitmproxy `--mode local:<WeChat.exe>`（官方进程级，Windows 底层 WinDivert/WFP 内核驱动，只拦指定 PID），需驱动+证书，成本高。
3. **UI 不翻**：model.js/view.js/panel.js/components.js（下载面板 219KB）不翻——号匣自研 WebView2 前端已覆盖 UI（原"自研前端"理由对 UI 成立，对注入桥不成立）。
4. **证书策略**：MITM 需 TLS 证书；进程级方案下证书信任范围可只限专用浏览器实例（参数/实例级信任），**不装系统根证书**（相比上游全局装证书的改进点，需实测浏览器实例证书信任注入方式）。

**落点/接入点**：
- `core/protocol/browser_bridge.py`（CDP 注入器：打开已登录页面 + 注入 JS 桥 + 心跳/重连）。
- `core/static/inject/channels.ws.js` 等（翻写后的注入 JS，全新命名不照抄）。
- 与 B5 配对：B5 `ServeWebsocket` 是服务端（core/protocol/ws_client.py 反向——**B5 的 ws_client 是客户端还是服务端需对齐**：上游 client.go 是服务端 ServeWebsocket，浏览器是客户端连上来；Python 侧 FastAPI 提供 `/ws/channels` 端点 + 注入 JS 作为浏览器侧客户端）。
- 浏览器容器：号匣已有 pywebview 6.2（WebView2）——**可选**：用 pywebview 打开已登录页面（复用登录态）或外接用户已开的 Chrome（CDP 远程调试）。

**风险/决策点**：
- **微信前端改版**：finder* 接口签名/JS 变量名变化 → 注入 JS 失效（B6 清单联动维护，同 B8 x-* 头风险）。
- **CDP 注入被页面 CSP 拦**：需实测；备选手动注入（global.js）。
- **登录态时效**：cookie 失效需重新登录（B9 的 cookies.json 持久化可复用）。
- **播放器/下载面板不做**：注入 JS 只负责"数据桥"（WS 往返），不负责页内 UI。
- **待拍板：微信客户端内嵌页面场景**是否要支持——若支持则需 mitmproxy local（WinDivert 驱动）+ 系统级证书，与"纯用户态"目标冲突，建议二期评估。

**验收细则**：
1. 已登录浏览器（CDP）→ 注入 JS 桥 → B5 WS 服务收到连接 → `api_call` 往返成功（fetch 出真实 feed 数据）。
2. 注入 JS 不改变页面原有行为（无 UI 注入、无 DOM 干扰）。
3. 断线重连：WS 断开 → 自动重连 + 未完成请求按 id 重发（对齐上游 requests map 语义）。
4. 验证命令：`python -m unittest core.protocol.tests.test_browser_bridge` + 手动 CDP 冒烟。
5. 端到端：CDP 注入 → B5 fetch → B10 门面 → B3 下载解密落盘（标"待 B5/B10 完成后联调"）。
6. **用户路径无感（v0.17 澄清固化）**：用户操作与原产品完全一致——微信扫码登录一次 → 软件内嵌窗口打开视频号页面 → 搜索/翻视频/点下载均正常；唯一差异=流量仅走 WebView2 单实例代理（用户不可感知），不得引入任何额外登录/授权/操作步骤。
7. **理论 100% 实测证据（v0.17 最小测试 PASS，2026-10-29）**：
   - 脚本：`scripts_probe_webview2_proxy.py`（起本地代理 2023 → Edge 带 `--proxy-server` 打开测试页 → 验证流量导向+系统代理未动），可重复运行。
   - 结果（实测）：22 条请求全部到达本地代理（含 Edge 后台流量 + `GET http://neverssl.com/` 测试目标页完整闭环）；系统代理注册表 ProxyEnable 前后一致（未被动）。**单实例 `--proxy-server` 机制实测可行，WebView2 同内核（Chromium），B11 主方案理论 100% 确认。**
   - **微信代理独立性（查证）**：微信 PC 版代理设置三选一（使用系统代理/使用手动代理/不使用代理）——**上游系统代理方案依赖"用户微信选使用系统代理"，用户改手动/不代理则上游失效**；本方案 WebView2 自有 `--proxy-server` 参数，**不依赖微信客户端代理设置，微信怎么配都不影响**。上游被微信设置牵制，本方案独立——额外优势。

**工作量**：2 个子块（CDP 注入器 + 注入 JS 桥翻写），1.5-2 天。

### B7 下载任务状态机——L4（执行级，2026-10-29 落档）

**上游源码**：`internal/services/download_task.go`（115.9KB，状态机核心）+ `handler_download_task_ws.go`（26.4KB，WS 进度推送）+ `internal/database/model/download_task.go`（状态枚举）。

**定位（重申）**：**不整块翻写**——号匣主线已有 **YZPQ-307 状态机设计**（PingCode 票 id=6ae2c04b02e3c5c7ad768200，8 态：pending/downloading/paused/completed/failed/cancelled/interrupted/expired）。B7 产出 = **差异比对报告 + YZPQ-307 补充项**，用上游实现校验号匣设计闭环性。

**上游状态枚举（实锤，model/download_task.go:10-19）**：

| 值 | 上游态 | 号匣 YZPQ-307 | 差异判定 |
|---|---|---|---|
| 0 | Waiting | pending | 仅命名不同，语义一致 |
| 1 | Preparing | —（无此态） | 上游有、号匣无：号匣直链单文件下载无"准备"独立阶段 |
| 2 | Downloading | downloading | 一致 |
| 3 | Paused | paused | 一致 |
| 4 | Merging | —（无此态） | 上游有、号匣无：分段合并是 gopeed 多段下载产物，号匣单流直链无合并 |
| 5 | Finished | completed | 仅命名不同 |
| 6 | Failed | failed | 一致 |
| 7 | Cancelled | cancelled | 一致 |
| — | — | interrupted | **号匣有、上游无**：本地应用单实例锁 + 优雅退出落 interrupted（YZPQ-312）；上游常驻服务无需此态 |
| — | — | expired | **号匣有、上游无**：直链 TTL 过期（实测约 10 天）；上游下载中 403 直接刷新重试、无独立态 |

**上游操作约束（实锤，download_task.go）**：
- `StartTask(1077)`：仅 Waiting/Paused/Failed 可启动（1087-1090）→ Preparing(1101)。
- `PauseTask(1106)`：仅 Preparing/Downloading 可暂停（1116-1117）→ Paused(1140)；**直播收尾检查**（1127-1132）：直播录制收尾后状态非 Finished → 报错不暂停。
- `ResumeTask(1145)`：仅 Paused 可恢复（1155-1156）→ Preparing(1166)。
- `RetryTask(1172)`：仅 Failed/Cancelled 可重试（1184-1185）→ Waiting(1196) → Preparing(1203)。
- `CancelTask(1209)` / `DeleteTask(1220)` / `StartAllTasks(1307)` / `PauseAllTasks(1345)`。
- **去重阻塞状态** `duplicate_blocking_task_statuses`（185-190）：Waiting/Preparing/Downloading/Paused/Merging —— 同一 unique_id 已有这些状态 → `DuplicateTaskError` 不新建（幂等锁语义）。

**WS 进度推送（handler_download_task_ws.go 26.4KB）**：上游 Go 服务经 `ws://127.0.0.1:2022/ws/downloader` 推 `type=event / batch_tasks` 进度。**号匣不翻写 WS**：号匣 Python 后端直连前端，进度走既有 SSE 通道（`task_progress` 事件，Spec.md §SSE + `core/api/routers/sse.py`）——WS 是上游"常驻服务→前端"架构的产物，号匣无此拓扑。

**差异比对结论（B7 核心产出）**：
1. **上游 Preparing/Merging 两态号匣不要**：直链单文件下载 + Python 内嵌解密，无独立准备阶段、无分段合并——号匣 `downloading` 覆盖。
2. **号匣 interrupted/expired 两态是必要增强**（上游没有）：
   - `interrupted`：单实例锁 + 优雅退出（YZPQ-312），进程被杀/退出落 interrupted，重启后校验续传或删除。
   - `expired`：直链 TTL 过期（L3 链接列，实测 10 天量级）——承接"链接失效但任务未完成"语义，触发 `ensure_valid_url` 刷新（Spec.md:527 下载中 403 → 刷新重试）。
3. **幂等锁对齐**：号匣 Spec.md:642"同一 video_id 已有 running 任务 → 返回现有任务"与上游 duplicate_blocking 语义一致——**差异：上游按 unique_id，号匣按 video_id**；B4 已对齐 video_id=object_id（64 位大整数字符串），需确认号匣任务去重键唯一性。
4. **两层衔接**：Spec.md:635-638 下载入口三态（is_downloaded 0/1 + 文件有效性）是**前端/入口层**；B7 状态机是**后端任务层**——两层通过 download_tasks 表状态互查衔接，不混层。

**落点/接入点**：
- 号匣 `core/service/task.py`（现状走 create2 链路）——B3 落地后下载执行器切 `core/service/downloader.py`（Spec.md:630-631），8 态流转 + 落库 `download_tasks`（表结构不动，Spec.md:685）。
- `resume_states` 表承接断点续传（YZPQ-308，Range 续传 + .part + Content-Length 字节对齐）。
- 前端 SSE `task_progress` 已存在，无新增通道。

**风险/决策点**：
- **interrupted vs paused 恢复路径不同**：paused=用户主动暂停→直接续传；interrupted=异常中断→恢复前先校验 .part 完整性 + 直链新鲜度（可能需刷新），不混同。
- **expired 防死循环**：下载中 403/404 → 转 expired → ensure_valid_url 刷新（B4/L3 链接列）→ 成功回 downloading / 失败 → failed。**刷新重试次数上限 = 1 次**，超过即 failed（防无限循环）。
- **直播任务收尾检查**（上游 1127-1132）：号匣直播回放下载收尾后状态校验——保留。
- **CancelTask 的 .part 清理**：取消后删除未完成 .part 或标记续传候选——由 YZPQ-308 定，B7 只定义 cancelled 终态语义。

**验收细则**：
1. 8 态全量转换矩阵单测：合法迁移全过、非法迁移全拒（如 completed 后再 Start → 拒绝）。
2. 幂等锁：同一 video_id 并发创建 → 仅 1 个任务（对齐上游 DuplicateTaskError 语义）。
3. interrupted 模拟：杀进程重启 → 落 interrupted → 恢复校验续传。
4. expired 模拟：下载中 mock HTTP 403 → 刷新 1 次成功 → 回 downloading；刷新失败 → failed。
5. 验证命令：`python -m unittest core.service.tests.test_task_state_machine`。
6. **差异报告落档**：`docs/B7状态机差异报告.md`（上游 8 态 ↔ 号匣 8 态映射表 + 决策理由），并向 YZPQ-307 票补充本报告摘要。

**工作量**：差异报告 0.5 天 + 状态机实现（8 态流转 + 落库 + 单测）1-2 天（归 YZPQ-307，号匣主线）。

## 三、弃用边界（明确不做，防缺漏假象）

| 上游模块 | 理由 |
|---|---|
| internal/interceptor（Sunny MITM 代理实现） | **弃 MITM 具体实现**，注入逻辑已在 B6（接口清单）/B11（CDP 投放+JS 桥）翻写——零成本版用浏览器自动化注入，不装证书不挂代理 |
| pkg/certificate（根证书生成/安装） | 无 MITM 即无证书需求（CDP 注入免证书） |
| frontend/inject 的 UI 部分（model.js/view.js/panel.js/components.js 219KB） | 号匣自研 WebView2 前端覆盖 UI；**注入 JS 本体（ws/events/utils 桥）由 B11 翻写** |
| internal/workers（Cloudflare worker） | 部署层，号匣本地应用不需要 |

## 四、执行纪律

- 严格依赖序：B1→B2→B3 硬链；B4/B9 可并行；B5/B8 等 B4+B9；B6 独立；B7 等 B3。
- 每块独立验收；上层验收包含下层已过。
- 翻写代码禁止上游版权标识/原注释/变量名照抄（全新命名）。
- 上游源码仅在 research/ 参考，不入主代码路径。
- 新增许可证依赖（ffmpeg）登记《开源依赖合规约束.md》。

## 五、待办（按依赖序，全部落 wechat-downloader 分支 core/）

- [ ] **B1** 解密核心生产化：算法已验证 → 升格 `core/decrypt/isaac64.py` + 微信视频号下载链路本地解密（L0，首块）
- [ ] **B4** 数据结构（与 B1 并行）
- [ ] **B9** Cookie 支撑（并行）
- [ ] **B2** 流式 Reader（依赖 B1）
- [ ] **B3** 解密服务（依赖 B1+B2）
- [ ] **B5** API 客户端（依赖 B4+B9）
- [ ] **B8** 元宝解析器（独立）
- [ ] **B6** JS 逆向接口清单（独立）
- [ ] **B11** 浏览器注入桥（依赖 B5；CDP 注入 + JS 桥翻写）
- [ ] **B10** 业务适配门面（依赖 B3+B5）
- [ ] **B7** 状态机差异比对（依赖 B3）
- [ ] 评估项：content/data_query、scraper_job、cache、events/hermes、database-model 对照（不阻塞，深入时再看）
- [ ] 配套：`core/api/app.py`/`base_service.py` 中微信视频号 exe 启停逻辑移除（随 B1/B7 渐进）
