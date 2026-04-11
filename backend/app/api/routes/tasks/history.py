"""
Task history endpoints.
"""
from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional

from app.init.container import AppContainer
from app.services.tasks.history_service import TaskHistoryService

router = APIRouter(prefix="/history")


@router.get("")
@inject
async def list_history(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=30, ge=1, le=100),
    status: Optional[str] = Query(default=None),
    history: TaskHistoryService = Depends(Provide[AppContainer.task_history]),
):
    """Query task history (paginated)."""
    return history.query(page=page, page_size=page_size, status=status)


@router.delete("/{task_id}")
@inject
async def delete_history_item(
    task_id: str,
    history: TaskHistoryService = Depends(Provide[AppContainer.task_history]),
):
    """Delete a single history entry."""
    if not history.delete(task_id):
        raise HTTPException(status_code=404, detail="History item not found")
    return {"status": "deleted", "task_id": task_id}


@router.delete("")
@inject
async def clear_history(
    history: TaskHistoryService = Depends(Provide[AppContainer.task_history]),
):
    """Clear all history entries."""
    count = history.clear()
    return {"status": "cleared", "count": count}
