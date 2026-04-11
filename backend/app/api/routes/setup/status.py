"""
System status routes.
"""
from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends

from app.init.container import AppContainer
from app.services.setup.manager_service import SetupService

router = APIRouter()


@router.get("/status")
@inject
async def get_status(
    service: SetupService = Depends(Provide[AppContainer.setup_service]),
):
    """Get system environment status."""
    return await service.get_system_status()
