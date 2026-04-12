"""
Application configuration routes.
"""
from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.init.container import AppContainer
from app.services.setup.config_service import ConfigService
router = APIRouter()


@router.get("/config")
@inject
async def get_config(
    config_service: ConfigService = Depends(Provide[AppContainer.config_service]),
):
    """Get application configuration."""
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
    """Update application configuration (takes effect after restart)."""
    return config_service.update_config(
        models_dir=data.models_dir,
        temp_dir=data.temp_dir,
    )