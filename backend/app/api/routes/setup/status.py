"""
系統狀態與環境初始化路由
"""
from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, BackgroundTasks, Depends
from uuid import uuid4

from app.init.container import AppContainer
from app.services.setup.manager_service import SetupService
from app.workers.task_manager import TaskManager

router = APIRouter()


@router.get("/status")
@inject
async def get_status(
    service: SetupService = Depends(Provide[AppContainer.setup_service]),
):
    """取得系統環境狀態"""
    return await service.get_system_status()


@router.post("/initialize")
@inject
async def initialize_env(
    background_tasks: BackgroundTasks,
    service: SetupService = Depends(Provide[AppContainer.setup_service]),
    task_manager: TaskManager = Depends(Provide[AppContainer.task_manager]),
):
    """啟動 AI 環境初始化任務"""
    task_id = f"setup-{uuid4().hex[:8]}"

    task_manager.register_task(task_id, "ai.setup")

    background_tasks.add_task(service.initialize_ai_env, task_id)

    return {"task_id": task_id}
