"""
應用程式設定路由
"""
from fastapi import APIRouter
from pydantic import BaseModel

from app.engine.paths import get_models_dir, get_temp_dir, get_app_config, save_app_config

router = APIRouter()


@router.get("/config")
async def get_config():
    """取得應用程式設定"""
    config = get_app_config()
    return {
        "models_dir": config.get("models_dir", ""),
        "effective_models_dir": str(get_models_dir()),
        "temp_dir": config.get("temp_dir", ""),
        "effective_temp_dir": str(get_temp_dir()),
    }


class AppConfigUpdate(BaseModel):
    models_dir: str = ""
    temp_dir: str = ""


@router.post("/config")
async def update_config(data: AppConfigUpdate):
    """更新應用程式設定，重啟後生效"""
    config = get_app_config()
    for key, val in {"models_dir": data.models_dir, "temp_dir": data.temp_dir}.items():
        if val.strip():
            config[key] = val.strip()
        else:
            config.pop(key, None)
    save_app_config(config)
    return {"ok": True, "needs_restart": True}


@router.get("/translate-styles")
async def get_translate_styles():
    """取得翻譯風格選項列表"""
    from app.engine.ai.base.translate import STYLE_OPTIONS
    return STYLE_OPTIONS
