"""
任務管理端點
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from typing import List

from backend.workers.task_manager import get_task_manager
from backend.api.schemas.common import TaskResponse

router = APIRouter()


@router.get("", response_model=List[TaskResponse])
async def list_tasks():
    """列出所有任務"""
    task_manager = get_task_manager()
    return task_manager.get_all_tasks()


@router.get("/active", response_model=List[TaskResponse])
async def list_active_tasks():
    """列出進行中的任務"""
    task_manager = get_task_manager()
    return task_manager.get_active_tasks()


@router.get("/{task_id}", response_model=TaskResponse)
async def get_task(task_id: str):
    """
    取得任務狀態

    Args:
        task_id: 任務 ID
    """
    task_manager = get_task_manager()
    task = task_manager.get_task(task_id)

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return task


@router.get("/{task_id}/progress")
async def stream_progress(task_id: str):
    """
    任務進度 SSE 串流

    Args:
        task_id: 任務 ID

    Returns:
        Server-Sent Events 串流
    """
    task_manager = get_task_manager()
    task = task_manager.get_task(task_id)

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    async def event_generator():
        async for event in task_manager.progress_tracker.subscribe(task_id):
            yield f"data: {event.to_json()}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 nginx 緩衝
        }
    )


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str):
    """
    取消任務

    Args:
        task_id: 任務 ID
    """
    task_manager = get_task_manager()

    if not await task_manager.cancel(task_id):
        raise HTTPException(status_code=400, detail="Cannot cancel task")

    return {"status": "cancelled", "task_id": task_id}


@router.delete("/{task_id}")
async def remove_task(task_id: str):
    """
    移除已完成的任務

    Args:
        task_id: 任務 ID
    """
    task_manager = get_task_manager()

    if not task_manager.remove(task_id):
        raise HTTPException(status_code=400, detail="Cannot remove task")

    return {"status": "removed", "task_id": task_id}
