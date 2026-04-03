"""
音訊轉檔 API 路由
"""
import logging
from typing import Optional

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.init.container import AppContainer
from app.services.audio.transcode_service import AudioTranscodeService

logger = logging.getLogger(__name__)

router = APIRouter()


_FORMAT_CODEC_MAP: dict[str, str] = {
    "mp3":  "libmp3lame",
    "aac":  "aac",
    "m4a":  "aac",
    "ogg":  "libvorbis",
    "opus": "libopus",
    "wma":  "wmav2",
    "flac": "flac",
    "wav":  "pcm_s16le",
    "alac": "alac",
    "aiff": "pcm_s16be",
}


class AudioTranscodeRequest(BaseModel):
    """音訊轉檔請求"""
    file_id: str = Field(..., description="輸入檔案 ID")
    output_format: str = Field(default="mp3", description="輸出格式")
    audio_bitrate: str = Field(default="192k", description="位元率")
    sample_rate: Optional[int] = Field(default=None, description="取樣率")
    channels: Optional[int] = Field(default=None, ge=1, le=2, description="聲道數")
    output_dir: Optional[str] = Field(default=None, description="自訂輸出目錄")
    output_filename: Optional[str] = Field(default=None, description="自訂輸出檔名")


class AudioTranscodeResponse(BaseModel):
    """音訊轉檔回應"""
    task_id: str
    message: str = "音訊轉檔任務已提交"


class AudioInfoResponse(BaseModel):
    """音訊資訊回應"""
    duration: float
    sample_rate: int
    channels: int
    codec: str
    bitrate: int
    file_size: int


@router.get("/info/{file_id}", response_model=AudioInfoResponse)
@inject
async def get_audio_info(
    file_id: str,
    service: AudioTranscodeService = Depends(Provide[AppContainer.audio_transcode]),
):
    """取得音訊檔案資訊"""
    try:
        info = await service.get_audio_info(file_id)
        return AudioInfoResponse(**info)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/transcode", response_model=AudioTranscodeResponse)
@inject
async def transcode_audio(
    request: AudioTranscodeRequest,
    service: AudioTranscodeService = Depends(Provide[AppContainer.audio_transcode]),
):
    """提交音訊轉檔任務"""
    try:
        codec = _FORMAT_CODEC_MAP.get(request.output_format)
        if not codec:
            raise ValueError(f"Unsupported format: {request.output_format}")

        task_id = await service.submit_transcode(
            file_id=request.file_id,
            output_format=request.output_format,
            audio_codec=codec,
            audio_bitrate=request.audio_bitrate,
            sample_rate=request.sample_rate,
            channels=request.channels,
            output_dir=request.output_dir,
            output_filename=request.output_filename,
        )
        return AudioTranscodeResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
