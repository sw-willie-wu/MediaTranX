"""Device info + refresh endpoints."""
from __future__ import annotations
from typing import TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.setup.device_service import DeviceService


router = APIRouter()


@router.get("/device")
@inject
async def device_info(
    service: DeviceService = Depends(Provide[AppContainer.device_service]),
):
    """Get device information (GPU/CPU)."""
    return service.get_device_info()


@router.post("/device/refresh")
@inject
async def refresh_device(
    service: DeviceService = Depends(Provide[AppContainer.device_service]),
):
    """Clear device cache and re-detect (called after CUDA DLL installation)."""
    service.refresh_cache()
    return service.get_device_info()
