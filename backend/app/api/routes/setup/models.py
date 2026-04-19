"""
Model management routes (list, download, remove).
"""
from __future__ import annotations
from typing import TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.setup.manager_service import SetupService
    from app.services.setup.model_metadata_service import ModelMetadataService

router = APIRouter()


# ─── Endpoints ────────────────────────────────────────────────────────────────

@router.get("/models")
@inject
async def get_models_status(
    model_metadata_service: ModelMetadataService = Depends(Provide[AppContainer.model_metadata]),
):
    """Get installation/download status of all tools/models."""
    return model_metadata_service.list_all()


class DownloadRequest(BaseModel):
    id: str = Field(..., min_length=1, description="Model/tool identifier")


@router.post("/models/remove")
@inject
async def remove_model_item(
    request: DownloadRequest,
    setup_service: SetupService = Depends(Provide[AppContainer.setup_service]),
):
    """Delete downloaded tool/model files."""
    setup_service.remove_model(request.id)
    return {"ok": True}


@router.post("/models/download")
@inject
async def download_model_item(
    request: DownloadRequest,
    setup_service: SetupService = Depends(Provide[AppContainer.setup_service]),
):
    """Submit tool/model download task."""
    task_id = await setup_service.submit_model_download(request.id)
    return {"task_id": task_id}
