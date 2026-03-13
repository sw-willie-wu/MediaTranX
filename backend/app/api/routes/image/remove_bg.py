"""
去背 API 路由
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.image.remove_bg_service import get_image_remove_bg_service

router = APIRouter()


class ImageRemoveBgRequest(BaseModel):
    file_id: str = Field(..., description="輸入檔案 ID")
    mode: str = Field(default="auto", description="去背模式 (auto/person/product/animal)")
    output_dir: Optional[str] = Field(default=None)


class ImageRemoveBgResponse(BaseModel):
    task_id: str
    message: str = "去背任務已提交"


@router.post("/remove-bg", response_model=ImageRemoveBgResponse)
async def remove_bg(request: ImageRemoveBgRequest):
    """提交去背任務"""
    try:
        service = get_image_remove_bg_service()
        task_id = await service.submit_remove_bg(
            file_id=request.file_id,
            mode=request.mode,
            output_dir=request.output_dir,
        )
        return ImageRemoveBgResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
