"""
音訊轉檔 API 路由
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.audio.transcode_service import get_audio_transcode_service

router = APIRouter()


class AudioTranscodeRequest(BaseModel):
    """音訊轉檔請求"""
    file_id: str = Field(..., description="輸入檔案 ID")
    output_format: str = Field(default="mp3", description="輸出格式 (mp3, aac, flac, wav, ogg)")
    audio_codec: str = Field(default="libmp3lame", description="音訊編碼器")
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
async def get_audio_info(file_id: str):
    """取得音訊檔案資訊"""
    try:
        service = get_audio_transcode_service()
        info = await service.get_audio_info(file_id)
        return AudioInfoResponse(**info)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/transcode", response_model=AudioTranscodeResponse)
async def transcode_audio(request: AudioTranscodeRequest):
    """提交音訊轉檔任務"""
    try:
        service = get_audio_transcode_service()
        task_id = await service.submit_transcode(
            file_id=request.file_id,
            output_format=request.output_format,
            audio_codec=request.audio_codec,
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
