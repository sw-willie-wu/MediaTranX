"""
AI 物件移除 API 路由
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.image.remove_object_service import get_image_remove_object_service

router = APIRouter()


class ImageRemoveObjectRequest(BaseModel):
    file_id: str = Field(..., description="輸入檔案 ID")
    mask_data: str = Field(..., description="遮罩圖片（base64 PNG）")
    output_dir: Optional[str] = Field(default=None)


class ImageRemoveObjectResponse(BaseModel):
    task_id: str
    message: str = "AI 物件移除任務已提交"


@router.post("/remove-object", response_model=ImageRemoveObjectResponse)
async def remove_object(request: ImageRemoveObjectRequest):
    """提交 AI 物件移除任務"""
    try:
        service = get_image_remove_object_service()
        task_id = await service.submit_remove_object(
            file_id=request.file_id,
            mask_data=request.mask_data,
            output_dir=request.output_dir,
        )
        return ImageRemoveObjectResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
