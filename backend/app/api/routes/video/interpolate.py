"""Video interpolation API routes."""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.video.interpolate_service import InterpolateService

router = APIRouter()

class InterpolateRequest(BaseModel):
    file_id: str = Field(..., description="Input file ID")
    model: str = Field(default="v4.22", description="RIFE model variant")
    mode: str = Field(default="2x", description="Interpolation mode (2x, 4x, custom)")
    target_fps: Optional[float] = Field(default=None, description="Target FPS (custom mode)")
    output_format: str = Field(default="mp4", description="Output container format")
    video_codec: str = Field(default="h264", description="Output video codec")
    suppress_results: bool = False

class InterpolateResponse(BaseModel):
    task_id: str
    message: str = "Interpolation task submitted"

@router.get("/rife/status")
@inject
async def rife_status(
    service: InterpolateService = Depends(Provide[AppContainer.video_interpolate]),
):
    return service.get_rife_status()

@router.post("/interpolate", response_model=InterpolateResponse)
@inject
async def interpolate_video(
    request: InterpolateRequest,
    service: InterpolateService = Depends(Provide[AppContainer.video_interpolate]),
):
    task_id = await service.submit(file_id=request.file_id, model=request.model, mode=request.mode, target_fps=request.target_fps, output_format=request.output_format, video_codec=request.video_codec, suppress_results=request.suppress_results)
    return InterpolateResponse(task_id=task_id)
