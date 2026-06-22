"""
初始化模块 - 视频标题生成
负责系统初始化、检测和日志设置

使用方式：
    from config import init_checker

    # 添加检测项
    @init_checker.register("检测名", critical=False)
    def my_check():
        return True, "检测通过"
"""
import os
import sys
import io
import json
import logging
from pathlib import Path
from typing import List, Dict

from config.settings import settings


# ==================== 初始化检测类 ====================
class InitializerChecker:
    """初始化检测器 - 启动时检查系统状态

    错误等级（三种）：
    - warning: 检测失败 → 记录黄色警告日志，不阻止运行
    - error:   检测失败 → 记录红色错误日志，不阻止运行
    - critical: 检测失败 → 记录红色错误日志，**直接退出应用**

    使用示例：
        checker = InitializerChecker()

        @checker.register("FFmpeg 可用性", level="critical")
        def check_ffmpeg():
            if not Path("ffmpeg.exe").exists():
                return False, "FFmpeg 不存在"
            return True, "FFmpeg 可用"
    """

    def __init__(self):
        self.checks: List[Dict] = []

    def register(self, name: str, level: str = "warning"):
        """注册检测项（装饰器）

        Args:
            name: 检测项名称
            level: 错误等级 ("warning" | "error" | "critical")
                - warning:   失败 → 黄色日志，不阻止运行
                - error:     失败 → 红色日志，不阻止运行
                - critical:  失败 → 红色日志，**退出应用**

        Returns:
            装饰器函数

        检测函数签名：
            def check_func() -> tuple[bool, str]
            返回: (是否成功, 消息)
        """
        if level not in ["warning", "error", "critical"]:
            raise ValueError(f"错误等级必须是 'warning'、'error'、'critical'，当前值: {level}")

        def decorator(func):
            self.checks.append({
                "name": name,
                "func": func,
                "level": level
            })
            return func
        return decorator

    def run_all(self) -> Dict[str, any]:
        """执行所有检测

        三级响应机制：
        - warning:  失败 → 黄色警告，继续
        - error:   失败 → 红色错误，继续
        - critical: 失败 → 红色错误，**抛出异常退出**

        Returns:
            检测结果字典
            {
                "total": 总数,
                "passed": 通过数,
                "failed": 失败数,
                "critical_failed": critical 级别的失败数,
                "results": [...]
            }
        """
        results = []
        passed = 0
        failed = 0
        critical_failed = 0

        for check in self.checks:
            name = check["name"]
            func = check["func"]
            level = check["level"]

            try:
                success, message = func()
                passed += success
                failed += not success
                if not success and level == "critical":
                    critical_failed += 1

                results.append({
                    "name": name,
                    "passed": success,
                    "message": message,
                    "level": level
                })

                # 日志输出
                logger = logging.getLogger(__name__)
                if success:
                    logger.info(f"[✓] {name}: {message}")
                else:
                    if level == "warning":
                        logger.warning(f"[✗] {name}: {message}")
                    elif level == "error":
                        logger.error(f"[✗] {name}: {message}")
                    elif level == "critical":
                        logger.error(f"[✗] {name}: {message} (致命)")

            except Exception as e:
                failed += 1
                if level == "critical":
                    critical_failed += 1
                results.append({
                    "name": name,
                    "passed": False,
                    "message": f"检测异常: {e}",
                    "level": level
                })
                logging.getLogger(__name__).error(f"[✗] {name}: 检测异常 - {e}")

        # 汇总日志
        summary = f"初始化检测完成: {passed}/{len(self.checks)} 通过"
        logger = logging.getLogger(__name__)

        if critical_failed > 0:
            logger.error(f"[致命错误] {summary}，{critical_failed} 个致命检测失败")
            # critical 失败 → 直接退出
            raise SystemExit(1)
        elif failed > 0:
            logger.warning(f"[有警告] {summary}")
        else:
            logger.info(f"[全部通过] {summary}")

        return {
            "total": len(self.checks),
            "passed": passed,
            "failed": failed,
            "critical_failed": critical_failed,
            "results": results
        }

# ==================== 全局检测器 + 默认检测项 ====================

init_checker = InitializerChecker()


@init_checker.register("Python 版本", level="warning")
def _check_python_version():
    """检测 Python 版本"""
    version = sys.version_info
    if version < (3, 8):
        return False, f"Python 版本过低: {version.major}.{version.minor} (需要 >= 3.8)"
    return True, f"Python {version.major}.{version.minor}.{version.micro}"


@init_checker.register("依赖库", level="critical")
def _check_dependencies():
    """检测关键依赖是否可导入"""
    # frozen 模式跳过（已打包环境依赖完整）
    if getattr(sys, 'frozen', False):
        return True, "frozen 模式跳过依赖扫描"

    # 关键依赖列表
    critical_packages = [
        "fastapi", "uvicorn", "requests", "httpx",
        "webview", "yaml", "peewee",
    ]

    missing = []
    for pkg in critical_packages:
        try:
            __import__(pkg)
        except ImportError:
            missing.append(pkg)

    if missing:
        return False, f"缺少依赖: {', '.join(missing)}"
    return True, f"关键依赖检测通过（{len(critical_packages)} 个）"


@init_checker.register("日志目录", level="warning")
def _check_log_dir():
    """检测并创建日志目录"""
    if not settings.log_dir.exists():
        settings.log_dir.mkdir(parents=True, exist_ok=True)
        return True, f"日志目录已创建: {settings.log_dir}"
    return True, f"日志目录存在: {settings.log_dir}"


@init_checker.register("author.json", level="warning")
def _check_author_json():
    """检测 author.json，不存在则创建空结构"""
    import json
    path = settings.config_path
    if path.exists():
        return True, str(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        json.dump({"api_keys": [], "prompts": [], "authors": []}, f, ensure_ascii=False, indent=2)
    return True, f"已创建空配置: {path}"

@init_checker.register("配置文件同步", level="warning")
def _check_env_sync():
    """检测并同步 .env 配置文件"""
    try:
        from config.settings import settings
        added = settings.sync_env()
        if added:
            return True, "已添加缺失的配置项到 .env"
        return True, "配置文件已是最新"
    except Exception as e:
        return False, f"配置同步失败: {e}"


# ==================== .env → config.yaml 同步 ====================

def _sync_env_to_yaml():
    """将 .env 中的 WX_ 配置项同步到 config.yaml

    路径区分环境：
    - 源码环境: app_root/weixin_exe/config.yaml
    - 打包环境: app_root/lib/config.yaml

    在 initialize_system() 最前面调用，
    保证 wx_video_download.exe 启动前 config.yaml 已是最新的。

    兼容源码/打包环境，使用 sys.executable 定位项目根目录。

    路径修正：
    - Go 后端把相对路径解析为 "lib/所在目录/相对路径"
    - 为让下载目录指向项目根目录，需要把相对路径前面加 "../"
    - 例如: "下载" → "../下载" → 项目根目录/下载
    """
    import yaml
    import os

    # 根据环境确定项目根目录（与 settings.py 逻辑一致）
    exe_path = Path(sys.executable)
    if getattr(sys, 'frozen', False):
        app_root = exe_path.parent
    elif '.venv' in str(exe_path):
        app_root = exe_path.parent.parent.parent
    else:
        app_root = Path(__file__).parent.parent

    # 读取 .env
    env_path = app_root / ".env" if getattr(sys, 'frozen', False) else app_root / "config" / ".env"
    if not env_path.exists():
        return

    env_values = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        env_values[key.strip()] = value.strip()

    # 确定要同步的字段映射
    sync_map = {
        "WX_DOWNLOAD_DIR": ("download", "dir"),
        "WX_FILENAME_TEMPLATE": ("download", "filenameTemplate"),
        "WX_API_HOSTNAME": ("api", "hostname"),
        "WX_API_PORT": ("api", "port"),
        "WX_PROXY_SYSTEM": ("proxy", "system"),
        "WX_PROXY_HOSTNAME": ("proxy", "hostname"),
        "WX_PROXY_PORT": ("proxy", "port"),
    }

    # 检查是否有需要同步的配置
    has_sync = any(k in env_values for k in sync_map)
    if not has_sync:
        return

    # 读取 config.yaml（统一在 lib/ 目录）
    yaml_path = app_root / "config.yaml" if getattr(sys, 'frozen', False) else app_root / "weixin_exe" / "config.yaml"
    if not yaml_path.exists():
        return

    config = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    if config is None:
        config = {}

    # 用 .env 值覆盖 yaml 对应字段
    for env_key, (section, field) in sync_map.items():
        if env_key not in env_values:
            continue
        value = env_values[env_key]

        # 类型转换
        if field == "port":
            value = int(value)
        elif field == "system":
            value = value.lower() in ("true", "1", "yes")

        # 路径修正：相对路径需要加 "../" 前缀
        # 这样 Go 后端解析时: lib/../下载 = 项目根目录/下载
        if field == "dir" and value and not os.path.isabs(value) and not value.startswith("%"):
            value = "../" + value

        if section not in config:
            config[section] = {}
        config[section][field] = value

    # 写回 config.yaml
    yaml_path.write_text(
        yaml.dump(config, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8"
    )


# ==================== 工具函数（内部使用）====================

def _fix_stdout_encoding():
    """修复标准输出编码为 UTF-8"""
    if sys.platform != 'win32':
        return

    # 检查是否有控制台
    if sys.stdout is None or sys.stderr is None:
        if sys.stdout is None:
            sys.stdout = io.TextIOWrapper(io.BytesIO(), encoding='utf-8')
        if sys.stderr is None:
            sys.stderr = io.TextIOWrapper(io.BytesIO(), encoding='utf-8')
        return
def _fix_print_and_logging_output():
    
    # Windows: 重定向到 UTF-8
    try:
        # ========== 关键改进：先刷新缓冲区，避免 print 输出丢失 ==========
        if hasattr(sys.stdout, 'flush'):
            sys.stdout.flush()
        if hasattr(sys.stderr, 'flush'):
            sys.stderr.flush()
        # ========== 刷新完成 ==========

        original_stdout = sys.stdout
        original_stderr = sys.stderr

        if getattr(original_stdout, 'encoding', '') and \
           original_stdout.encoding.lower().replace('-', '') == 'utf8':
            return

        sys.stdout = io.TextIOWrapper(
            original_stdout.buffer,
            encoding='utf-8',
            errors='replace',
            line_buffering=True,
            write_through=True  # ← 关键：直接写入，不缓冲
        )
        sys.stderr = io.TextIOWrapper(
            original_stderr.buffer,
            encoding='utf-8',
            errors='replace',
            line_buffering=True,
            write_through=True  # ← 关键：直接写入，不缓冲
        )
    except (AttributeError, ValueError):
        pass


class _JsonFormatter(logging.Formatter):
    """JSON 格式化器，用于文件输出"""

    def format(self, record: logging.LogRecord) -> str:
        return json.dumps({
            "time": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }, ensure_ascii=False) + "\n"


class _StructlogConsoleHandler(logging.Handler):
    """structlog 风格的彩色控制台输出"""

    COLORS = {
        "DEBUG": "\x1b[36m",    # 青色
        "INFO": "\x1b[32m",     # 绿色
        "WARNING": "\x1b[33m",  # 黄色
        "ERROR": "\x1b[31m",    # 红色
        "CRITICAL": "\x1b[35m",  # 紫色
        "RESET": "\x1b[0m",
    }

    def emit(self, record: logging.LogRecord) -> None:
        from datetime import datetime
        color = self.COLORS.get(record.levelname, "")
        reset = self.COLORS["RESET"]
        timestamp = datetime.fromtimestamp(record.created).strftime("%Y-%m-%d %H:%M:%S")
        msg = record.getMessage()

        sys.stdout.write(f"{color}{timestamp} | {record.name:<25} | {record.levelname:<8} | {msg}{reset}\n")
        sys.stdout.flush()


def _setup_logging(config) -> None:
    """设置日志系统（控制台 + 文件双输出）

    日志级别统一从 config.log_level 读取（来自 LOG_LEVEL 环境变量）。
    DEBUG 模式不影响日志级别，只用于其他调试功能。
    """
    from logging.handlers import TimedRotatingFileHandler

    # 调试：打印读取到的日志级别
    print(f"[日志配置] config.log_level = {config.log_level!r}")

    level = getattr(logging, config.log_level.upper(), logging.INFO)
    print(f"[日志配置] 设置日志级别为: {logging.getLevelName(level)}")

    # 确保日志目录存在
    settings.log_dir.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.handlers.clear()

    # 文件输出：JSON 格式
    file_handler = TimedRotatingFileHandler(
        settings.log_dir / "app.log",
        when="midnight",
        backupCount=7,
        encoding="utf-8",
    )
    file_handler.setLevel(level)
    file_handler.setFormatter(_JsonFormatter())

    # 控制台输出
    try:
        console_handler = _StructlogConsoleHandler(level)
    except ImportError:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(
            logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        )

    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # peewee logger 禁用 propagate
    peewee_logger = logging.getLogger("peewee")
    peewee_logger.setLevel(logging.WARNING)
    peewee_logger.propagate = False

    # 第三方库日志级别
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("watchdog").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)


# ==================== 初始化函数 ====================

def initialize_system():
    """完整初始化流程

    初始化顺序：
    0. 同步 .env → config.yaml
    1. 修复编码
    2. 初始化路径和配置（settings 内部）
    3. 设置日志
    4. 执行初始化检测
    """
    # 0. 同步 .env → config.yaml (最前面，保证 exe 启动前 yaml 已更新)
    _sync_env_to_yaml()

    # 1. 修复编码
    _fix_stdout_encoding()

    # 1.5 清除代理环境变量（避免本地请求走代理导致连接失败）
    for key in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY"):
        os.environ.pop(key, None)
    os.environ["NO_PROXY"] = "*"

    # 2. 使logging和print和平共处而不是让logging抢占print的输出
    _fix_print_and_logging_output()
    # 3. 初始化路径和配置
    settings.initialize()

    # 4. 设置日志
    _setup_logging(settings._config)

    # 4.5 写入待记录的日志（settings.py 初始化时的日志）
    settings.flush_pending_logs()

    # 5. 执行初始化检测
    init_checker.run_all()


# 模块导入时自动初始化
initialize_system()
