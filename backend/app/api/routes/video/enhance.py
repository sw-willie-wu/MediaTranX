"""Video enhancement API routes."""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.video.enhance_service import EnhanceService

router = APIRouter()

class EnhanceRequest(BaseModel):
    file_id: str = Field(..., description="Input file ID")
    model: str = Field(default="realesrgan", description="Enhancement model family")
    variant: str = Field(default="x4plus", description="Model variant")
    output_format: str = Field(default="mp4", description="Output container format")
    video_codec: str = Field(default="h264", description="Output video codec")
    suppress_results: Optional[bool] = None

class EnhanceResponse(BaseModel):
    task_id: str
    message: str = "Video enhancement task submitted"

@router.post("/enhance", response_model=EnhanceResponse)
@inject
async def enhance_video(
    request: EnhanceRequest,
    service: EnhanceService = Depends(Provide[AppContainer.video_enhance]),
):
    task_id = await service.submit(file_id=request.file_id, model=request.model, variant=request.variant, output_format=request.output_format, video_codec=request.video_codec, suppress_results=request.suppress_results)
    return EnhanceResponse(task_id=task_id)
