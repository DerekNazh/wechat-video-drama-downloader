"""
配置管理模块 - 视频下载
单例模式，负责配置加载和路径管理

使用方式：
    from config import settings

    # 访问配置
    api_key = settings.api_key
    model = settings.model

    # 访问路径
    app_root = settings.app_root
    log_dir = settings.log_root
    gui_dir = settings.get_gui_dir()

    # 同步配置文件
    settings.sync_env()  # 自动添加 .env.example 中缺失的配置项到 .env
"""
import os
import sys
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, List

try:
    from dotenv import load_dotenv
except ImportError:
    logger.info("错误: 需要安装 python-dotenv 库")
    logger.info("请运行: pip install python-dotenv")
    sys.exit(1)


# ==================== 默认提示词配置 ====================

# 注意：提示词数据已移至 author.json，此处保留空列表作为后备
DEFAULT_PROMPTS: List[Dict] = []


# ==================== 默认 API 配置 ====================

# 注意：API 配置数据已移至 author.json，此处保留空列表作为后备
DEFAULT_API_CONFIGS: List[Dict] = []


# ==================== 环境配置数据类 ====================

@dataclass
class _EnvConfig:
    """环境配置数据（来自 .env）

    说明：
        - 只包含从 .env 文件加载的环境参数
        - API 配置从 author.json 读取，不在这里
        - 使用 dataclass 提供类型检查和默认值
        - 仅保留实际在用的字段，无用字段已清除
    """
    # 项目信息
    project_version: str

    # 日志配置
    log_level: str = "INFO"

    # ===== 视频号自动监控配置 =====
    wx_status_interval: int = 5        # 服务状态轮询间隔（秒）
    wx_download_dir: str = "下载"      # 下载目录（相对 app_root）
    max_concurrent: int = 5            # 最大并发下载数
    doc_sync_interval: int = 60       # 腾讯文档监控轮询间隔（分钟）

    # 广告开关
    ads_enabled: bool = True          # 广告总开关

    # GUI 调试
    pywebview_debug: bool = False     # pywebview 开发者工具


# ==================== 配置管理器（单例）====================

class SettingsManager:
    """全局配置管理器 - 单例模式

    职责：
    1. 路径管理（兼容打包/源码环境）
    2. 配置加载（.env 文件）
    3. 提供 .env 配置属性访问
    """

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            # 初始化待记录日志列表
            cls._instance._pending_logs = []
            # 创建智能 logger（用于初始化阶段）
            cls._instance._init_logger = cls._instance._create_init_logger()
        return cls._instance

    def _create_init_logger(self):
        """创建初始化阶段的智能 logger

        说明：
            - 初始化时日志系统还未配置
            - 此 logger 会：保存到内存（不输出到控制台）
            - 等 initializer 配置好日志系统后，再一次性输出到控制台和文件
        """
        import logging

        class InitLogger:
            def __init__(self, pending_list):
                self.pending = pending_list

            def info(self, msg, *args, **kwargs):
                """保存到内存（等后续输出）"""
                full_msg = msg % args if args else msg
                self.pending.append((logging.INFO, full_msg, kwargs))

            def warning(self, msg, *args, **kwargs):
                """保存到内存（等后续输出）"""
                full_msg = msg % args if args else msg
                self.pending.append((logging.WARNING, full_msg, kwargs))

            def error(self, msg, *args, **kwargs):
                """保存到内存（等后续输出）"""
                full_msg = msg % args if args else msg
                self.pending.append((logging.ERROR, full_msg, kwargs))

        return InitLogger(self._pending_logs)

    def initialize(self, env_path: str = None) -> None:
        """初始化配置和路径（只执行一次）

        初始化顺序：
        1. 初始化路径（sys.path + 目录结构）
        2. 加载 .env 配置
        3. 加载 author.json 配置
        """
        if self._initialized:
            return

        # 1. 初始化路径
        self._init_paths()
        self._init_sys_path()
        self.ensure_dirs()

        # 2. 加载配置
        if env_path is None:
            env_path = str(self.env_path)
        self._config = self._load_env(env_path)

        # 3. 加载 API 配置和提示词
        self._load_configs()

        # 4. 打印配置汇总
        self._print_config_summary()

        self._initialized = True

    def _print_config_summary(self):
        """打印配置汇总信息"""
        print(f"\n{'='*60}")
        print(f"[配置汇总] SettingsManager 初始化完成")
        print(f"{'='*60}")
        print(f"[路径配置]")
        print(f"  应用根目录: {self.app_root}")
        print(f"  配置文件: {self.config_path}")
        print(f"  .env文件: {self.env_path}")
        print(f"  日志目录: {self.log_dir}")
        print(f"\n[.env 变量访问]")
        print(f"  项目版本: {self.project_version}")
        print(f"  日志级别: {self.log_level}")
        print(f"  状态轮询间隔: {self.wx_status_interval}s")
        print(f"  下载目录: {self.wx_download_dir}")
        print(f"  最大并发下载数: {self.max_concurrent}")
        print(f"\n[author.json 数据访问]")
        print(f"{'='*60}\n")

    def flush_pending_logs(self):
        """写入待记录的日志到日志系统

        说明：
            - settings.py 初始化时，日志系统还未配置
            - 所以先把日志保存在 _pending_logs 列表中
            - 等 initializer.py 配置好日志系统后，再调用此方法写入
        """
        if not self._pending_logs:
            return

        import logging

        logger = logging.getLogger(__name__)

        # 写入所有待记录的日志
        for level, msg, extra in self._pending_logs:
            logger.log(level, msg, extra=extra)

        # 清空列表
        self._pending_logs.clear()

    # ========== 路径管理 ==========

    def _init_paths(self):
        """初始化路径（兼容打包/源码环境）

        统一使用 sys.executable 定位项目根目录：
        - 源码环境: .venv/Scripts/python.exe → 上三级 → 项目根目录
        - 打包环境: xxx.exe → 父目录 → 项目根目录

        所有路径使用相对路径定义，统一基于 app_root
        """
        exe_path = Path(sys.executable)

        if getattr(sys, 'frozen', False):
            # frozen: 项目根目录 = exe 所在目录（onedir 和 onefile 一致）
            # _internal 是 PyInstaller 内部目录，app_root 永远指向项目根目录
            self.app_root = exe_path.parent
        else:
            # 源码环境: 通过 .venv 定位项目根目录
            # .venv/Scripts/python.exe → .venv/Scripts → .venv → project/
            if '.venv' in str(exe_path):
                self.app_root = exe_path.parent.parent.parent
            else:
                # 回退方案：使用 config 目录的上级目录
                self.app_root = Path(__file__).parent.parent

        self._is_frozen = getattr(sys, 'frozen', False)

        # ========== 初始化配置变量 ==========

        self._api_configs = []  # API 配置列表
        self._prompts = []         # 提示词列表

    @property
    def env_path(self) -> Path:
        """获取 .env 文件路径（支持 ENV_PATH 环境变量覆盖）

        单一路径来源：app_root
        - 源码环境: app_root/config/.env
        - 打包环境: app_root/.env（由 build.py 从 config/.env 复制到根目录）
        """
        env_path_str = os.getenv("ENV_PATH")
        if env_path_str:
            p = Path(env_path_str)
            return p if p.is_absolute() else self.app_root / p

        # 打包环境由 build.py 将 config/.env 复制到根目录
        rel = ".env" if self._is_frozen else "config/.env"
        return self.app_root / rel

    @property
    def data_dir(self) -> Path:
        """用户数据目录"""
        return self.app_root / "data"

    @property
    def lib_dir(self) -> Path:
        """运行时库目录"""
        return self.app_root / "lib"

    @property
    def config_path(self) -> Path:
        """获取 author.json 配置文件路径（存放在 data/ 目录下，用户无需关注）"""
        return self.app_root / "data" / "author.json"
    @property
    def log_dir(self) -> Path:
        """获取日志目录路径"""
        return self.app_root / "logs"

    @property
    def static_dir(self) -> Path:
        """获取 static 目录路径"""
        return self.app_root / "static"

    @property
    def gopeed_db_path(self) -> Path:
        """获取 gopeed.db 路径"""
        if self._is_frozen:
            return self.app_root / "lib" / "gopeed.db"
        return self.app_root / "weixin_exe" / "gopeed.db"

    @property
    def wx_config_yaml_path(self) -> Path:
        """获取微信下载服务 config.yaml 路径"""
        if self._is_frozen:
            return self.app_root / "lib" / "config.yaml"
        return self.app_root / "weixin_exe" / "config.yaml"

    @property
    def wx_exe_path(self) -> Path:
        """获取 wx_video_download.exe 路径"""
        if self._is_frozen:
            return self.app_root / "lib" / "wx_video_download.exe"
        return self.app_root / "weixin_exe" / "wx_video_download.exe"

    def _init_sys_path(self):
        """初始化 sys.path - 添加项目根目录和 core 目录"""
        app_root_str = str(self.app_root)
        if app_root_str not in sys.path:
            sys.path.insert(0, app_root_str)
        # core/ 目录包含 weixin_monitor 等核心模块
        core_str = str(self.app_root / "core")
        if core_str not in sys.path:
            sys.path.insert(0, core_str)

    def ensure_dirs(self):
        """确保关键目录存在"""
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def _load_configs(self):
        """从 author.json 加载 API 配置和提示词"""
        import json
        import logging

        # 使用智能 logger（同时保存到内存和输出到控制台）
        logger = self._init_logger

        config_path = self.config_path
        print(f"\n{'='*60}")
        print(f"[配置加载] 从 author.json 加载配置")
        print(f"{'='*60}")
        print(f"配置文件路径: {config_path}")

        if not config_path.exists():
            logger.warning(f"配置文件不存在: {config_path}，使用空配置")
            self._api_configs = []
            self._prompts = []
            print(f"[author.json 配置项]")
            print(f"  API配置数量: 0")
            print(f"  提示词数量: 0")
            print(f"{'='*60}\n")
            return

        try:
            with open(config_path, encoding='utf-8') as f:
                data = json.load(f)

            self._api_configs = data.get("api_keys", [])
            self._prompts = data.get("prompts", [])

            print(f"\n[author.json 配置项]")
            print(f"  API配置数量: {len(self._api_configs)}")

            # 打印每个 API 配置的简要信息
            for i, api_config in enumerate(self._api_configs, 1):
                print(f"    [{i}] ID: {api_config.get('id')}, Name: {api_config.get('name')}, Base URL: {api_config.get('base_url')}, Model: {api_config.get('model')}")

           

            # 打印每个提示词的简要信息
            for i, prompt in enumerate(self._prompts, 1):
                print(f"    [{i}] ID: {prompt.get('id')}, Name: {prompt.get('name')}, Type: {prompt.get('type')}")

            print(f"{'='*60}\n")


        except json.JSONDecodeError as e:
            self._api_configs = []
            self._prompts = []
            print(f"[错误] 配置文件 JSON 格式错误: {e}")
            print(f"{'='*60}\n")
            logger.error(f"配置文件 JSON 格式错误: {e}")
        except Exception as e:
            self._api_configs = []
            self._prompts = []
            print(f"[错误] 加载配置文件失败: {e}")
            print(f"{'='*60}\n")
            logger.error(f"加载配置文件失败: {e}")

    def sync_env(self) -> bool:
        """同步 .env 文件：添加 .env.example 中存在但 .env 中缺失的配置项

        Returns:
            bool: 是否有新增配置项

        说明：
            - 读取 .env.example 获取所有应该有的配置项
            - 读取当前 .env 文件，提取已存在的配置项
            - 将缺失的配置项添加到 .env 文件末尾
        """
        env_path = self.env_path
        example_path = env_path.parent / ".env.example"

        # 如果 .env.example 不存在，无法同步
        if not example_path.exists():
            return False

        # 如果 .env 不存在，直接复制 .env.example
        if not env_path.exists():
            import shutil
            shutil.copy(example_path, env_path)
            print(f"[配置] 已创建 .env 文件: {env_path}")
            return True

        # 读取 .env.example 和 .env
        example_lines = example_path.read_text(encoding='utf-8').splitlines()
        env_lines = env_path.read_text(encoding='utf-8').splitlines()

        # 提取 .env 中已存在的配置项名称
        existing_keys = set()
        for line in env_lines:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key = line.split('=')[0].strip()
                existing_keys.add(key)

        # 找出缺失的配置项
        missing_lines = []
        for line in example_lines:
            line_stripped = line.strip()
            # 跳过空行和注释
            if not line_stripped or line_stripped.startswith('#'):
                continue
            # 检查是否是配置项
            if '=' in line_stripped:
                key = line_stripped.split('=')[0].strip()
                if key not in existing_keys:
                    # 找到这个配置项的注释（前面相邻的注释行）
                    comment_lines = []
                    i = example_lines.index(line)
                    for j in range(i - 1, -1, -1):
                        prev_line = example_lines[j].strip()
                        if prev_line.startswith('#'):
                            comment_lines.insert(0, example_lines[j])
                        else:
                            break
                    # 添加注释和配置项
                    missing_lines.extend(comment_lines)
                    missing_lines.append(line)

        # 如果有缺失的配置项，添加到 .env
        if missing_lines:
            with open(env_path, 'a', encoding='utf-8') as f:
                f.write('\n\n# ========== 自动同步的配置项 ==========\n')
                f.write('\n'.join(missing_lines))
            print(f"[配置] 已添加 {len([l for l in missing_lines if '=' in l])} 个缺失的配置项到 .env")
            return True

        return False

    # ========== 配置加载 ==========

    def _load_env(self, env_path: str) -> _EnvConfig:
        """加载 .env 配置"""
        import logging
        env_file = Path(env_path)

        # 使用智能 logger（同时保存到内存和输出到控制台）
        logger = self._init_logger

        if env_file.exists():
            load_dotenv(env_path)
            print(f"\n{'='*60}")
            print(f"[配置加载] 从 .env 文件加载配置")
            print(f"{'='*60}")
            print(f"配置文件路径: {env_file}")
        else:
            print(f"[警告] 环境变量文件不存在: {env_path}，使用默认配置")

        config_data = _EnvConfig(
            # 项目信息
            project_version=os.getenv("PROJECT_VERSION", "1.0.0"),

            # 日志配置
            log_level=os.getenv("LOG_LEVEL", "INFO"),

            # 视频号自动监控配置
            wx_status_interval=int(os.getenv("WX_STATUS_INTERVAL", "5")),
            wx_download_dir=os.getenv("WX_DOWNLOAD_DIR", "下载"),
            max_concurrent=int(os.getenv("MAX_CONCURRENT", "5")),
            doc_sync_interval=int(os.getenv("DOC_SYNC_INTERVAL", "60")),
            ads_enabled=os.getenv("ADS_ENABLED", "true").lower() == "true",
            pywebview_debug=os.getenv("PYWEBVIEW_DEBUG", "false").lower() == "true",
        )

        # 打印 .env 加载的配置
        if env_file.exists():
            print(f"\n[.env 配置项]")
            print(f"  项目版本: {config_data.project_version}")
            print(f"  日志级别: {config_data.log_level}")
            print(f"  状态轮询间隔: {config_data.wx_status_interval}s")
            print(f"  下载目录: {config_data.wx_download_dir}")
            print(f"{'='*60}\n")

            # 使用智能 logger（自动保存到内存 + 输出到控制台）
            logger.info(
                f"从 .env 加载配置: 版本={config_data.project_version}, "
                f"日志级别={config_data.log_level}"
            )

        return config_data

    # ========== 对外接口：配置属性 ==========

    @property
    def project_version(self): return self._config.project_version

    @property
    def log_level(self): return self._config.log_level

    @property
    def wx_status_interval(self): return self._config.wx_status_interval

    @property
    def wx_download_dir(self):
        """获取下载目录的绝对路径（基于 app_root 解析）"""
        raw = self._config.wx_download_dir
        p = Path(raw)
        if p.is_absolute():
            return p
        return self.app_root / raw

    @property
    def max_concurrent(self): return self._config.max_concurrent

    @property
    def ads_enabled(self): return self._config.ads_enabled

    @property
    def pywebview_debug(self): return self._config.pywebview_debug

    @max_concurrent.setter
    def max_concurrent(self, value: int):
        self._config.max_concurrent = max(1, min(20, value))

    # ========== 对外接口：路径属性 ==========

    @property
    def log_root(self): return self.log_dir


# ==================== 全局单例 ====================

_app_settings = SettingsManager()
_app_settings.initialize()  # 自动初始化

# 导出为 settings（兼容现有代码）
settings = _app_settings
