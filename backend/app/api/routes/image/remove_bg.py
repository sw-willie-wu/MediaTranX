"""
Background removal API routes.
"""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.image.remove_bg_service import ImageRemoveBgService

router = APIRouter()


class ImageRemoveBgRequest(BaseModel):
    file_id: str = Field(..., description="Input file ID")
    mode: str = Field(default="auto", description="Removal mode (auto/person/product/animal/anime)")


class ImageRemoveBgResponse(BaseModel):
    task_id: str
    message: str = "Background removal task submitted"


@router.post("/remove-bg", response_model=ImageRemoveBgResponse)
@inject
async def remove_bg(
    request: ImageRemoveBgRequest,
    service: ImageRemoveBgService = Depends(Provide[AppContainer.image_remove_bg]),
):
    """Submit background removal task."""
    task_id = await service.submit_remove_bg(
        file_id=request.file_id,
        mode=request.mode,
    )
    return ImageRemoveBgResponse(task_id=task_id)
