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
    model_id: str = Field(default="realesrgan-x4plus", description="模型 ID（如 realesrgan-x4plus）")
    scale: int = Field(default=4, description="放大倍率 (2, 3, 4)")
    sharpen: bool = Field(default=False, description="銳化後處理")
    face_fix: bool = Field(default=False, description="人臉修復後處理")
    face_restore_model_id: Optional[str] = Field(default=None, description="人臉修復模型 ID（如 codeformer-default）")
    face_restore_fidelity: float = Field(default=0.7, description="CodeFormer 自然度 (0=強修復, 1=保留原貌)")
    face_restore_upscale: int = Field(default=2, description="GFPGAN 放大倍率 (1/2/4)")
    output_dir: Optional[str] = Field(default=None, description="自訂輸出目錄")


class ImageUpscaleResponse(BaseModel):
    """超解析回應"""
    task_id: str
    message: str = "超解析任務已提交"


@router.post("/upscale", response_model=ImageUpscaleResponse)
async def upscale_image(request: ImageUpscaleRequest):
    """提交圖片超解析任務"""
    try:
        service = get_image_upscale_service()
        task_id = await service.submit_upscale(
            file_id=request.file_id,
            model_id=request.model_id,
            scale=request.scale,
            sharpen=request.sharpen,
            face_fix=request.face_fix,
            face_restore_model_id=request.face_restore_model_id,
            face_restore_fidelity=request.face_restore_fidelity,
            face_restore_upscale=request.face_restore_upscale,
            output_dir=request.output_dir,
        )
        return ImageUpscaleResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
