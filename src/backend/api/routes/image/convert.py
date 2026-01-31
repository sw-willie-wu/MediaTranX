"""
圖片轉檔 API 路由
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.image.convert_service import get_image_convert_service

router = APIRouter()


class ImageConvertRequest(BaseModel):
    """圖片轉檔請求"""
    file_id: str = Field(..., description="輸入檔案 ID")
    output_format: str = Field(default="png", description="輸出格式 (png, jpg, webp, gif, bmp)")
    quality: int = Field(default=85, ge=1, le=100, description="品質 (1-100)")
    width: Optional[int] = Field(default=None, gt=0, description="目標寬度")
    height: Optional[int] = Field(default=None, gt=0, description="目標高度")
    scale: Optional[float] = Field(default=None, gt=0, description="縮放比例")
    output_dir: Optional[str] = Field(default=None, description="自訂輸出目錄")
    output_filename: Optional[str] = Field(default=None, description="自訂輸出檔名")


class ImageConvertResponse(BaseModel):
    """圖片轉檔回應"""
    task_id: str
    message: str = "圖片轉檔任務已提交"


class ImageInfoResponse(BaseModel):
    """圖片資訊回應"""
    width: int
    height: int
    format: str
    mode: str
    file_size: int


@router.get("/info/{file_id}", response_model=ImageInfoResponse)
async def get_image_info(file_id: str):
    """取得圖片檔案資訊"""
    try:
        service = get_image_convert_service()
        info = await service.get_image_info(file_id)
        return ImageInfoResponse(**info)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/convert", response_model=ImageConvertResponse)
async def convert_image(request: ImageConvertRequest):
    """提交圖片轉檔任務"""
    try:
        service = get_image_convert_service()
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
