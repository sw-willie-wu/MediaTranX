"""
Image conversion API routes.
"""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.image.convert_service import ImageConvertService

router = APIRouter()


class ImageConvertRequest(BaseModel):
    """Image conversion request."""
    file_id: str = Field(..., description="Input file ID")
    output_format: str = Field(default="png", description="Output format (png, jpg, webp, gif, bmp)")
    quality: int = Field(default=85, ge=1, le=100, description="Quality (1-100)")
    width: Optional[int] = Field(default=None, gt=0, description="Target width")
    height: Optional[int] = Field(default=None, gt=0, description="Target height")
    scale: Optional[float] = Field(default=None, gt=0, description="Scale ratio")
    coalesce: bool = Field(default=False, description="Coalesce (unoptimize) GIF frames for compatibility")
    suppress_results: Optional[bool] = None


class ImageConvertResponse(BaseModel):
    """Image conversion response."""
    task_id: str
    message: str = "Image conversion task submitted"


class ImageInfoResponse(BaseModel):
    """Image info response."""
    width: int
    height: int
    format: str
    mode: str
    file_size: int
    palette_size: Optional[int] = None


@router.get("/info/{file_id}", response_model=ImageInfoResponse)
@inject
async def get_image_info(
    file_id: str,
    service: ImageConvertService = Depends(Provide[AppContainer.image_convert]),
):
    """Get image file info."""
    info = await service.get_image_info(file_id)
    return ImageInfoResponse(**info)


@router.post("/convert", response_model=ImageConvertResponse)
@inject
async def convert_image(
    request: ImageConvertRequest,
    service: ImageConvertService = Depends(Provide[AppContainer.image_convert]),
):
    """Submit image conversion task."""
    task_id = await service.submit_convert(
        file_id=request.file_id,
        output_format=request.output_format,
        quality=request.quality,
        width=request.width,
        height=request.height,
        scale=request.scale,
        coalesce=request.coalesce,
        suppress_results=request.suppress_results,
    )
    return ImageConvertResponse(task_id=task_id)
