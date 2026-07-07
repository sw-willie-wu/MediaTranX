"""
Image compression API routes.
"""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.image.compress_service import ImageCompressService

router = APIRouter()


class ImageCompressRequest(BaseModel):
    """Image compression request."""
    file_id: str = Field(..., description="Input file ID")
    strength: int = Field(default=60, ge=1, le=100, description="Compression strength (1-100)")
    # GIF-specific options
    gif_colors: Optional[int] = Field(default=None, ge=2, le=256, description="Reduce GIF palette to N colors")
    gif_frame_drop: int = Field(default=0, ge=0, description="Keep every Nth frame (0 = keep all)")
    gif_optimize_transparency: bool = Field(default=True, description="Apply transparency optimisation")
    # PNG-specific options
    png_lossy: bool = Field(default=True, description="Allow lossy PNG compression (pngquant)")
    # JPEG-specific options
    jpeg_progressive: bool = Field(default=True, description="Save as progressive JPEG")
    jpeg_keep_metadata: bool = Field(default=False, description="Preserve EXIF/metadata")
    # WebP-specific options
    webp_lossless: bool = Field(default=False, description="Use lossless WebP encoding")
    suppress_results: Optional[bool] = None


class ImageCompressResponse(BaseModel):
    """Image compression response."""
    task_id: str
    message: str = "Image compression task submitted"


@router.post("/compress", response_model=ImageCompressResponse)
@inject
async def compress_image(
    request: ImageCompressRequest,
    service: ImageCompressService = Depends(Provide[AppContainer.image_compress]),
):
    """Submit image compression task."""
    task_id = await service.submit_compress(
        file_id=request.file_id,
        strength=request.strength,
        gif_colors=request.gif_colors,
        gif_frame_drop=request.gif_frame_drop,
        gif_optimize_transparency=request.gif_optimize_transparency,
        png_lossy=request.png_lossy,
        jpeg_progressive=request.jpeg_progressive,
        jpeg_keep_metadata=request.jpeg_keep_metadata,
        webp_lossless=request.webp_lossless,
        suppress_results=request.suppress_results,
    )
    return ImageCompressResponse(task_id=task_id)
