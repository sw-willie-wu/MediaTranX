"""
System status routes.
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.setup.manager_service import SetupService

router = APIRouter()


@router.get("/status")
@inject
async def get_status(
    service: SetupService = Depends(Provide[AppContainer.setup_service]),
):
    """Get system environment status."""
    return await service.get_system_status()
