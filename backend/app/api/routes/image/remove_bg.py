"""
去背 API 路由
"""
from typing import Optional

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.init.container import AppContainer
from app.services.image.remove_bg_service import ImageRemoveBgService

router = APIRouter()


class ImageRemoveBgRequest(BaseModel):
    file_id: str = Field(..., description="輸入檔案 ID")
    mode: str = Field(default="auto", description="去背模式 (auto/person/product/animal/anime)")
    output_dir: Optional[str] = Field(default=None)


class ImageRemoveBgResponse(BaseModel):
    task_id: str
    message: str = "去背任務已提交"


@router.post("/remove-bg", response_model=ImageRemoveBgResponse)
@inject
async def remove_bg(
    request: ImageRemoveBgRequest,
    service: ImageRemoveBgService = Depends(Provide[AppContainer.image_remove_bg]),
):
    """提交去背任務"""
    try:
        task_id = await service.submit_remove_bg(
            file_id=request.file_id,
            mode=request.mode,
            output_dir=request.output_dir,
        )
        return ImageRemoveBgResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
