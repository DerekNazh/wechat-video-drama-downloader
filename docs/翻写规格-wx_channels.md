# 翻写规格：wx_channels_download → wechat-downloader 自研（微信视频号域）

> 状态：v0.8 B2/B3 执行级 · 2026-10-29（解密链 B1-B3 全部落执行级，逐块深入推进中）
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

### B4 数据结构——L0（与 B1 并行）
- types.go 全量模型（feed/作者/直播/评论 30.7KB）+ util.go。
- 产出 `core/models/wxchannels.py`（Pydantic，对齐号匣 DB 表）。

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

## 五、待办（按依赖序，全部落 wechat-downloader 分支 core/）

- [ ] **B1** 解密核心生产化：算法已验证 → 升格 `core/decrypt/isaac64.py` + 微信视频号下载链路本地解密（L0，首块）
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
- [ ] 配套：`core/api/app.py`/`base_service.py` 中微信视频号 exe 启停逻辑移除（随 B1/B7 渐进）
