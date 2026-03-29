"""
模型管理路由（列表、下載、移除）
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.setup import get_setup_service
from app.services.setup.model_metadata_service import get_model_metadata_service
from app.workers.task_manager import get_task_manager

router = APIRouter()


# ─── 端點 ────────────────────────────────────────────────────────────────────

@router.get("/models")
async def get_models_status():
    """取得所有工具/模型的安裝/下載狀態"""
    return get_model_metadata_service().list_all()


class DownloadRequest(BaseModel):
    id: str


@router.post("/models/remove")
async def remove_model_item(request: DownloadRequest):
    """刪除已下載的工具/模型檔案"""
    if not request.id:
        raise HTTPException(status_code=400, detail="Missing id")
    service = get_setup_service()
    service.remove_model(request.id)
    return {"ok": True}


@router.post("/models/download")
async def download_model_item(request: DownloadRequest):
    """提交工具/模型下載任務"""
    if not request.id:
        raise HTTPException(status_code=400, detail="Missing id")

    task_manager = get_task_manager()
    task_id = await task_manager.submit("setup.model_download", {"id": request.id})
    return {"task_id": task_id}
