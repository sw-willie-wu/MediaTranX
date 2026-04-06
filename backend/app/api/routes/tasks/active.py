"""
進行中任務端點
"""
from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException
from typing import List

from app.init.container import AppContainer
from app.workers.task_manager import TaskManager
from app.api.schemas.common import TaskResponse

router = APIRouter()


@router.get("/", response_model=List[TaskResponse])
@inject
async def list_tasks(
    task_manager: TaskManager = Depends(Provide[AppContainer.task_manager]),
):
    """列出所有任務"""
    return [TaskResponse.from_task_data(t) for t in task_manager.get_all_tasks()]


@router.get("/active", response_model=List[TaskResponse])
@inject
async def list_active_tasks(
    task_manager: TaskManager = Depends(Provide[AppContainer.task_manager]),
):
    """列出進行中的任務"""
    return [TaskResponse.from_task_data(t) for t in task_manager.get_active_tasks()]


@router.get("/{task_id}", response_model=TaskResponse)
@inject
async def get_task(
    task_id: str,
    task_manager: TaskManager = Depends(Provide[AppContainer.task_manager]),
):
    """取得任務狀態"""
    task = task_manager.get_task(task_id)

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return TaskResponse.from_task_data(task)


@router.post("/{task_id}/cancel")
@inject
async def cancel_task(
    task_id: str,
    task_manager: TaskManager = Depends(Provide[AppContainer.task_manager]),
):
    """取消任務"""
    if not await task_manager.cancel(task_id):
        raise HTTPException(status_code=400, detail="Cannot cancel task")

    return {"status": "cancelled", "task_id": task_id}


@router.delete("/{task_id}")
@inject
async def remove_task(
    task_id: str,
    task_manager: TaskManager = Depends(Provide[AppContainer.task_manager]),
):
    """移除已完成的任務"""
    if not task_manager.remove(task_id):
        raise HTTPException(status_code=400, detail="Cannot remove task")

    return {"status": "removed", "task_id": task_id}
