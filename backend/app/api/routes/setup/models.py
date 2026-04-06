"""
模型管理路由（列表、下載、移除）
"""
from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.init.container import AppContainer
from app.services.setup.manager_service import SetupService
from app.services.setup.model_metadata_service import ModelMetadataService
from app.workers.task_manager import TaskManager

router = APIRouter()


# ─── 端點 ────────────────────────────────────────────────────────────────────

@router.get("/models")
@inject
async def get_models_status(
    model_metadata_service: ModelMetadataService = Depends(Provide[AppContainer.model_metadata]),
):
    """取得所有工具/模型的安裝/下載狀態"""
    return model_metadata_service.list_all()


class DownloadRequest(BaseModel):
    id: str


@router.post("/models/remove")
@inject
async def remove_model_item(
    request: DownloadRequest,
    setup_service: SetupService = Depends(Provide[AppContainer.setup_service]),
):
    """刪除已下載的工具/模型檔案"""
    if not request.id:
        raise HTTPException(status_code=400, detail="Missing id")
    setup_service.remove_model(request.id)
    return {"ok": True}


@router.post("/models/download")
@inject
async def download_model_item(
    request: DownloadRequest,
    setup_service: SetupService = Depends(Provide[AppContainer.setup_service]),
    task_manager: TaskManager = Depends(Provide[AppContainer.task_manager]),
):
    """提交工具/模型下載任務"""
    if not request.id:
        raise HTTPException(status_code=400, detail="Missing id")

    task_id = await task_manager.submit("setup.model_download", {"id": request.id})
    return {"task_id": task_id}
