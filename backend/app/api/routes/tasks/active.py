"""
Active task endpoints.
"""
from datetime import datetime
from typing import Any, List, Optional

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_serializer

from app.init.container import AppContainer
from app.types.task import TaskData, TaskStatus
from app.workers.task_manager import TaskManager


def _serialize_dt(v: datetime) -> str:
    return v.isoformat()


class TaskResponse(BaseModel):
    """Task API response model."""
    task_id: str
    task_type: str
    status: TaskStatus = TaskStatus.PENDING
    progress: float = Field(default=0.0, ge=0.0, le=1.0)
    message: Optional[str] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    _serialize_created_at = field_serializer("created_at")(_serialize_dt)
    _serialize_updated_at = field_serializer("updated_at")(_serialize_dt)

    @classmethod
    def from_task_data(cls, t: TaskData) -> "TaskResponse":
        return cls(
            task_id=t.task_id,
            task_type=t.task_type,
            status=t.status,
            progress=t.progress,
            message=t.message,
            result=t.result,
            error=t.error,
            error_code=getattr(t, 'error_code', None),
            created_at=t.created_at,
            updated_at=t.updated_at,
        )

router = APIRouter()


@router.get("/", response_model=List[TaskResponse])
@inject
async def list_tasks(
    task_manager: TaskManager = Depends(Provide[AppContainer.task_manager]),
):
    """List all tasks."""
    return [TaskResponse.from_task_data(t) for t in task_manager.get_all_tasks()]


@router.get("/active", response_model=List[TaskResponse])
@inject
async def list_active_tasks(
    task_manager: TaskManager = Depends(Provide[AppContainer.task_manager]),
):
    """List active (in-progress) tasks."""
    return [TaskResponse.from_task_data(t) for t in task_manager.get_active_tasks()]


@router.get("/{task_id}", response_model=TaskResponse)
@inject
async def get_task(
    task_id: str,
    task_manager: TaskManager = Depends(Provide[AppContainer.task_manager]),
):
    """Get task status."""
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
    """Cancel a task."""
    if not await task_manager.cancel(task_id):
        raise HTTPException(status_code=400, detail="Cannot cancel task")

    return {"status": "cancelled", "task_id": task_id}


@router.delete("/{task_id}")
@inject
async def remove_task(
    task_id: str,
    task_manager: TaskManager = Depends(Provide[AppContainer.task_manager]),
):
    """Remove a completed task."""
    if not task_manager.remove(task_id):
        raise HTTPException(status_code=400, detail="Cannot remove task")

    return {"status": "removed", "task_id": task_id}
