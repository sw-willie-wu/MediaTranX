"""
Audio transcoding API routes.
"""
from __future__ import annotations
import logging
from typing import Optional, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.init.container import AppContainer

if TYPE_CHECKING:
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
    """Audio transcode request."""
    file_id: str = Field(..., description="Input file ID")
    output_format: str = Field(default="mp3", description="Output format")
    audio_bitrate: str = Field(default="192k", description="Bitrate")
    sample_rate: Optional[int] = Field(default=None, description="Sample rate")
    channels: Optional[int] = Field(default=None, ge=1, le=2, description="Number of channels")


class AudioTranscodeResponse(BaseModel):
    """Audio transcode response."""
    task_id: str
    message: str = "Audio transcode task submitted"


class AudioInfoResponse(BaseModel):
    """Audio info response."""
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
    """Get audio file info."""
    info = await service.get_audio_info(file_id)
    return AudioInfoResponse(**info)


@router.post("/transcode", response_model=AudioTranscodeResponse)
@inject
async def transcode_audio(
    request: AudioTranscodeRequest,
    service: AudioTranscodeService = Depends(Provide[AppContainer.audio_transcode]),
):
    """Submit audio transcode task."""
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
    )
    return AudioTranscodeResponse(task_id=task_id)
