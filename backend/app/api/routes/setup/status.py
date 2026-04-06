"""
系統狀態路由
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
    """取得系統環境狀態"""
    return await service.get_system_status()
