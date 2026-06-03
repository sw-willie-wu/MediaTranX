"""
Active task endpoints.
"""
from __future__ import annotations
from datetime import datetime
from typing import Any, List, Optional, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_serializer

from app.init.container import AppContainer
from app.schemas.task import TaskData, TaskStatus

if TYPE_CHECKING:
    from app.workers.task_manager import TaskManager
    from app.services.files.file_service import FileService


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
    file_id: Optional[str] = None
    file_name: Optional[str] = None
    notices: list = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    _serialize_created_at = field_serializer("created_at")(_serialize_dt)
    _serialize_updated_at = field_serializer("updated_at")(_serialize_dt)

    @classmethod
    def from_task_data(cls, t: TaskData, file_service: Optional["FileService"] = None) -> "TaskResponse":
        """Build a response from internal task state.

        ``file_service`` (optional) resolves ``t.file_id`` to a human-readable
        ``file_name``; omitted -> ``file_name`` stays None.
        """
        from app.utils.task_notices import snapshot_notices
        return cls(
            task_id=t.task_id,
            task_type=t.task_type,
            status=t.status,
            progress=t.progress,
            message=t.message,
            result=t.result,
            error=t.error,
            error_code=getattr(t, 'error_code', None),
            file_id=t.file_id,
            file_name=file_service.get_file_name(t.file_id) if file_service else None,
            notices=snapshot_notices(getattr(t, "notices", []) or []),
            created_at=t.created_at,
            updated_at=t.updated_at,
        )

router = APIRouter()


@router.get("/", response_model=List[TaskResponse])
@inject
async def list_tasks(
    task_manager: TaskManager = Depends(Provide[AppContainer.task_manager]),
    file_service: FileService = Depends(Provide[AppContainer.file_service]),
):
    """List all tasks."""
    return [TaskResponse.from_task_data(t, file_service)
            for t in task_manager.get_all_tasks()]


@router.get("/active", response_model=List[TaskResponse])
@inject
async def list_active_tasks(
    task_manager: TaskManager = Depends(Provide[AppContainer.task_manager]),
    file_service: FileService = Depends(Provide[AppContainer.file_service]),
):
    """List active (in-progress) tasks."""
    return [TaskResponse.from_task_data(t, file_service)
            for t in task_manager.get_active_tasks()]


@router.get("/{task_id}", response_model=TaskResponse)
@inject
async def get_task(
    task_id: str,
    task_manager: TaskManager = Depends(Provide[AppContainer.task_manager]),
    file_service: FileService = Depends(Provide[AppContainer.file_service]),
):
    """Get task status."""
    return TaskResponse.from_task_data(task_manager.require_task(task_id), file_service)


@router.post("/{task_id}/cancel")
@inject
async def cancel_task(
    task_id: str,
    task_manager: TaskManager = Depends(Provide[AppContainer.task_manager]),
):
    """Cancel a task."""
    await task_manager.cancel(task_id)
    return {"status": "cancelled", "task_id": task_id}


@router.delete("/{task_id}")
@inject
async def remove_task(
    task_id: str,
    task_manager: TaskManager = Depends(Provide[AppContainer.task_manager]),
):
    """Remove a completed task."""
    task_manager.remove(task_id)
    return {"status": "removed", "task_id": task_id}
