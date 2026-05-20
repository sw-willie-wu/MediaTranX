from __future__ import annotations
from typing import TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.audio.volume_service import AudioVolumeService

router = APIRouter()

class AudioVolumeRequest(BaseModel):
    file_id: str = Field(..., description="Input file ID")
    volume_db: float = Field(default=0.0, ge=-30.0, le=30.0, description="Volume adjustment in dB")
    normalize: bool = Field(default=False, description="Loudness normalization")

class AudioVolumeResponse(BaseModel):
    task_id: str
    message: str = "Volume adjustment task submitted"

@router.post("/volume", response_model=AudioVolumeResponse)
@inject
async def adjust_volume(
    request: AudioVolumeRequest,
    service: AudioVolumeService = Depends(Provide[AppContainer.audio_volume]),
):
    task_id = await service.submit_volume(
        file_id=request.file_id,
        volume_db=request.volume_db,
        normalize=request.normalize,
    )
    return AudioVolumeResponse(task_id=task_id)
