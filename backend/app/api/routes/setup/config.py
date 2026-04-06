"""
應用程式設定路由
"""
from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.init.container import AppContainer
from app.services.setup.config_service import ConfigService
from app.services.setup.language_service import LanguageService

router = APIRouter()


@router.get("/config")
@inject
async def get_config(
    config_service: ConfigService = Depends(Provide[AppContainer.config_service]),
):
    """取得應用程式設定"""
    return config_service.get_config()


class AppConfigUpdate(BaseModel):
    models_dir: str = ""
    temp_dir: str = ""


@router.post("/config")
@inject
async def update_config(
    data: AppConfigUpdate,
    config_service: ConfigService = Depends(Provide[AppContainer.config_service]),
):
    """更新應用程式設定，重啟後生效"""
    return config_service.update_config(
        models_dir=data.models_dir,
        temp_dir=data.temp_dir,
    )


@router.get("/translate-styles")
@inject
async def get_translate_styles(
    language_service: LanguageService = Depends(Provide[AppContainer.language_service]),
):
    """取得翻譯風格選項列表"""
    return language_service.get_translate_styles()
