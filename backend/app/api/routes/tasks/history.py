"""
Task history endpoints.
"""
from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from typing import Optional

from app.init.container import AppContainer
from app.services.tasks.history_service import TaskHistoryService

router = APIRouter(prefix="/history")


class SaveHistoryRequest(BaseModel):
    """Save a frontend-only task to history (e.g. MIDI export)."""
    task_id: str
    task_type: str
    status: str = "completed"
    label: Optional[str] = None
    file_name: Optional[str] = None
    error: Optional[str] = None
    result: Optional[dict] = None


class SaveHistoryResponse(BaseModel):
    """Save history response."""
    status: str
    task_id: str


@router.post("", response_model=SaveHistoryResponse)
@inject
async def save_history(
    request: SaveHistoryRequest,
    history: TaskHistoryService = Depends(Provide[AppContainer.task_history]),
):
    """Save a frontend-only task to history."""
    try:
        history.save_frontend_task(
            task_id=request.task_id,
            task_type=request.task_type,
            status=request.status,
            label=request.label,
            file_name=request.file_name,
            error=request.error,
            result=request.result,
        )
        return SaveHistoryResponse(status="saved", task_id=request.task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


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
