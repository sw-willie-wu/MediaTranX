"""
Image filter/adjustment API routes.
"""
from __future__ import annotations
import asyncio
from typing import TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.image.filter_service import ImageFilterService

router = APIRouter()


class ImageFilterRequest(BaseModel):
    """Image filter/adjustment request."""
    file_id:    str   = Field(...,         description="Input file ID")
    brightness: float = Field(default=1.0, description="Brightness (1.0 = unchanged)")
    contrast:   float = Field(default=1.0, description="Contrast (1.0 = unchanged)")
    saturation: float = Field(default=1.0, description="Saturation (1.0 = unchanged)")
    hue:        float = Field(default=0.0, description="Hue rotation angle (-180 ~ 180)")
    sharpness:  float = Field(default=1.0, description="Sharpness (1.0 = unchanged)")
    warmth:     float = Field(default=0.0, description="Color temperature (-1.0 cool ~ 1.0 warm)")
    grayscale:  float = Field(default=0.0,   description="Grayscale intensity (0.0 = unchanged, 1.0 = full grayscale)")
    sepia:      float = Field(default=0.0, description="Sepia tone intensity (0.0 ~ 1.0)")
    invert:     float = Field(default=0.0, description="Invert intensity (0.0 ~ 1.0)")
    blur:       float = Field(default=0.0, description="Blur radius (px)")
    vignette:   float = Field(default=0.0, description="Vignette intensity (0.0 ~ 1.0)")


class ImageFilterResponse(BaseModel):
    """Image filter response."""
    task_id: str
    message: str = "Image filter task submitted"


class ImageFilterPreviewRequest(BaseModel):
    """Image filter quick preview request (synchronous, reduced resolution)."""
    file_id:    str   = Field(...,         description="Input file ID")
    brightness: float = Field(default=1.0)
    contrast:   float = Field(default=1.0)
    saturation: float = Field(default=1.0)
    hue:        float = Field(default=0.0)
    sharpness:  float = Field(default=1.0)
    warmth:     float = Field(default=0.0)
    grayscale:  float = Field(default=0.0)
    sepia:      float = Field(default=0.0)
    invert:     float = Field(default=0.0)
    blur:       float = Field(default=0.0)
    vignette:   float = Field(default=0.0)


class ImageFilterPreviewResponse(BaseModel):
    """Preview response, returns base64 JPEG."""
    preview: str  # data:image/jpeg;base64,...


@router.post("/filter", response_model=ImageFilterResponse)
@inject
async def filter_image(
    request: ImageFilterRequest,
    service: ImageFilterService = Depends(Provide[AppContainer.image_filter]),
):
    """Submit image filter task."""
    task_id = await service.submit_filter(
        file_id=request.file_id,
        brightness=request.brightness,
        contrast=request.contrast,
        saturation=request.saturation,
        hue=request.hue,
        sharpness=request.sharpness,
        warmth=request.warmth,
        grayscale=request.grayscale,
        sepia=request.sepia,
        invert=request.invert,
        blur=request.blur,
        vignette=request.vignette,
    )
    return ImageFilterResponse(task_id=task_id)


@router.post("/filter/preview", response_model=ImageFilterPreviewResponse)
@inject
async def preview_filter(
    request: ImageFilterPreviewRequest,
    service: ImageFilterService = Depends(Provide[AppContainer.image_filter]),
):
    """Synchronously generate a preview image (reduced resolution, returns base64 data URI)."""
    params = request.model_dump(exclude={"file_id"})
    data_uri = await asyncio.to_thread(
        service.generate_preview,
        file_id=request.file_id,
        params=params,
    )
    return ImageFilterPreviewResponse(preview=data_uri)
