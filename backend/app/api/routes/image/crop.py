"""
Image crop API routes.
"""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.image.crop_service import ImageCropService

router = APIRouter()


class ImageCropRequest(BaseModel):
    """Image crop request."""
    file_id: str = Field(..., description="Input file ID")
    x: int = Field(default=0, description="Crop start X coordinate")
    y: int = Field(default=0, description="Crop start Y coordinate")
    width: int = Field(..., gt=0, description="Crop width")
    height: int = Field(..., gt=0, description="Crop height")
    suppress_results: Optional[bool] = None


class ImageCropResponse(BaseModel):
    """Image crop response."""
    task_id: str
    message: str = "Image crop task submitted"


@router.post("/crop", response_model=ImageCropResponse)
@inject
async def crop_image(
    request: ImageCropRequest,
    service: ImageCropService = Depends(Provide[AppContainer.image_crop]),
):
    """Submit image crop task."""
    task_id = await service.submit_crop(
        file_id=request.file_id,
        x=request.x,
        y=request.y,
        width=request.width,
        height=request.height,
        suppress_results=request.suppress_results,
    )
    return ImageCropResponse(task_id=task_id)
