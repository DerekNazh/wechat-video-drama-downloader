# 翻写规格：wx_channels_download → 号匣/legacy 自研（微信视频号域）

> 状态：v0.1 草稿 · 2026-10-29
> 目的：把 `research/wx_channels_download`（MIT+Commons Clause，禁 Sell）微信视频号核心逻辑**按块翻写为自有代码**（参考逻辑、不复制源码），供 legacy 分支自研版使用。
> 合规铁律：只读参考**逻辑/算法/协议**，禁止整文件复制进主代码；翻写代码为全新实现，不受 Commons Clause 约束。
> 源码位置：`D:\setup_temp\剪辑合成拆散\新_二合一总下载器\research\wx_channels_download\`

## 一、拆块总览（逐块消化，块间无耦合）

| 块 | 名称 | 上游源码 | 翻写产出（自有代码） | 优先级 |
|---|---|---|---|---|
| B1 | 解密核心（ISAAC-64） | `pkg/scraper/wxchannels/decrypt.go`（171行） | `core/decrypt/isaac64.py` | P0 |
| B2 | 流式解密 Reader | `pkg/scraper/wxchannels/reader.go`（74行） | `core/decrypt/decrypt_reader.py` | P0 |
| B3 | 解密服务（HTTP 流/断点/转码） | `pkg/scraper/wxchannels/decryptor.go`（378行） | `core/decrypt/decrypt_service.py` | P0 |
| B4 | 数据结构（视频号模型） | `pkg/scraper/wxchannels/types.go`（30.7KB） | `core/models/wxchannels.py` | P1 |
| B5 | API 客户端（请求/WS 协议） | `pkg/scraper/wxchannels/client.go`（15.1KB） | `core/api/wxchannels_client.py` | P1 |
| B6 | 拦截器（代理/注入协议） | `pkg/scraper/wxchannels/interceptor.go`（24.6KB） | `core/protocol/wxchannels_interceptor.py`（仅协议参考） | P2 |
| B7 | 下载任务管理（状态机） | `internal/services/download_task.go`（115.9KB）+ `internal/api/handler_download_task.go`（60.4KB） | 对齐 master 号匣 YZPQ-307 状态机 | P2 |

> 说明：B1–B3 解密链路是核心价值（微信视频号加密视频唯一硬能力）；B4–B5 数据/客户端；B6 拦截器在号匣纯 API 架构下**弃用注入/代理**，但**其抓包得到的接口协议**值得参考；B7 与号匣已有设计重叠，对齐即可。

## 二、B1 解密核心（ISAAC-64）——首块

**上游逻辑要点**（decrypt.go 逐行读毕）：
- ISAAC-64 keystream 生成：`CreateISAacInst(key)` → `rand64Init`（256 状态，golden=0x9e3779b97f4a7c13 常量，4+2 轮 mix）→ `isAAC64`（每轮 256 步，AA/BB/CC 演进）→ `ISAacRandom()` 取 8 字节大端。
- `DecryptData(data, encLen, key)`：从偏移 0 起，每 8 字节 XOR 一个 keystream 块，encLen 为加密区长度（**只有前 encLen 字节加密**）。
- 关键参数：`key` = decode_key（uint64，视频号解密密钥），`encLen` = 加密区长度（实测 = 视频文件前若干 KB，对应号匣 L3 年龄窗口）。

**与号匣已有实现的对照**：
- master 号匣已有 Python 内嵌解密（ISAAC-64 + 前 128KB XOR，v1.70 端到端实测通过，参考 Evil0ctal 仓库 CLI）→ **B1 翻写 = 逐行对照验证**：确认号匣 Python 版与上游 Go 版算法等价（keystream 序列一致）。
- 验证方法：同一 key + 同一加密文件 → 两边解密结果逐字节一致。

**验收标准**：
1. `core/decrypt/isaac64.py` 存在，纯 Python 实现，无外部依赖；
2. 与上游 Go `decrypt.go` 对照：同一 encKey 生成的前 8 个 keystream 值一致；
3. 用实测视频文件解密，输出可播放。

## 三、B2 流式解密 Reader——次块

**上游逻辑要点**（reader.go 逐行读毕）：
- `NewDecryptReader(reader, key, offset, limit)`：**支持断点偏移**——offset>0 时预跳过 `offset/8` 个完整块，再从 `offset%8` 续解；limit=加密区长度，超出部分不解。
- `Read(p)`：逐字节 XOR，keystream 位置 `ksPos` 8 字节一轮，`consumed` 计数限制解密区。
- 核心价值：**边下边解 + 断点续传解密**（HTTP Range 对齐）。

**翻写产出**：`core/decrypt/decrypt_reader.py` —— 流式 XOR Reader（Generator/回调式，适配 Python `requests`/`httpx` 流）。

**验收标准**：同一加密文件，offset=0 全量解 vs offset=1024 断点解 → 拼接结果一致。

## 四、B3 解密服务——HTTP 流/断点/转码

**上游逻辑要点**（decryptor.go 逐行读毕）：
- `DecryptOnly`：代理请求→解析 `Content-Range` 得 startOffset→`NewDecryptReader(body, key, startOffset, encLimit)`→透传 header（Content-Type/Accept-Ranges）→`io.Copy` 流式输出。
- `ConvertWithDecrypt`：解密流接 **ffmpeg** 转 mp3（`-vn -acodec libmp3lame -ab 192k`）——注意：这是**音频转码**场景（视频号音频提取）。
- `DecryptFile`：本地文件解密落地。
- 设计要点：**解密与下载解耦**（解密是 HTTP 中间层），支持 HEAD 探测、Range 断点、状态码透传。

**翻写产出**：`core/decrypt/decrypt_service.py` —— 解密中间层（FastAPI 路由或纯函数：download+decrypt 流式管道；如需 mp3 转码则对接 ffmpeg CLI）。

**验收标准**：本地起服务，对加密直链发起 Range 请求→返回已解密字节流；断点续传正确。

## 五、执行纪律

- 每块独立完成、独立验收，**块间不阻塞**（B1→B2→B3 有先后，其余并行）。
- 翻写代码**禁止**出现上游版权标识/原注释/变量名照抄（全新命名）。
- 上游源码仅在 `research/` 目录参考，不入主代码路径。
- 新增许可证依赖（如 ffmpeg）另行登记《开源依赖合规约束.md》。

## 六、待办

- [ ] B1 解密核心对照验证（首个执行块）
- [ ] B2 流式 Reader
- [ ] B3 解密服务
- [ ] B4 数据模型抽取
- [ ] B5 客户端协议
- [ ] B6 拦截器协议参考（不实现注入）
- [ ] B7 任务状态机对齐号匣
