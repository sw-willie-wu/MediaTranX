"""
Application configuration routes.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.init.container import AppContainer
from app.schemas.compute_settings import ComputeSettings, ComputeSettingsUpdate

if TYPE_CHECKING:
    from app.services.setup.compute_settings_service import ComputeSettingsService
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


@router.get("/config/compute", response_model=ComputeSettings)
@inject
async def get_compute_settings(
    service: "ComputeSettingsService" = Depends(Provide[AppContainer.compute_settings_service]),
):
    """Get current CPU-fallback compute policy."""
    return service.get_settings()


@router.put("/config/compute", response_model=ComputeSettings)
@inject
async def put_compute_settings(
    request: ComputeSettingsUpdate,
    service: "ComputeSettingsService" = Depends(Provide[AppContainer.compute_settings_service]),
):
    """Update CPU-fallback compute policy (takes effect immediately)."""
    return service.update_settings(request.model_dump(exclude_none=True))