"""
影片轉檔 API 路由
"""
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.services.video.transcode_service import get_transcode_service
from backend.core.ffmpeg import FFmpeg

router = APIRouter()


class TranscodeRequest(BaseModel):
    """轉檔請求"""
    file_id: str = Field(..., description="輸入檔案 ID")
    output_format: str = Field(default="mp4", description="輸出格式 (mp4, mkv, webm, avi)")
    video_codec: str = Field(default="h264", description="影片編碼 (h264, h265, vp9, av1, copy)")
    audio_codec: str = Field(default="aac", description="音訊編碼 (aac, mp3, opus, flac, copy)")
    preset: str = Field(default="medium", description="編碼速度 (ultrafast, fast, medium, slow, veryslow)")
    crf: int = Field(default=23, ge=0, le=51, description="品質值 (0-51, 越小越好)")
    resolution: Optional[str] = Field(default=None, description="解析度 (e.g., 1920x1080)")
    scale_algorithm: Optional[str] = Field(default=None, description="縮放演算法 (bicubic, lanczos, bilinear, spline, neighbor)")
    fps: Optional[float] = Field(default=None, gt=0, description="幀率")
    audio_bitrate: Optional[str] = Field(default=None, description="音訊位元率 (e.g., 128k)")
    output_dir: Optional[str] = Field(default=None, description="自訂輸出目錄")
    output_filename: Optional[str] = Field(default=None, description="自訂輸出檔名")


class CutRequest(BaseModel):
    """剪輯請求"""
    file_id: str = Field(..., description="輸入檔案 ID")
    start_time: float = Field(..., ge=0, description="開始時間（秒）")
    end_time: float = Field(..., gt=0, description="結束時間（秒）")
    stream_copy: bool = Field(default=True, description="是否使用 stream copy（快速但不精確）")
    output_dir: Optional[str] = Field(default=None, description="自訂輸出目錄")
    output_filename: Optional[str] = Field(default=None, description="自訂輸出檔名")


class ExtractAudioRequest(BaseModel):
    """提取音訊請求"""
    file_id: str = Field(..., description="輸入檔案 ID")
    audio_format: str = Field(default="mp3", description="音訊格式 (mp3, wav, flac, aac)")
    audio_bitrate: Optional[str] = Field(default=None, description="音訊位元率 (e.g., 320k)")
    output_dir: Optional[str] = Field(default=None, description="自訂輸出目錄")
    output_filename: Optional[str] = Field(default=None, description="自訂輸出檔名")


class TranscodeResponse(BaseModel):
    """轉檔回應"""
    task_id: str
    message: str = "轉檔任務已提交"


class CutResponse(BaseModel):
    """剪輯回應"""
    task_id: str
    message: str = "剪輯任務已提交"


class ExtractAudioResponse(BaseModel):
    """提取音訊回應"""
    task_id: str
    message: str = "提取音訊任務已提交"


class MediaInfoResponse(BaseModel):
    """媒體資訊回應"""
    duration: float
    width: int
    height: int
    fps: float
    video_codec: str
    audio_codec: str
    bitrate: int
    file_size: int


class FFmpegStatusResponse(BaseModel):
    """FFmpeg 狀態回應"""
    installed: bool
    ffmpeg_path: Optional[str] = None
    ffprobe_path: Optional[str] = None
    bin_dir: str


@router.get("/ffmpeg/status", response_model=FFmpegStatusResponse)
async def get_ffmpeg_status():
    """檢查 FFmpeg 安裝狀態"""
    is_installed = FFmpeg.is_installed()
    bin_dir = str(FFmpeg.get_bin_dir())

    if is_installed:
        try:
            ffmpeg = FFmpeg()
            return FFmpegStatusResponse(
                installed=True,
                ffmpeg_path=ffmpeg.ffmpeg_path,
                ffprobe_path=ffmpeg.ffprobe_path,
                bin_dir=bin_dir
            )
        except Exception:
            pass

    return FFmpegStatusResponse(
        installed=False,
        bin_dir=bin_dir
    )


@router.get("/info/{file_id}", response_model=MediaInfoResponse)
async def get_media_info(file_id: str):
    """
    取得媒體檔案資訊

    - **file_id**: 已上傳的檔案 ID
    """
    try:
        service = get_transcode_service()
        info = await service.get_media_info(file_id)
        return MediaInfoResponse(**info)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/transcode", response_model=TranscodeResponse)
async def transcode_video(request: TranscodeRequest):
    """
    提交影片轉檔任務

    支援的格式：
    - **output_format**: mp4, mkv, webm, avi, mov
    - **video_codec**: h264, h265, vp9, av1, copy (不重新編碼)
    - **audio_codec**: aac, mp3, opus, flac, copy (不重新編碼)
    - **preset**: ultrafast (最快), fast, medium (預設), slow, veryslow (最佳品質)
    - **crf**: 0-51，建議 18-28，越小品質越好但檔案越大
    """
    try:
        service = get_transcode_service()
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
            output_dir=request.output_dir,
            output_filename=request.output_filename,
        )
        return TranscodeResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/cut", response_model=CutResponse)
async def cut_video(request: CutRequest):
    """
    提交影片剪輯任務

    - **start_time**: 開始時間（秒）
    - **end_time**: 結束時間（秒）
    - **stream_copy**: 是否使用 stream copy（預設 True，快速但可能不精確）
    """
    try:
        service = get_transcode_service()
        task_id = await service.submit_cut(
            file_id=request.file_id,
            start_time=request.start_time,
            end_time=request.end_time,
            stream_copy=request.stream_copy,
            output_dir=request.output_dir,
            output_filename=request.output_filename,
        )
        return CutResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/extract-audio", response_model=ExtractAudioResponse)
async def extract_audio(request: ExtractAudioRequest):
    """
    提交提取音訊任務

    - **audio_format**: 音訊格式 (mp3, wav, flac, aac)
    - **audio_bitrate**: 音訊位元率 (e.g., 128k, 192k, 256k, 320k)
    """
    try:
        service = get_transcode_service()
        task_id = await service.submit_extract_audio(
            file_id=request.file_id,
            audio_format=request.audio_format,
            audio_bitrate=request.audio_bitrate,
            output_dir=request.output_dir,
            output_filename=request.output_filename,
        )
        return ExtractAudioResponse(task_id=task_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
