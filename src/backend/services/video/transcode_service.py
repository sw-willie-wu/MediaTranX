"""
影片轉檔服務
"""
import asyncio
import logging
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable, Optional
from uuid import uuid4

from backend.core.ffmpeg import (
    FFmpeg,
    FFmpegError,
    TranscodeOptions,
    TranscodeProgress,
    VideoCodec,
    AudioCodec,
    QualityPreset,
    get_ffmpeg,
)
from backend.services.files.file_service import FileService, get_file_service
from backend.workers.task_manager import TaskManager, get_task_manager

logger = logging.getLogger(__name__)

# 任務類型常數
TASK_TYPE_TRANSCODE = "video.transcode"
TASK_TYPE_CUT = "video.cut"
TASK_TYPE_EXTRACT_AUDIO = "video.extract_audio"


class TranscodeService:
    """
    影片轉檔服務
    整合 FFmpeg、檔案管理和任務管理
    """

    _instance: Optional["TranscodeService"] = None

    def __new__(cls, *args, **kwargs):
        """單例模式"""
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

        # 註冊任務處理器
        self._task_manager.register_handler(
            TASK_TYPE_TRANSCODE,
            self._handle_transcode_task
        )
        self._task_manager.register_handler(
            TASK_TYPE_CUT,
            self._handle_cut_task
        )
        self._task_manager.register_handler(
            TASK_TYPE_EXTRACT_AUDIO,
            self._handle_extract_audio_task
        )

        self._initialized = True
        logger.info("TranscodeService initialized")

    async def get_media_info(self, file_id: str) -> dict:
        """
        取得媒體資訊

        Args:
            file_id: 檔案 ID

        Returns:
            媒體資訊字典
        """
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        media_info = await self._ffmpeg.get_media_info(file_info.file_path)
        return asdict(media_info)

    async def submit_transcode(
        self,
        file_id: str,
        output_format: str = "mp4",
        video_codec: str = "h264",
        audio_codec: str = "aac",
        preset: str = "medium",
        crf: int = 23,
        resolution: Optional[str] = None,
        scale_algorithm: Optional[str] = None,
        fps: Optional[float] = None,
        audio_bitrate: Optional[str] = None,
        output_dir: Optional[str] = None,
        output_filename: Optional[str] = None,
    ) -> str:
        """
        提交轉檔任務

        Args:
            file_id: 輸入檔案 ID
            output_format: 輸出格式 (mp4, mkv, webm, etc.)
            video_codec: 影片編碼器 (h264, h265, vp9, av1, copy)
            audio_codec: 音訊編碼器 (aac, mp3, opus, flac, copy)
            preset: 編碼速度預設 (ultrafast, fast, medium, slow, veryslow)
            crf: 品質值 (0-51, 越小越好)
            resolution: 解析度 (e.g., "1920x1080")
            fps: 幀率
            audio_bitrate: 音訊位元率 (e.g., "128k")
            output_dir: 自訂輸出目錄（可選）
            output_filename: 自訂輸出檔名（可選，不含副檔名）

        Returns:
            task_id: 任務 ID
        """
        # 驗證檔案存在
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        # 建立任務參數
        params = {
            "file_id": file_id,
            "output_format": output_format,
            "video_codec": video_codec,
            "audio_codec": audio_codec,
            "preset": preset,
            "crf": crf,
            "resolution": resolution,
            "scale_algorithm": scale_algorithm,
            "fps": fps,
            "audio_bitrate": audio_bitrate,
            "output_dir": output_dir,
            "output_filename": output_filename,
        }

        # 提交任務
        task_id = await self._task_manager.submit(TASK_TYPE_TRANSCODE, params)
        logger.info(f"Transcode task submitted: {task_id} for file {file_id}")

        return task_id

    async def submit_cut(
        self,
        file_id: str,
        start_time: float,
        end_time: float,
        stream_copy: bool = True,
        output_dir: Optional[str] = None,
        output_filename: Optional[str] = None,
    ) -> str:
        """提交剪輯任務"""
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        params = {
            "file_id": file_id,
            "start_time": start_time,
            "end_time": end_time,
            "stream_copy": stream_copy,
            "output_dir": output_dir,
            "output_filename": output_filename,
        }

        task_id = await self._task_manager.submit(TASK_TYPE_CUT, params)
        logger.info(f"Cut task submitted: {task_id} for file {file_id}")
        return task_id

    async def submit_extract_audio(
        self,
        file_id: str,
        audio_format: str = "mp3",
        audio_bitrate: Optional[str] = None,
        output_dir: Optional[str] = None,
        output_filename: Optional[str] = None,
    ) -> str:
        """提交提取音訊任務"""
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        params = {
            "file_id": file_id,
            "audio_format": audio_format,
            "audio_bitrate": audio_bitrate,
            "output_dir": output_dir,
            "output_filename": output_filename,
        }

        task_id = await self._task_manager.submit(TASK_TYPE_EXTRACT_AUDIO, params)
        logger.info(f"Extract audio task submitted: {task_id} for file {file_id}")
        return task_id

    def _handle_transcode_task(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """
        處理轉檔任務（在 executor 中執行）

        Args:
            params: 任務參數
            progress_callback: 進度回調 (percent, message)

        Returns:
            結果字典
        """
        # 在新的事件循環中執行異步代碼
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
        """
        執行轉檔

        Args:
            params: 任務參數
            progress_callback: 進度回調

        Returns:
            結果字典
        """
        file_id = params["file_id"]
        file_info = self._file_service.get_file(file_id)

        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        # 映射編碼器
        video_codec_map = {
            "h264": VideoCodec.H264,
            "h265": VideoCodec.H265,
            "vp9": VideoCodec.VP9,
            "av1": VideoCodec.AV1,
            "copy": VideoCodec.COPY,
        }

        audio_codec_map = {
            "aac": AudioCodec.AAC,
            "mp3": AudioCodec.MP3,
            "opus": AudioCodec.OPUS,
            "flac": AudioCodec.FLAC,
            "copy": AudioCodec.COPY,
        }

        preset_map = {
            "ultrafast": QualityPreset.ULTRAFAST,
            "fast": QualityPreset.FAST,
            "medium": QualityPreset.MEDIUM,
            "slow": QualityPreset.SLOW,
            "veryslow": QualityPreset.VERYSLOW,
        }

        # 建立轉檔選項
        options = TranscodeOptions(
            output_format=params["output_format"],
            video_codec=video_codec_map.get(params["video_codec"], VideoCodec.H264),
            audio_codec=audio_codec_map.get(params["audio_codec"], AudioCodec.AAC),
            preset=preset_map.get(params["preset"], QualityPreset.MEDIUM),
            crf=params.get("crf", 23),
            resolution=params.get("resolution"),
            scale_algorithm=params.get("scale_algorithm"),
            fps=params.get("fps"),
            audio_bitrate=params.get("audio_bitrate"),
        )

        # 建立輸出路徑
        custom_output_dir = params.get("output_dir")
        custom_output_filename = params.get("output_filename")
        output_file_id = str(uuid4())

        # 決定檔名
        if custom_output_filename:
            # 使用自訂檔名（移除使用者可能輸入的副檔名，統一用選擇的格式）
            base_name = Path(custom_output_filename).stem
            final_filename = f"{base_name}.{params['output_format']}"
        else:
            # 自動產生檔名
            original_stem = Path(file_info.original_filename).stem
            final_filename = f"{original_stem}_transcoded_{output_file_id[:8]}.{params['output_format']}"

        # 決定輸出目錄（優先自訂 > 來源目錄 > 預設 output）
        if custom_output_dir:
            output_dir_path = Path(custom_output_dir)
        elif file_info.source_dir:
            output_dir_path = Path(file_info.source_dir)
        else:
            output_dir_path = self._file_service.output_dir
        output_dir_path.mkdir(parents=True, exist_ok=True)
        output_path = output_dir_path / final_filename

        # 進度回調包裝
        def on_ffmpeg_progress(progress: TranscodeProgress):
            progress_callback(
                progress.percent / 100,
                f"轉檔中... {progress.percent:.1f}% (速度: {progress.speed:.1f}x)"
            )

        progress_callback(0.0, "開始轉檔...")

        try:
            # 執行轉檔
            await self._ffmpeg.transcode(
                input_path=file_info.file_path,
                output_path=output_path,
                options=options,
                on_progress=on_ffmpeg_progress
            )

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

        except FFmpegError as e:
            logger.error(f"Transcode failed: {e}")
            raise

    def _handle_cut_task(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """處理剪輯任務（在 executor 中執行）"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self._execute_cut(params, progress_callback)
            )
        finally:
            loop.close()

    async def _execute_cut(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """執行剪輯"""
        file_id = params["file_id"]
        file_info = self._file_service.get_file(file_id)

        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        start_time = params["start_time"]
        end_time = params["end_time"]
        stream_copy = params.get("stream_copy", True)

        # 建立輸出路徑
        custom_output_dir = params.get("output_dir")
        custom_output_filename = params.get("output_filename")
        output_file_id = str(uuid4())

        original_ext = Path(file_info.original_filename).suffix
        if custom_output_filename:
            base_name = Path(custom_output_filename).stem
            final_filename = f"{base_name}{original_ext}"
        else:
            original_stem = Path(file_info.original_filename).stem
            final_filename = f"{original_stem}_cut_{output_file_id[:8]}{original_ext}"

        if custom_output_dir:
            output_dir_path = Path(custom_output_dir)
        elif file_info.source_dir:
            output_dir_path = Path(file_info.source_dir)
        else:
            output_dir_path = self._file_service.output_dir
        output_dir_path.mkdir(parents=True, exist_ok=True)
        output_path = output_dir_path / final_filename

        def on_ffmpeg_progress(progress: TranscodeProgress):
            progress_callback(
                progress.percent / 100,
                f"剪輯中... {progress.percent:.1f}% (速度: {progress.speed:.1f}x)"
            )

        progress_callback(0.0, "開始剪輯...")

        try:
            await self._ffmpeg.cut(
                input_path=file_info.file_path,
                output_path=output_path,
                start_time=start_time,
                end_time=end_time,
                stream_copy=stream_copy,
                on_progress=on_ffmpeg_progress,
            )

            output_info = self._file_service.register_output(
                file_id=output_file_id,
                file_path=output_path,
                original_filename=file_info.original_filename,
            )

            progress_callback(1.0, "剪輯完成")

            return {
                "output_file_id": output_file_id,
                "output_filename": output_info.filename,
                "output_size": output_info.file_size,
            }

        except FFmpegError as e:
            logger.error(f"Cut failed: {e}")
            raise

    def _handle_extract_audio_task(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """處理提取音訊任務（在 executor 中執行）"""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(
                self._execute_extract_audio(params, progress_callback)
            )
        finally:
            loop.close()

    async def _execute_extract_audio(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None]
    ) -> dict:
        """執行提取音訊"""
        file_id = params["file_id"]
        file_info = self._file_service.get_file(file_id)

        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        audio_format = params.get("audio_format", "mp3")
        audio_bitrate = params.get("audio_bitrate")

        # 建立輸出路徑
        custom_output_dir = params.get("output_dir")
        custom_output_filename = params.get("output_filename")
        output_file_id = str(uuid4())

        if custom_output_filename:
            base_name = Path(custom_output_filename).stem
            final_filename = f"{base_name}.{audio_format}"
        else:
            original_stem = Path(file_info.original_filename).stem
            final_filename = f"{original_stem}_audio_{output_file_id[:8]}.{audio_format}"

        if custom_output_dir:
            output_dir_path = Path(custom_output_dir)
        elif file_info.source_dir:
            output_dir_path = Path(file_info.source_dir)
        else:
            output_dir_path = self._file_service.output_dir
        output_dir_path.mkdir(parents=True, exist_ok=True)
        output_path = output_dir_path / final_filename

        def on_ffmpeg_progress(progress: TranscodeProgress):
            progress_callback(
                progress.percent / 100,
                f"提取音訊中... {progress.percent:.1f}% (速度: {progress.speed:.1f}x)"
            )

        progress_callback(0.0, "開始提取音訊...")

        try:
            await self._ffmpeg.extract_audio(
                input_path=file_info.file_path,
                output_path=output_path,
                audio_format=audio_format,
                audio_bitrate=audio_bitrate,
                on_progress=on_ffmpeg_progress,
            )

            output_info = self._file_service.register_output(
                file_id=output_file_id,
                file_path=output_path,
                original_filename=file_info.original_filename,
            )

            progress_callback(1.0, "提取音訊完成")

            return {
                "output_file_id": output_file_id,
                "output_filename": output_info.filename,
                "output_size": output_info.file_size,
            }

        except FFmpegError as e:
            logger.error(f"Extract audio failed: {e}")
            raise


# 全域服務實例
_transcode_service: Optional[TranscodeService] = None


def get_transcode_service() -> TranscodeService:
    """取得全域轉檔服務實例"""
    global _transcode_service
    if _transcode_service is None:
        _transcode_service = TranscodeService()
    return _transcode_service
