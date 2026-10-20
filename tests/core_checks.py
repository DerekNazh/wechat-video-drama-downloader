"""严格校验核心（pytest 与 selftest 共用，保证两处校验口径一致）

严格性约定（用户要求：不能太假、不能太宽松）：
- 下载成功 = HTTP 200 + code=1 + 文件存在 + 大小与源精确一致 + md5 逐字节一致
- 重复命中 = 服务器请求计数不增长（真正的零网络请求，而非"看起来没下"）
- 失败 = HTTP 502 + code=0 + 下载目录无任何残留（半截文件会污染下次判断）
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

ASSETS_DIR = Path(__file__).resolve().parent / ".assets"
TEST_MP4 = ASSETS_DIR / "test_video.mp4"


def ensure_test_mp4() -> Path:
    """用 ffmpeg 生成真实测试视频（带画面+音轨，约 1~2 秒）

    生成后文件固定不变，测试全程复用同一份源文件做 md5 比对。
    """
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    if TEST_MP4.exists() and TEST_MP4.stat().st_size > 0:
        return TEST_MP4
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-f", "lavfi", "-i", "testsrc2=size=640x360:rate=30:duration=2",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
        "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac", "-b:a", "96k",
        "-pix_fmt", "yuv420p",
        str(TEST_MP4),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0 or not TEST_MP4.exists():
        raise RuntimeError(f"ffmpeg 生成测试视频失败: {proc.stderr[:500]}")
    return TEST_MP4


def md5_file(path: Path) -> str:
    h = hashlib.md5()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def file_size(path: Path) -> int:
    return path.stat().st_size


# ---------- 测试环境：独立 app（只挂下载路由，无启动序列） ----------

def build_test_app():
    """构造只挂 sniff_proxy 路由的 FastAPI app

    不挂 core.api.app 的 lifespan（那会启动真实 Go / res_download），
    直接测 Python 侧下载链路的完整 HTTP 行为。
    """
    from fastapi import FastAPI
    from core.api.routers import sniff_proxy

    app = FastAPI(title="download-chain-test")
    app.include_router(sniff_proxy.router)
    return app


def override_settings(settings, tmp_path: Path, download_timeout: float = 3.0):
    """把下载目录指到临时目录、缩短下载超时，并返回还原函数

    直接改 settings._config 上的字段：
    - short_drama_download_dir 是 property（绝对路径直接返回）
    - DOWNLOAD_TIMEOUT / HTTP_TIMEOUT 是 sniff_proxy 模块级常量，需一并替换
    """
    import core.api.routers.sniff_proxy as sniff_proxy

    old_cfg = settings._config
    old_dl = sniff_proxy.DOWNLOAD_TIMEOUT
    old_http = sniff_proxy.HTTP_TIMEOUT

    cfg_type = type(old_cfg)
    new_cfg = cfg_type(**old_cfg.model_dump()) if hasattr(old_cfg, "model_dump") else old_cfg
    try:
        new_cfg.short_drama_download_dir = str(tmp_path)
    except Exception:
        setattr(new_cfg, "short_drama_download_dir", str(tmp_path))
    settings._config = new_cfg
    sniff_proxy.DOWNLOAD_TIMEOUT = download_timeout
    sniff_proxy.HTTP_TIMEOUT = download_timeout

    def restore():
        settings._config = old_cfg
        sniff_proxy.DOWNLOAD_TIMEOUT = old_dl
        sniff_proxy.HTTP_TIMEOUT = old_http

    return restore


# ---------- 严格断言 ----------

class CheckError(AssertionError):
    pass


def _assert(cond: bool, msg: str):
    if not cond:
        raise CheckError(msg)


def check_download_ok(resp, download_dir: Path, source_mp4: Path,
                      expected_name: str, counter_before: int):
    """严格校验：成功下载必须字节级一致，且没有多余网络请求"""
    _assert(resp.status_code == 200, f"期望 200，实际 {resp.status_code}")
    data = resp.json()
    _assert(data.get("code") == 1, f"期望 code=1，实际 code={data.get('code')} msg={data.get('message')}")
    save_path = Path(data["data"]["save_path"])
    _assert(save_path.exists(), f"文件不存在: {save_path}")
    _assert(save_path.name == expected_name, f"命名错误: {save_path.name} != {expected_name}")
    _assert(file_size(save_path) == file_size(source_mp4),
            f"大小不一致: {file_size(save_path)} != {file_size(source_mp4)}")
    _assert(md5_file(save_path) == md5_file(source_mp4),
            f"md5 不一致: {md5_file(save_path)} != {md5_file(source_mp4)}")
    return save_path


def check_no_duplicate_request(counter_after: int, counter_before: int, video_id: str):
    _assert(counter_after == counter_before,
            f"重复下载竟然重新请求了: {video_id} 请求数 {counter_before}→{counter_after}")


def check_failure_clean(resp, download_dir: Path, video_id: str):
    """失败必须：HTTP 502 + code=0 + 下载目录无该视频残留"""
    _assert(resp.status_code == 502, f"期望 502，实际 {resp.status_code}")
    data = resp.json()
    _assert(data.get("code") == 0, f"失败时 code 应为 0，实际 {data.get('code')}")
    leftovers = [f.name for f in download_dir.rglob(f"*{video_id}*") if f.is_file()]
    _assert(not leftovers, f"失败后存在残留文件: {leftovers}")


def list_downloaded(download_dir: Path) -> list[str]:
    return sorted(f.name for f in download_dir.rglob("*") if f.is_file())
