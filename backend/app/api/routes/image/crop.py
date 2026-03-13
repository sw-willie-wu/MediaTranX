"""
圖片裁切 API 路由
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.image.crop_service import get_image_crop_service

router = APIRouter()


class ImageCropRequest(BaseModel):
    """圖片裁切請求"""
    file_id: str = Field(..., description="輸入檔案 ID")
    x: int = Field(default=0, description="裁切起始 X 座標")
    y: int = Field(default=0, description="裁切起始 Y 座標")
    width: int = Field(..., gt=0, description="裁切寬度")
    height: int = Field(..., gt=0, description="裁切高度")
    output_dir: Optional[str] = Field(default=None, description="自訂輸出目錄")


class ImageCropResponse(BaseModel):
    """圖片裁切回應"""
    task_id: str
    message: str = "圖片裁切任務已提交"


@router.post("/crop", response_model=ImageCropResponse)
async def crop_image(request: ImageCropRequest):
    """提交圖片裁切任務"""
    try:
        service = get_image_crop_service()
        task_id = await service.submit_crop(
            file_id=request.file_id,
            x=request.x,
            y=request.y,
            width=request.width,
            height=request.height,
            output_dir=request.output_dir,
        )
        return ImageCropResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
