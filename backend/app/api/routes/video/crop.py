"""Video crop API routes."""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.video.crop_service import VideoCropService

router = APIRouter()


class VideoCropRequest(BaseModel):
    file_id: str = Field(..., description="Input file ID")
    x: int = Field(default=0, ge=0)
    y: int = Field(default=0, ge=0)
    width: int = Field(..., gt=0)
    height: int = Field(..., gt=0)
    suppress_results: Optional[bool] = None


class VideoCropResponse(BaseModel):
    task_id: str
    message: str = "Video crop task submitted"


@router.post("/crop", response_model=VideoCropResponse)
@inject
async def crop_video(
    request: VideoCropRequest,
    service: VideoCropService = Depends(Provide[AppContainer.video_crop]),
):
    task_id = await service.submit_crop(
        file_id=request.file_id,
        x=request.x, y=request.y,
        width=request.width, height=request.height,
        suppress_results=request.suppress_results,
    )
    return VideoCropResponse(task_id=task_id)
