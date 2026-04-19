"""
Video transcoding API routes.
"""
from __future__ import annotations
from typing import Optional, TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.init.container import AppContainer

if TYPE_CHECKING:
    from app.services.video.transcode_service import VideoTranscodeService
    from app.services.video.cut_service import VideoCutService
    from app.services.video.extract_audio_service import VideoExtractAudioService

router = APIRouter()


class TranscodeRequest(BaseModel):
    """Transcode request."""
    file_id: str = Field(..., description="Input file ID")
    output_format: str = Field(default="mp4", description="Output format (mp4, mkv, webm, avi)")
    video_codec: str = Field(default="h264", description="Video codec (h264, h265, vp9, av1, copy)")
    audio_codec: str = Field(default="aac", description="Audio codec (aac, mp3, opus, flac, copy)")
    preset: str = Field(default="medium", description="Encoding speed (ultrafast, fast, medium, slow, veryslow)")
    crf: int = Field(default=23, ge=0, le=51, description="Quality value (0-51, lower is better)")
    resolution: Optional[str] = Field(default=None, description="Resolution (e.g., 1920x1080)")
    scale_algorithm: Optional[str] = Field(default=None, description="Scaling algorithm (bicubic, lanczos, bilinear, spline, neighbor)")
    fps: Optional[float] = Field(default=None, gt=0, description="Frame rate")
    audio_bitrate: Optional[str] = Field(default=None, description="Audio bitrate (e.g., 128k)")


class CutRequest(BaseModel):
    """Cut request."""
    file_id: str = Field(..., description="Input file ID")
    start_time: float = Field(..., ge=0, description="Start time (seconds)")
    end_time: float = Field(..., gt=0, description="End time (seconds)")
    stream_copy: bool = Field(default=True, description="Use stream copy (fast but less precise)")


class ExtractAudioRequest(BaseModel):
    """Extract audio request."""
    file_id: str = Field(..., description="Input file ID")
    audio_format: str = Field(default="mp3", description="Audio format (mp3, wav, flac, aac)")
    audio_bitrate: Optional[str] = Field(default=None, description="Audio bitrate (e.g., 320k)")


class TranscodeResponse(BaseModel):
    """Transcode response."""
    task_id: str
    message: str = "Transcode task submitted"


class CutResponse(BaseModel):
    """Cut response."""
    task_id: str
    message: str = "Cut task submitted"


class ExtractAudioResponse(BaseModel):
    """Extract audio response."""
    task_id: str
    message: str = "Extract audio task submitted"


class MediaInfoResponse(BaseModel):
    """Media info response."""
    duration: float
    width: int
    height: int
    fps: float
    video_codec: str
    audio_codec: str
    bitrate: int
    file_size: int


class FFmpegStatusResponse(BaseModel):
    """FFmpeg status response."""
    installed: bool
    ffmpeg_path: Optional[str] = None
    ffprobe_path: Optional[str] = None
    bin_dir: str


@router.get("/ffmpeg/status", response_model=FFmpegStatusResponse)
@inject
async def get_ffmpeg_status(
    service: VideoTranscodeService = Depends(Provide[AppContainer.video_transcode]),
):
    """Check FFmpeg installation status."""
    status = service.get_ffmpeg_status()
    return FFmpegStatusResponse(**status)


@router.get("/info/{file_id}", response_model=MediaInfoResponse)
@inject
async def get_media_info(
    file_id: str,
    service: VideoTranscodeService = Depends(Provide[AppContainer.video_transcode]),
):
    """
    Get media file information.

    - **file_id**: Uploaded file ID
    """
    info = await service.get_media_info(file_id)
    return MediaInfoResponse(**info)


@router.post("/transcode", response_model=TranscodeResponse)
@inject
async def transcode_video(
    request: TranscodeRequest,
    service: VideoTranscodeService = Depends(Provide[AppContainer.video_transcode]),
):
    """
    Submit video transcode task.

    Supported formats:
    - **output_format**: mp4, mkv, webm, avi, mov
    - **video_codec**: h264, h265, vp9, av1, copy (no re-encoding)
    - **audio_codec**: aac, mp3, opus, flac, copy (no re-encoding)
    - **preset**: ultrafast (fastest), fast, medium (default), slow, veryslow (best quality)
    - **crf**: 0-51, recommended 18-28; lower = better quality but larger file
    """
    task_id = await service.submit_transcode(
        file_id=request.file_id,
        output_format=request.output_format,
        video_codec=request.video_codec,
        audio_codec=request.audio_codec,
        preset=request.preset,
        crf=request.crf,
        resolution=request.resolution,
        scale_algorithm=request.scale_algorithm,
        fps=request.fps,
        audio_bitrate=request.audio_bitrate,
    )
    return TranscodeResponse(task_id=task_id)


@router.post("/cut", response_model=CutResponse)
@inject
async def cut_video(
    request: CutRequest,
    service: VideoCutService = Depends(Provide[AppContainer.video_cut]),
):
    """
    Submit video cut task.

    - **start_time**: Start time (seconds)
    - **end_time**: End time (seconds)
    - **stream_copy**: Use stream copy (default True, fast but may be imprecise)
    """
    task_id = await service.submit_cut(
        file_id=request.file_id,
        start_time=request.start_time,
        end_time=request.end_time,
        stream_copy=request.stream_copy,
    )
    return CutResponse(task_id=task_id)


@router.post("/extract-audio", response_model=ExtractAudioResponse)
@inject
async def extract_audio(
    request: ExtractAudioRequest,
    service: VideoExtractAudioService = Depends(Provide[AppContainer.video_extract_audio]),
):
    """
    Submit extract audio task.

    - **audio_format**: Audio format (mp3, wav, flac, aac)
    - **audio_bitrate**: Audio bitrate (e.g., 128k, 192k, 256k, 320k)
    """
    task_id = await service.submit_extract_audio(
        file_id=request.file_id,
        audio_format=request.audio_format,
        audio_bitrate=request.audio_bitrate,
    )
    return ExtractAudioResponse(task_id=task_id)
