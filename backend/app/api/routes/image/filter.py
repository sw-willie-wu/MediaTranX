"""
圖片調整 API 路由
"""
import asyncio
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.image.filter_service import get_image_filter_service

router = APIRouter()


class ImageFilterRequest(BaseModel):
    """圖片調整請求"""
    file_id:    str   = Field(...,         description="輸入檔案 ID")
    brightness: float = Field(default=1.0, description="亮度 (1.0 = 不變)")
    contrast:   float = Field(default=1.0, description="對比度 (1.0 = 不變)")
    saturation: float = Field(default=1.0, description="飽和度 (1.0 = 不變)")
    hue:        float = Field(default=0.0, description="色相旋轉角度 (-180 ~ 180)")
    sharpness:  float = Field(default=1.0, description="銳利度 (1.0 = 不變)")
    warmth:     float = Field(default=0.0, description="色溫 (-1.0 冷 ~ 1.0 暖)")
    grayscale:  float = Field(default=0.0,   description="灰階強度 (0.0 = 不變，1.0 = 完全灰階)")
    sepia:      float = Field(default=0.0, description="復古色調強度 (0.0 ~ 1.0)")
    invert:     float = Field(default=0.0, description="負片強度 (0.0 ~ 1.0)")
    blur:       float = Field(default=0.0, description="模糊半徑 (px)")
    vignette:   float = Field(default=0.0, description="暈影強度 (0.0 ~ 1.0)")
    output_dir: Optional[str] = Field(default=None, description="自訂輸出目錄")


class ImageFilterResponse(BaseModel):
    """圖片調整回應"""
    task_id: str
    message: str = "圖片調整任務已提交"


class ImageFilterPreviewRequest(BaseModel):
    """圖片調整快速預覽請求（同步，降解析度）"""
    file_id:    str   = Field(...,         description="輸入檔案 ID")
    brightness: float = Field(default=1.0)
    contrast:   float = Field(default=1.0)
    saturation: float = Field(default=1.0)
    hue:        float = Field(default=0.0)
    sharpness:  float = Field(default=1.0)
    warmth:     float = Field(default=0.0)
    grayscale:  float = Field(default=0.0)
    sepia:      float = Field(default=0.0)
    invert:     float = Field(default=0.0)
    blur:       float = Field(default=0.0)
    vignette:   float = Field(default=0.0)


class ImageFilterPreviewResponse(BaseModel):
    """預覽回應，回傳 base64 JPEG"""
    preview: str  # data:image/jpeg;base64,...


@router.post("/filter", response_model=ImageFilterResponse)
async def filter_image(request: ImageFilterRequest):
    """提交圖片調整任務"""
    try:
        service = get_image_filter_service()
        task_id = await service.submit_filter(
            file_id=request.file_id,
            brightness=request.brightness,
            contrast=request.contrast,
            saturation=request.saturation,
            hue=request.hue,
            sharpness=request.sharpness,
            warmth=request.warmth,
            grayscale=request.grayscale,
            sepia=request.sepia,
            invert=request.invert,
            blur=request.blur,
            vignette=request.vignette,
            output_dir=request.output_dir,
        )
        return ImageFilterResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/filter/preview", response_model=ImageFilterPreviewResponse)
async def preview_filter(request: ImageFilterPreviewRequest):
    """同步生成預覽圖（降解析度，回傳 base64 JPEG）"""
    try:
        service = get_image_filter_service()
        params = request.model_dump(exclude={"file_id"})
        base64_data = await asyncio.to_thread(
            service.generate_preview,
            file_id=request.file_id,
            params=params,
        )
        return ImageFilterPreviewResponse(preview=f"data:image/jpeg;base64,{base64_data}")
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
