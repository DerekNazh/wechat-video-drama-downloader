"""
打包脚本 - 视频号监控控制台

用法:
  python build.py                      打包，版本不变，输出带时间戳命名
  python build.py --version            打包 + patch 递增（1.0.0 → 1.0.1）
  python build.py --version 2.0.0      打包 + 指定版本
  python build.py clean                清理 dist/build

产物命名: 视频号监控控制台_版本_日期_时间
"""
import re
import sys
import shutil
import zipfile
import subprocess
import logging
import tempfile
from datetime import datetime
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)

ROOT = Path(__file__).parent.resolve()
SPEC_FILE = ROOT / "video_download.spec"
DIST_DIR = ROOT / "dist" / "视频号监控控制台"
ENV_FILE = ROOT / "config" / ".env"
PRODUCT_NAME = "视频号监控控制台"

# 打包后需要复制到根目录的文件/目录
BUNDLE_FILES = {
    ROOT / "config" / ".env": DIST_DIR / ".env",
    ROOT / "weixin_exe" / "config.yaml": DIST_DIR / "lib" / "config.yaml",
    ROOT / "weixin_exe" / "wx_video_download.exe": DIST_DIR / "lib" / "wx_video_download.exe",
    ROOT / "weixin_exe" / "gopeed.db": DIST_DIR / "lib" / "gopeed.db",
    ROOT / "static": DIST_DIR / "static",
}

# WebView2 Bootstrapper（约 2MB，用于客户机未安装 WebView2 时引导安装）
WEBVIEW2_BOOTSTRAPPER_URL = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"
WEBVIEW2_BOOTSTRAPPER_FILE = ROOT / "lib" / "MicrosoftEdgeWebview2Setup.exe"


def _read_version() -> str:
    """从 .env 读取 PROJECT_VERSION"""
    if not ENV_FILE.exists():
        return "0.0.0"
    content = ENV_FILE.read_text(encoding="utf-8")
    m = re.search(r"^PROJECT_VERSION=(.+)$", content, re.MULTILINE)
    return m.group(1).strip() if m else "0.0.0"


def _write_version(version: str):
    """将 PROJECT_VERSION 写回 .env"""
    content = ENV_FILE.read_text(encoding="utf-8")
    content = re.sub(
        r"^PROJECT_VERSION=.*$",
        f"PROJECT_VERSION={version}",
        content,
        flags=re.MULTILINE,
    )
    ENV_FILE.write_text(content, encoding="utf-8")
    logger.info(f"版本已更新: {version}")


def _bump_version(target: str | None) -> str:
    """递增版本号并写回 .env

    Args:
        target: None = patch 递增, "x.y.z" = 指定版本
    Returns:
        新版本号
    """
    current = _read_version()
    if target:
        _write_version(target)
        return target

    parts = current.split(".")
    while len(parts) < 3:
        parts.append("0")
    parts[2] = str(int(parts[2]) + 1)
    new_version = ".".join(parts)
    _write_version(new_version)
    return new_version


def exec_cmd(cmd: list[str]) -> None:
    print(f"\n>>> {' '.join(str(c) for c in cmd)}")
    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        sys.exit(1)


def clean() -> None:
    for p in ["dist", "build"]:
        path = ROOT / p
        if path.exists():
            shutil.rmtree(path)
            print(f"已删除: {path}")


def backup_user_data():
    """备份 dist 中的用户数据目录（仅 logs，运行时数据不备份）"""
    backed_up = {}
    for name in ["logs"]:
        src = DIST_DIR / name
        if src.exists():
            tmp = Path(tempfile.mkdtemp(prefix=f"backup_{name}_"))
            shutil.copytree(src, tmp / name, dirs_exist_ok=True)
            backed_up[name] = tmp
            logger.info(f"  备份: {name}/ -> {tmp.name}")
    return backed_up


def restore_user_data(backed_up):
    """恢复用户数据到 dist"""
    for name, tmp in backed_up.items():
        dst = DIST_DIR / name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(tmp / name, dst)
        logger.info(f"  恢复: {name}/")
        shutil.rmtree(tmp, ignore_errors=True)


def _rename_dist(version: str) -> Path:
    """将 dist/视频号监控控制台 重命名为 视频号监控控制台_版本_日期_时间"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder_name = f"{PRODUCT_NAME}_{version}_{timestamp}"
    new_path = ROOT / "dist" / folder_name

    if DIST_DIR.exists():
        DIST_DIR.rename(new_path)
        logger.info(f"产物已重命名: {folder_name}/")

    return new_path


def _make_zip(dist_path: Path):
    """将 dist_path 打包为同名 .zip"""
    zip_path = Path(str(dist_path) + ".zip")
    logger.info(f"正在打包 zip: {zip_path.name}...")
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file in dist_path.rglob("*"):
            if file.is_file():
                arcname = file.relative_to(dist_path.parent)
                zf.write(file, arcname)
    mb = zip_path.stat().st_size / 1024 / 1024
    logger.info(f"zip 已生成: {zip_path.name} ({mb:.1f} MB)")


def _ensure_webview2_bootstrapper():
    """确保 WebView2 Bootstrapper 已下载并复制到打包目录"""
    import urllib.request

    dst = DIST_DIR / "lib" / "MicrosoftEdgeWebview2Setup.exe"

    if WEBVIEW2_BOOTSTRAPPER_FILE.exists():
        logger.info(f"WebView2 Bootstrapper 已存在: {WEBVIEW2_BOOTSTRAPPER_FILE}")
    else:
        logger.info("下载 WebView2 Bootstrapper...")
        WEBVIEW2_BOOTSTRAPPER_FILE.parent.mkdir(parents=True, exist_ok=True)
        try:
            urllib.request.urlretrieve(WEBVIEW2_BOOTSTRAPPER_URL, str(WEBVIEW2_BOOTSTRAPPER_FILE))
            logger.info(f"已下载: {WEBVIEW2_BOOTSTRAPPER_FILE.name}")
        except Exception as e:
            logger.warning(f"WebView2 Bootstrapper 下载失败: {e}")
            logger.warning("客户机如果没有 WebView2 Runtime 可能无法正常使用")
            return

    # 复制到 dist
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(WEBVIEW2_BOOTSTRAPPER_FILE, dst)
    logger.info(f"已复制: {dst.name}")


def build(bump_target: str | None = None) -> None:
    version = _read_version()

    if bump_target is not None:
        version = _bump_version(bump_target if bump_target else None)
        logger.info(f"版本递增: {_read_version()}")
    else:
        logger.info(f"当前版本: {version}")

    print("\n=== 构建开始 ===")

    # 检查 pyinstaller
    pyinstaller_exe = ROOT / ".venv" / "Scripts" / "pyinstaller.exe"
    if not pyinstaller_exe.exists():
        print("[ERROR] PyInstaller 未安装，请先运行: .venv\\Scripts\\pip install pyinstaller")
        sys.exit(1)

    if not SPEC_FILE.exists():
        print(f"[ERROR] Spec 文件不存在: {SPEC_FILE}")
        sys.exit(1)

    wx_exe_src = ROOT / "weixin_exe" / "wx_video_download.exe"
    if not wx_exe_src.exists():
        print(f"[ERROR] Go 后端未找到: {wx_exe_src}")
        sys.exit(1)

    # 备份旧数据
    logger.info("备份用户数据...")
    backed_up = backup_user_data()
    if not backed_up:
        logger.info("  无旧数据")

    # 打包
    logger.info("\nPyInstaller 打包中...")
    exec_cmd([str(pyinstaller_exe), str(SPEC_FILE), "--noconfirm"])

    # 复制所有文件到 dist
    for src, dst in BUNDLE_FILES.items():
        if not src.exists():
            logger.warning(f"跳过（不存在）: {src}")
            continue
        if src.is_dir():
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
            logger.info(f"已复制: {src.name}/")
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dst)
            logger.info(f"已复制: {src.name}")

    # 恢复用户数据
    if backed_up:
        logger.info("\n恢复用户数据...")
        restore_user_data(backed_up)

    # WebView2 Bootstrapper
    _ensure_webview2_bootstrapper()

    # 重命名 + 打 zip
    dist_path = _rename_dist(version)
    _make_zip(dist_path)

    # 输出
    exe_path = dist_path / "视频号监控控制台.exe"
    if exe_path.exists():
        mb = exe_path.stat().st_size / 1024 / 1024
        logger.info(f"\n=== 构建完成 ===")
        logger.info(f"版本:   {version}")
        logger.info(f"目录:   {dist_path}")
        logger.info(f"ZIP:    {str(dist_path) + '.zip'}")
        logger.info(f"EXE:    {mb:.1f} MB")


def _parse_args():
    """解析命令行参数"""
    args = sys.argv[1:]

    if not args:
        return "build", None

    if args[0].lower() == "clean":
        return "clean", None

    if args[0] == "--version":
        target = args[1] if len(args) > 1 else None
        return "build", target

    print(f"用法: python build.py [--version [x.y.z]] | clean")
    sys.exit(1)


if __name__ == "__main__":
    action, bump_target = _parse_args()
    if action == "clean":
        clean()
    else:
        build(bump_target)
