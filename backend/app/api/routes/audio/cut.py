from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.audio.cut_service import AudioCutService

router = APIRouter()

class AudioCutRequest(BaseModel):
    file_id: str = Field(..., description="Input file ID")
    start_time: str = Field(default="00:00:00", description="Start time HH:MM:SS")
    end_time: str = Field(..., description="End time HH:MM:SS")
    suppress_results: Optional[bool] = None

class AudioCutResponse(BaseModel):
    task_id: str
    message: str = "Audio cut task submitted"

@router.post("/cut", response_model=AudioCutResponse)
@inject
async def cut_audio(
    request: AudioCutRequest,
    service: AudioCutService = Depends(Provide[AppContainer.audio_cut]),
):
    task_id = await service.submit_cut(
        file_id=request.file_id,
        start_time=request.start_time,
        end_time=request.end_time,
        suppress_results=request.suppress_results,
    )
    return AudioCutResponse(task_id=task_id)
