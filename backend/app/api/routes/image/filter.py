"""
圖片濾鏡 API 路由
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.image.filter_service import get_image_filter_service

router = APIRouter()


class ImageFilterRequest(BaseModel):
    """圖片濾鏡請求"""
    file_id: str = Field(..., description="輸入檔案 ID")
    brightness: float = Field(default=1.0, description="亮度 (1.0 = 不變)")
    contrast: float = Field(default=1.0, description="對比度 (1.0 = 不變)")
    saturation: float = Field(default=1.0, description="飽和度 (1.0 = 不變)")
    sharpness: float = Field(default=1.0, description="銳利度 (1.0 = 不變)")
    grayscale: bool = Field(default=False, description="轉換為灰階")
    output_dir: Optional[str] = Field(default=None, description="自訂輸出目錄")


class ImageFilterResponse(BaseModel):
    """圖片濾鏡回應"""
    task_id: str
    message: str = "圖片濾鏡任務已提交"


@router.post("/filter", response_model=ImageFilterResponse)
async def filter_image(request: ImageFilterRequest):
    """提交圖片濾鏡任務"""
    try:
        service = get_image_filter_service()
        task_id = await service.submit_filter(
            file_id=request.file_id,
            brightness=request.brightness,
            contrast=request.contrast,
            saturation=request.saturation,
            sharpness=request.sharpness,
            grayscale=request.grayscale,
            output_dir=request.output_dir,
        )
        return ImageFilterResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
