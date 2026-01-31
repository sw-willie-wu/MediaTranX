"""
音訊轉檔服務
"""
import asyncio
import logging
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from backend.core.ffmpeg import (
    FFmpeg,
    FFmpegError,
    get_ffmpeg,
)
from backend.services.file_service import FileService, get_file_service
from backend.workers.task_manager import TaskManager, get_task_manager

logger = logging.getLogger(__name__)

TASK_TYPE_AUDIO_TRANSCODE = "audio.transcode"


class AudioTranscodeService:
    """
    音訊轉檔服務
    """

    _instance: Optional["AudioTranscodeService"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self._ffmpeg: FFmpeg = get_ffmpeg()
        self._file_service: FileService = get_file_service()
        self._task_manager: TaskManager = get_task_manager()

        self._task_manager.register_handler(
            TASK_TYPE_AUDIO_TRANSCODE,
            self._handle_transcode_task
        )

        self._initialized = True
        logger.info("AudioTranscodeService initialized")

    async def get_audio_info(self, file_id: str) -> dict:
        """取得音訊資訊"""
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        media_info = await self._ffmpeg.get_media_info(file_info.file_path)
        return {
            "duration": media_info.duration,
            "sample_rate": 44100,  # TODO: 從 ffprobe 取得
            "channels": 2,
            "codec": media_info.audio_codec,
            "bitrate": media_info.bitrate,
            "file_size": media_info.file_size,
        }

    async def submit_transcode(
        self,
        file_id: str,
        output_format: str = "mp3",
        audio_codec: str = "libmp3lame",
        audio_bitrate: str = "192k",
        sample_rate: Optional[int] = None,
        channels: Optional[int] = None,
        output_dir: Optional[str] = None,
        output_filename: Optional[str] = None,
    ) -> str:
        """提交音訊轉檔任務"""
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        params = {
            "file_id": file_id,
            "output_format": output_format,
            "audio_codec": audio_codec,
            "audio_bitrate": audio_bitrate,
            "sample_rate": sample_rate,
            "channels": channels,
            "output_dir": output_dir,
            "output_filename": output_filename,
        }

        task_id = await self._task_manager.submit(TASK_TYPE_AUDIO_TRANSCODE, params)
        logger.info(f"Audio transcode task submitted: {task_id}")

        return task_id

    def _handle_transcode_task(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """處理轉檔任務"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self._execute_transcode(params, progress_callback)
            )
        finally:
            loop.close()

    async def _execute_transcode(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """執行音訊轉檔"""
        file_id = params["file_id"]
        file_info = self._file_service.get_file(file_id)

        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        # 建立輸出路徑
        custom_output_dir = params.get("output_dir")
        custom_output_filename = params.get("output_filename")
        output_file_id = str(uuid4())

        if custom_output_filename:
            base_name = Path(custom_output_filename).stem
            final_filename = f"{base_name}.{params['output_format']}"
        else:
            original_stem = Path(file_info.original_filename).stem
            final_filename = f"{original_stem}_converted_{output_file_id[:8]}.{params['output_format']}"

        # 決定輸出目錄（優先自訂 > 來源目錄 > 預設 output）
        if custom_output_dir:
            output_dir_path = Path(custom_output_dir)
        elif file_info.source_dir:
            output_dir_path = Path(file_info.source_dir)
        else:
            output_dir_path = self._file_service.output_dir
        output_dir_path.mkdir(parents=True, exist_ok=True)
        output_path = output_dir_path / final_filename

        # 建立 FFmpeg 命令
        cmd = [
            self._ffmpeg.ffmpeg_path,
            "-i", file_info.file_path,
            "-vn",  # 移除影片串流
            "-acodec", params["audio_codec"],
            "-b:a", params["audio_bitrate"],
        ]

        if params.get("sample_rate"):
            cmd.extend(["-ar", str(params["sample_rate"])])

        if params.get("channels"):
            cmd.extend(["-ac", str(params["channels"])])

        cmd.extend(["-y", str(output_path)])

        progress_callback(0.0, "開始轉檔...")

        # 執行轉檔
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # 簡單進度模擬（音訊通常很快）
            progress_callback(0.3, "轉檔中...")

            stdout, stderr = await process.communicate()

            if process.returncode != 0:
                raise FFmpegError(f"FFmpeg error: {stderr.decode()}")

            progress_callback(0.9, "處理中...")

            # 註冊輸出檔案
            output_info = self._file_service.register_output(
                file_id=output_file_id,
                file_path=output_path,
                original_filename=file_info.original_filename,
            )

            progress_callback(1.0, "轉檔完成")

            return {
                "output_file_id": output_file_id,
                "output_filename": output_info.filename,
                "output_size": output_info.file_size,
            }

        except Exception as e:
            logger.error(f"Audio transcode failed: {e}")
            raise


_audio_transcode_service: Optional[AudioTranscodeService] = None


def get_audio_transcode_service() -> AudioTranscodeService:
    global _audio_transcode_service
    if _audio_transcode_service is None:
        _audio_transcode_service = AudioTranscodeService()
    return _audio_transcode_service
