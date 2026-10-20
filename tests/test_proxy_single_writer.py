"""系统代理单一写者断言（防冲突回归）

拓扑事实（2026-10-21 代码审查 + Go config.yaml 证据）：
- 系统代理注册表 ProxyServer 的唯一写者 = core/utils/res_download_service.py
  （open_proxy → /api/proxy-open 或回退 _set_proxy_registry 写 127.0.0.1:8899）
- Go 黑盒 config.yaml proxy.system: false → 不自写系统代理
- 2022 = Go HTTP API（Python 直连 127.0.0.1:2022，不走系统代理）
- 2023 = res_download 的 UpstreamProxy 目标（内部注入，非系统代理）

本测试静态断言：全仓库只有 res_download_service.py 一处写 ProxyServer 注册表，
防止未来新增第二个写者（如 Go 侧自开代理、前端直写注册表）造成系统代理冲突。
"""
import os
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
# 排除：测试自身、dist 打包产物、docs 源码参考
EXCLUDE = {"tests", "dist", "docs", ".git", ".codex", ".gemini", "__pycache__", "tools"}


def _py_files():
    """os.walk 剪枝遍历（rglob 会无谓遍历 dist 等大目录，慢 200s）"""
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in EXCLUDE]
        for name in files:
            if name.endswith(".py"):
                full = Path(root) / name
                yield full.relative_to(REPO), full


def test_system_proxy_writer_only_in_res_download_service():
    """ProxyServer 的注册表写入只能出现在 res_download_service.py"""
    writers = []
    for rel, path in _py_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        if '"ProxyServer"' in text and ("SetValueEx" in text or "SetValueEx" in text.replace(" ", "")):
            writers.append(str(rel))
    assert writers == ["core\\utils\\res_download_service.py"] or \
        writers == ["core/utils/res_download_service.py"], \
        f"系统代理写者漂移！除 res_download_service 外还有: {writers}"


def test_go_proxy_system_disabled_in_config():
    """Go 黑盒 config.yaml 必须保持 proxy.system: false（不自写系统代理）"""
    cfg = REPO / "weixin_exe" / "config.yaml"
    assert cfg.exists(), "weixin_exe/config.yaml 缺失"
    text = cfg.read_text(encoding="utf-8", errors="replace")
    # proxy: 块内 system: false（非 pagespy/system 等误匹配）
    idx = text.find("proxy:")
    assert idx != -1, "config.yaml 无 proxy 段"
    block = text[idx:idx + 200]
    assert "system: false" in block, (
        f"Go config.yaml proxy.system 不再是 false！若 Go 黑盒改为自写系统代理，"
        f"将与 res_download(8899) 冲突，需评估链路拓扑。当前 proxy 段: {block}")


def test_no_second_registry_proxy_writer():
    """注册表 ProxyEnable 写入同样只允许 res_download_service.py（含关闭）"""
    writers = []
    for rel, path in _py_files():
        text = path.read_text(encoding="utf-8", errors="replace")
        if "ProxyEnable" in text and "SetValueEx" in text:
            writers.append(str(rel))
    assert writers == ["core\\utils\\res_download_service.py"] or \
        writers == ["core/utils/res_download_service.py"], \
        f"ProxyEnable 写者漂移: {writers}"
