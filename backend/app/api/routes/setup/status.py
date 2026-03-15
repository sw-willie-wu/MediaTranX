"""
系統狀態與環境初始化路由
"""
from fastapi import APIRouter, BackgroundTasks
from uuid import uuid4

from app.services.setup import get_setup_service
from app.workers.task_manager import get_task_manager

router = APIRouter()

# 初始化 SetupService（完成 task handler 的綁定）
get_setup_service()


@router.get("/status")
async def get_status():
    """取得系統環境狀態"""
    service = get_setup_service()
    return await service.get_system_status()


@router.post("/initialize")
async def initialize_env(background_tasks: BackgroundTasks):
    """啟動 AI 環境初始化任務"""
    service = get_setup_service()
    task_id = f"setup-{uuid4().hex[:8]}"

    task_manager = get_task_manager()
    task_manager.register_task(task_id, "ai.setup")

    background_tasks.add_task(service.initialize_ai_env, task_id)

    return {"task_id": task_id}
