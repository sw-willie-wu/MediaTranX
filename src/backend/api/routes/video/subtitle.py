"""
字幕提取 API 路由
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.video.subtitle_service import get_subtitle_service

router = APIRouter()


class SubtitleGenerateRequest(BaseModel):
    """字幕生成請求"""
    file_id: str = Field(..., description="輸入影片檔案 ID")
    language: Optional[str] = Field(
        default=None,
        description="語言代碼 (None=自動偵測, zh=中文, en=英文, ja=日文...)"
    )
    model_size: str = Field(
        default="medium",
        description="模型大小 (tiny, base, small, medium, large-v3)"
    )
    output_format: str = Field(
        default="srt",
        description="輸出格式 (srt, vtt)"
    )
    output_dir: Optional[str] = Field(default=None, description="自訂輸出目錄")
    output_filename: Optional[str] = Field(default=None, description="自訂輸出檔名")


class SubtitleGenerateResponse(BaseModel):
    """字幕生成回應"""
    task_id: str
    message: str = "字幕生成任務已提交"


class WhisperStatusResponse(BaseModel):
    """Whisper 模型狀態回應"""
    available: bool
    model_size: str
    model_downloaded: bool
    device: str
    compute_type: str
    device_name: str


@router.get("/whisper/status", response_model=WhisperStatusResponse)
async def get_whisper_status(model_size: str = "medium"):
    """
    查詢 Whisper 模型狀態

    - **model_size**: 要查詢的模型大小 (預設 medium)
    """
    try:
        service = get_subtitle_service()
        status = service.get_model_status(model_size)
        return WhisperStatusResponse(**status)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/subtitle/generate", response_model=SubtitleGenerateResponse)
async def generate_subtitle(request: SubtitleGenerateRequest):
    """
    提交字幕生成任務

    使用 faster-whisper 從影片中提取語音並生成字幕檔。
    首次使用時會自動下載指定大小的模型。

    支援的選項：
    - **language**: None (自動偵測), zh, en, ja, ko, fr, de, es...
    - **model_size**: tiny, base, small, medium (推薦), large-v3
    - **output_format**: srt (預設), vtt
    """
    try:
        service = get_subtitle_service()
        task_id = await service.submit_subtitle_generate(
            file_id=request.file_id,
            language=request.language,
            model_size=request.model_size,
            output_format=request.output_format,
            output_dir=request.output_dir,
            output_filename=request.output_filename,
        )
        return SubtitleGenerateResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
