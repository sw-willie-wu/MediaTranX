from typing import Optional
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from app.services.audio.transcribe_service import get_audio_transcribe_service

router = APIRouter()

class AudioTranscribeRequest(BaseModel):
    file_id: str = Field(..., description="輸入檔案 ID")
    language: Optional[str] = Field(default=None, description="語言代碼，None=自動偵測")
    model_size: str = Field(default="medium", description="Whisper 模型大小")
    output_format: str = Field(default="txt", description="輸出格式 (txt, srt)")

class AudioTranscribeResponse(BaseModel):
    task_id: str
    message: str = "逐字稿轉譯任務已提交"

@router.get("/transcribe/languages")
async def get_transcribe_languages():
    """取得 Whisper 支援的語言列表"""
    from app.engine.ai.base.translate import WHISPER_LANGUAGE_OPTIONS
    return WHISPER_LANGUAGE_OPTIONS


@router.get("/transcribe/status")
async def get_transcribe_status(model_size: str = "medium"):
    try:
        service = get_audio_transcribe_service()
        return service.get_model_status(model_size)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/transcribe", response_model=AudioTranscribeResponse)
async def transcribe_audio(request: AudioTranscribeRequest):
    try:
        service = get_audio_transcribe_service()
        task_id = await service.submit_transcribe(
            file_id=request.file_id,
            language=request.language,
            model_size=request.model_size,
            output_format=request.output_format,
        )
        return AudioTranscribeResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
