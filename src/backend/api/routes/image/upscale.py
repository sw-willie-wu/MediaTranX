"""
圖片超解析 API 路由
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.image.upscale_service import get_image_upscale_service
from backend.core.ai.model_manager import get_model_manager, MODELS_REGISTRY

router = APIRouter()

# 前端 model+engine 組合 → 後端 model_id 映射
_MODEL_ID_MAP = {
    ("realesrgan", "photo"): "realesrgan-x4plus",
    ("realesrgan", "anime"): "realesrgan-x4plus",  # 未來可換成 anime 專用模型
    ("waifu2x",    "photo"): "realesrgan-x4plus",  # 暫用 realesrgan 替代
    ("waifu2x",    "anime"): "realesrgan-x4plus",
}


class ImageUpscaleRequest(BaseModel):
    """超解析請求"""
    file_id: str = Field(..., description="輸入檔案 ID")
    scale: int = Field(default=4, description="放大倍率 (2, 3, 4)")
    model: str = Field(default="photo", description="內容類型 (photo, anime)")
    engine: str = Field(default="realesrgan", description="引擎 (realesrgan, waifu2x)")
    sharpen: bool = Field(default=False, description="銳化後處理")
    output_dir: Optional[str] = Field(default=None, description="自訂輸出目錄")


class ImageUpscaleResponse(BaseModel):
    """超解析回應"""
    task_id: str
    message: str = "超解析任務已提交"


@router.get("/upscale/status")
async def get_upscale_status():
    """檢查各引擎 / 模型是否可用"""
    manager = get_model_manager()
    upscale_models = MODELS_REGISTRY.get("upscale", {})
    return {
        "realesrgan": manager.get_model_path("upscale", "realesrgan-x4plus") is not None,
        "waifu2x": False,  # ncnn-vulkan 已棄用，純 Python 版尚未加入
        "available_models": list(upscale_models.keys()),
    }


@router.post("/upscale", response_model=ImageUpscaleResponse)
async def upscale_image(request: ImageUpscaleRequest):
    """提交圖片超解析任務"""
    try:
        # 將前端 engine+model 組合轉換為 model_id
        model_id = _MODEL_ID_MAP.get(
            (request.engine, request.model),
            "realesrgan-x4plus"  # 預設值
        )

        service = get_image_upscale_service()
        task_id = await service.submit_upscale(
            file_id=request.file_id,
            model_id=model_id,
            scale=request.scale,
            sharpen=request.sharpen,
            output_dir=request.output_dir,
        )
        return ImageUpscaleResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
