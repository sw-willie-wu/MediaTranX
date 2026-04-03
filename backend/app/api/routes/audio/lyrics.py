"""
歌詞提取 API 路由
"""
import logging
from typing import Optional

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.init.container import AppContainer
from app.services.audio.lyrics_service import AudioLyricsService

logger = logging.getLogger(__name__)

router = APIRouter()


class LyricsRequest(BaseModel):
    file_id: str = Field(..., description="輸入檔案 ID")
    whisper_size: str = Field(default="medium", description="Whisper 模型大小")
    align: bool = Field(default=False, description="啟用 Wav2Vec2 精準對齊")
    translate: bool = Field(default=False, description="是否翻譯歌詞")
    target_lang: Optional[str] = Field(default=None, description="翻譯目標語言")
    translate_model_type: str = Field(default="translategemma", description="翻譯模型類型")
    translate_model_size: str = Field(default="4b", description="翻譯模型大小")
    translate_quantization: Optional[str] = Field(default=None, description="翻譯模型量化精度")
    translate_remote: bool = Field(default=False, description="使用雲端翻譯")
    translate_provider: Optional[str] = Field(default=None, description="雲端服務提供者")
    translate_conn_id: Optional[int] = Field(default=None, description="雲端連線 ID")
    translate_remote_model: Optional[str] = Field(default=None, description="雲端模型 ID")
    output_format: str = Field(default="lrc", description="輸出格式 (lrc, txt)")
    output_dir: Optional[str] = Field(default=None, description="自訂輸出目錄")
    output_filename: Optional[str] = Field(default=None, description="自訂輸出檔名")


class LyricsResponse(BaseModel):
    task_id: str
    message: str = "歌詞提取任務已提交"


@router.post("/lyrics", response_model=LyricsResponse)
@inject
async def extract_lyrics(
    request: LyricsRequest,
    service: AudioLyricsService = Depends(Provide[AppContainer.audio_lyrics]),
):
    try:
        task_id = await service.submit_lyrics(
            file_id=request.file_id,
            whisper_size=request.whisper_size,
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
            output_format=request.output_format,
            output_dir=request.output_dir,
            output_filename=request.output_filename,
        )
        return LyricsResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
