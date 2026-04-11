"""
Image conversion API routes.
"""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException
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
    output_dir: Optional[str] = Field(default=None, description="Custom output directory")
    output_filename: Optional[str] = Field(default=None, description="Custom output filename")


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


@router.get("/info/{file_id}", response_model=ImageInfoResponse)
@inject
async def get_image_info(
    file_id: str,
    service: ImageConvertService = Depends(Provide[AppContainer.image_convert]),
):
    """Get image file info."""
    try:
        info = await service.get_image_info(file_id)
        return ImageInfoResponse(**info)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/convert", response_model=ImageConvertResponse)
@inject
async def convert_image(
    request: ImageConvertRequest,
    service: ImageConvertService = Depends(Provide[AppContainer.image_convert]),
):
    """Submit image conversion task."""
    try:
        task_id = await service.submit_convert(
            file_id=request.file_id,
            output_format=request.output_format,
            quality=request.quality,
            width=request.width,
            height=request.height,
            scale=request.scale,
            output_dir=request.output_dir,
            output_filename=request.output_filename,
        )
        return ImageConvertResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
