"""
Image super-resolution API routes.
"""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.image.upscale_service import ImageUpscaleService

router = APIRouter()


class ImageUpscaleRequest(BaseModel):
    """Super-resolution request."""
    file_id: str = Field(..., description="Input file ID")
    model_id: str = Field(default="realesrgan-x4plus", description="Model ID (e.g. realesrgan-x4plus)")
    scale: int = Field(default=4, description="Upscale factor (2, 3, 4)")
    sharpen: bool = Field(default=False, description="Sharpen post-processing")
    face_fix: bool = Field(default=False, description="Face restoration post-processing")
    face_restore_model_id: Optional[str] = Field(default=None, description="Face restoration model ID (e.g. gfpgan-v1.4)")
    face_restore_upscale: int = Field(default=2, description="GFPGAN upscale factor (1/2/4)")


class ImageUpscaleResponse(BaseModel):
    """Super-resolution response."""
    task_id: str
    message: str = "Super-resolution task submitted"


@router.post("/upscale", response_model=ImageUpscaleResponse)
@inject
async def upscale_image(
    request: ImageUpscaleRequest,
    service: ImageUpscaleService = Depends(Provide[AppContainer.image_upscale]),
):
    """Submit image super-resolution task."""
    task_id = await service.submit_upscale(
        file_id=request.file_id,
        model_id=request.model_id,
        scale=request.scale,
        sharpen=request.sharpen,
        face_fix=request.face_fix,
        face_restore_model_id=request.face_restore_model_id,
        face_restore_upscale=request.face_restore_upscale,
    )
    return ImageUpscaleResponse(task_id=task_id)
