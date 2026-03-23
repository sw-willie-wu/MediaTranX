"""
應用程式設定服務
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
包裝 engine.paths 的設定操作，提供給 Route 層使用。
Route 不應直接 import engine.paths 的 config 函數。
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ConfigService:
    """應用程式設定管理服務（單例）"""

    _instance: Optional["ConfigService"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
        logger.info("ConfigService initialized")

    def get_config(self) -> dict:
        """取得應用程式設定（含有效路徑）"""
        from app.engine.paths import get_models_dir, get_temp_dir, get_app_config
        config = get_app_config()
        return {
            "models_dir": config.get("models_dir", ""),
            "effective_models_dir": str(get_models_dir()),
            "temp_dir": config.get("temp_dir", ""),
            "effective_temp_dir": str(get_temp_dir()),
        }

    def update_config(self, models_dir: str = "", temp_dir: str = "") -> dict:
        """更新應用程式設定，回傳 {ok, needs_restart}"""
        from app.engine.paths import get_app_config, save_app_config
        config = get_app_config()
        for key, val in {"models_dir": models_dir, "temp_dir": temp_dir}.items():
            if val.strip():
                config[key] = val.strip()
            else:
                config.pop(key, None)
        save_app_config(config)
        return {"ok": True, "needs_restart": True}


_config_service: Optional[ConfigService] = None


def get_config_service() -> ConfigService:
    """取得 ConfigService 單例"""
    global _config_service
    if _config_service is None:
        _config_service = ConfigService()
    return _config_service
