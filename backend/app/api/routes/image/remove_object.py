"""
AI object removal API routes.
"""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.image.remove_object_service import ImageRemoveObjectService

router = APIRouter()


class ImageRemoveObjectRequest(BaseModel):
    file_id: str = Field(..., description="Input file ID")
    mask_data: str = Field(..., description="Mask image (base64 PNG)")
    output_dir: Optional[str] = Field(default=None)


class ImageRemoveObjectResponse(BaseModel):
    task_id: str
    message: str = "AI object removal task submitted"


@router.post("/remove-object", response_model=ImageRemoveObjectResponse)
@inject
async def remove_object(
    request: ImageRemoveObjectRequest,
    service: ImageRemoveObjectService = Depends(Provide[AppContainer.image_remove_object]),
):
    """Submit AI object removal task."""
    try:
        task_id = await service.submit_remove_object(
            file_id=request.file_id,
            mask_data=request.mask_data,
            output_dir=request.output_dir,
        )
        return ImageRemoveObjectResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
