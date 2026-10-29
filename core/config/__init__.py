"""号匣（haoxia）配置包。对外导出全局 settings 单例。"""
from core.config.settings import Settings, get_settings, ensure_env_bootstrapped

settings = get_settings()

__all__ = ["Settings", "get_settings", "settings", "ensure_env_bootstrapped"]
