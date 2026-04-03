import logging
from typing import Optional

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.init.container import AppContainer
from app.services.audio.transcribe_service import AudioTranscribeService
from app.services.setup.language_service import LanguageService

logger = logging.getLogger(__name__)

router = APIRouter()

class AudioTranscribeRequest(BaseModel):
    file_id: str = Field(..., description="輸入檔案 ID")
    language: Optional[str] = Field(default=None, description="語言代碼，None=自動偵測")
    model_size: str = Field(default="medium", description="Whisper 模型大小")
    output_format: str = Field(default="txt", description="輸出格式 (txt, srt)")
    vocal_separation: bool = Field(default=False, description="人聲分離前處理")
    align: bool = Field(default=False, description="精準對齊")
    translate: bool = Field(default=False, description="翻譯")
    target_lang: Optional[str] = Field(default=None, description="翻譯目標語言")
    translate_model_type: str = Field(default="translategemma", description="翻譯模型類型")
    translate_model_size: str = Field(default="4b", description="翻譯模型大小")
    translate_quantization: Optional[str] = Field(default=None, description="翻譯模型量化精度")
    translate_remote: bool = Field(default=False, description="使用雲端翻譯")
    translate_provider: Optional[str] = Field(default=None, description="雲端服務提供者")
    translate_conn_id: Optional[int] = Field(default=None, description="雲端連線 ID")
    translate_remote_model: Optional[str] = Field(default=None, description="雲端模型 ID")
    summarize: bool = Field(default=False, description="大綱整理")
    summarize_model_type: str = Field(default="qwen3", description="大綱模型類型")
    summarize_model_size: str = Field(default="4b", description="大綱模型大小")
    summarize_quantization: Optional[str] = Field(default=None, description="大綱模型量化精度")
    summarize_remote: bool = Field(default=False, description="使用雲端大綱模型")
    summarize_provider: Optional[str] = Field(default=None, description="雲端服務提供者")
    summarize_conn_id: Optional[int] = Field(default=None, description="雲端連線 ID")
    summarize_remote_model: Optional[str] = Field(default=None, description="雲端模型 ID")
    output_dir: Optional[str] = Field(default=None, description="自訂輸出目錄")
    output_filename: Optional[str] = Field(default=None, description="自訂輸出檔名")

class AudioTranscribeResponse(BaseModel):
    task_id: str
    message: str = "逐字稿轉譯任務已提交"

@router.get("/transcribe/languages")
@inject
async def get_transcribe_languages(
    language_service: LanguageService = Depends(Provide[AppContainer.language_service]),
):
    """取得 Whisper 支援的語言列表"""
    return language_service.get_whisper_languages()


@router.get("/transcribe/status")
@inject
async def get_transcribe_status(
    model_size: str = "medium",
    service: AudioTranscribeService = Depends(Provide[AppContainer.audio_transcribe]),
):
    try:
        return service.get_model_status(model_size)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/transcribe", response_model=AudioTranscribeResponse)
@inject
async def transcribe_audio(
    request: AudioTranscribeRequest,
    service: AudioTranscribeService = Depends(Provide[AppContainer.audio_transcribe]),
):
    try:
        task_id = await service.submit_transcribe(
            file_id=request.file_id,
            language=request.language,
            model_size=request.model_size,
            output_format=request.output_format,
            vocal_separation=request.vocal_separation,
            align=request.align,
            translate=request.translate,
            target_lang=request.target_lang,
            translate_model_type=request.translate_model_type,
            translate_model_size=request.translate_model_size,
            translate_quantization=request.translate_quantization,
            translate_remote=request.translate_remote,
            translate_provider=request.translate_provider,
            translate_conn_id=request.translate_conn_id,
            translate_remote_model=request.translate_remote_model,
            summarize=request.summarize,
            summarize_model_type=request.summarize_model_type,
            summarize_model_size=request.summarize_model_size,
            summarize_quantization=request.summarize_quantization,
            summarize_remote=request.summarize_remote,
            summarize_provider=request.summarize_provider,
            summarize_conn_id=request.summarize_conn_id,
            summarize_remote_model=request.summarize_remote_model,
            output_dir=request.output_dir,
            output_filename=request.output_filename,
        )
        return AudioTranscribeResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
