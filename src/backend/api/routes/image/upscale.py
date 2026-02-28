"""
圖片超解析 API 路由
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.image.upscale_service import get_image_upscale_service

router = APIRouter()


class ImageUpscaleRequest(BaseModel):
    """超解析請求"""
    file_id: str = Field(..., description="輸入檔案 ID")
    scale: int = Field(default=4, description="放大倍率 (2, 3, 4)")
    model: str = Field(default="photo", description="模型 (photo, anime)")
    engine: str = Field(default="realesrgan", description="引擎 (realesrgan, waifu2x)")
    sharpen: bool = Field(default=False, description="銳化後處理")
    output_dir: Optional[str] = Field(default=None, description="自訂輸出目錄")
    output_filename: Optional[str] = Field(default=None, description="自訂輸出檔名")


class ImageUpscaleResponse(BaseModel):
    """超解析回應"""
    task_id: str
    message: str = "超解析任務已提交"


@router.get("/upscale/status")
async def get_upscale_status():
    """檢查各引擎是否可用"""
    service = get_image_upscale_service()
    return {
        "realesrgan": service.is_realesrgan_available(),
        "waifu2x": service.is_waifu2x_available(),
    }


@router.post("/upscale", response_model=ImageUpscaleResponse)
async def upscale_image(request: ImageUpscaleRequest):
    """提交圖片超解析任務"""
    try:
        service = get_image_upscale_service()
        task_id = await service.submit_upscale(
            file_id=request.file_id,
            scale=request.scale,
            model=request.model,
            engine=request.engine,
            sharpen=request.sharpen,
            output_dir=request.output_dir,
            output_filename=request.output_filename,
        )
        return ImageUpscaleResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
