"""
應用程式設定路由
"""
from fastapi import APIRouter
from pydantic import BaseModel

from app.services.setup.config_service import get_config_service
from app.services.setup.language_service import get_language_service

router = APIRouter()


@router.get("/config")
async def get_config():
    """取得應用程式設定"""
    return get_config_service().get_config()


class AppConfigUpdate(BaseModel):
    models_dir: str = ""
    temp_dir: str = ""


@router.post("/config")
async def update_config(data: AppConfigUpdate):
    """更新應用程式設定，重啟後生效"""
    return get_config_service().update_config(
        models_dir=data.models_dir,
        temp_dir=data.temp_dir,
    )


@router.get("/translate-styles")
async def get_translate_styles():
    """取得翻譯風格選項列表"""
    return get_language_service().get_translate_styles()
