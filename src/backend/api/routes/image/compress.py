"""
圖片壓縮 API 路由
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.image.compress_service import get_image_compress_service

router = APIRouter()


class ImageCompressRequest(BaseModel):
    """圖片壓縮請求"""
    file_id: str = Field(..., description="輸入檔案 ID")
    output_format: str = Field(default="jpeg", description="輸出格式 (jpeg, webp, png)")
    quality: int = Field(default=80, ge=1, le=95, description="壓縮品質 (1-95)")
    output_dir: Optional[str] = Field(default=None, description="自訂輸出目錄")


class ImageCompressResponse(BaseModel):
    """圖片壓縮回應"""
    task_id: str
    message: str = "圖片壓縮任務已提交"


@router.post("/compress", response_model=ImageCompressResponse)
async def compress_image(request: ImageCompressRequest):
    """提交圖片壓縮任務"""
    try:
        service = get_image_compress_service()
        task_id = await service.submit_compress(
            file_id=request.file_id,
            output_format=request.output_format,
            quality=request.quality,
            output_dir=request.output_dir,
        )
        return ImageCompressResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
