"""
Video frame interpolation service.
Uses RIFE to increase video frame rate.
"""
import logging
import shutil
from pathlib import Path
from typing import Optional
from uuid import uuid4

from app.engine.paths import get_temp_dir
from app.services.files.file_service import get_file_service, FileService
from app.workers.task_manager import get_task_manager, TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_INTERPOLATE = "video.interpolate"


class InterpolateService:
    _instance: Optional["InterpolateService"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._file_service: FileService = get_file_service()
        self._task_manager: TaskManager = get_task_manager()
        self._task_manager.register_handler(TASK_TYPE_INTERPOLATE, self._handle_task)
        self._initialized = True
        logger.info("InterpolateService initialized")

    async def submit(self, file_id: str, model: str = "v4.26", mode: str = "2x",
                     target_fps: Optional[float] = None, output_format: str = "mp4",
                     video_codec: str = "h264", output_dir: Optional[str] = None) -> str:
        task_id = await self._task_manager.submit(TASK_TYPE_INTERPOLATE, {
            "file_id": file_id, "model": model, "mode": mode,
            "target_fps": target_fps, "output_format": output_format,
            "video_codec": video_codec, "output_dir": output_dir,
        })
        logger.info(f"Interpolation task submitted: {task_id}")
        return task_id

    def _handle_task(self, params: dict, progress_callback) -> dict:
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._execute(params, progress_callback))
        finally:
            loop.close()

    async def _execute(self, params: dict, progress_callback) -> dict:
        from app.engine.ffmpeg import get_ffmpeg
        from app.engine.ai.video.rife import get_rife

        file_id = params["file_id"]
        model = params.get("model", "v4.26")
        mode = params.get("mode", "2x")
        target_fps = params.get("target_fps")
        output_format = params.get("output_format", "mp4")
        video_codec = params.get("video_codec", "h264")
        output_dir = params.get("output_dir")

        file_info = self._file_service.get_file(file_id)
        if not file_info:
            raise ValueError(f"File not found: {file_id}")

        ffmpeg = get_ffmpeg()
        media_info = await ffmpeg.get_media_info(file_info.file_path)
        source_fps = media_info.fps or 30.0
        width = media_info.width
        height = media_info.height

        if mode == "custom" and target_fps:
            if target_fps <= source_fps:
                raise ValueError(f"目標 FPS ({target_fps}) 必須大於原始 FPS ({source_fps})")
            ratio = target_fps / source_fps
            multiplier = 2
            while multiplier < ratio:
                multiplier *= 2
            out_fps = target_fps
        elif mode == "4x":
            multiplier = 4
            out_fps = source_fps * 4
        else:
            multiplier = 2
            out_fps = source_fps * 2

        # Output path
        original_stem = Path(file_info.original_filename).stem
        output_filename = f"{original_stem}.interpolated_{mode}.{output_format}"
        if output_dir:
            output_path = Path(output_dir) / output_filename
        else:
            output_path = get_temp_dir() / "video_frames" / output_filename

        # Pipe mode: FFmpeg decode → RIFE → FFmpeg encode (zero disk I/O)
        progress_callback(0.0, "補幀中...")
        rife = get_rife()

        def interp_progress(p, msg):
            progress_callback(p * 0.95, msg)

        total_out, _ = rife.interpolate_pipe(
            input_path=file_info.file_path,
            output_path=output_path,
            variant=model,
            multiplier=multiplier,
            width=width,
            height=height,
            source_fps=source_fps,
            duration=media_info.duration or 0.0,
            target_fps=out_fps if mode == "custom" else 0,
            video_codec=video_codec,
            on_progress=interp_progress,
        )

        output_file_id = str(uuid4())
        self._file_service.register_output(
            file_id=output_file_id,
            file_path=output_path,
            original_filename=file_info.original_filename,
        )
        progress_callback(1.0, "補幀完成")
        return {
            "output_file_id": output_file_id,
            "output_filename": output_filename,
            "source_fps": source_fps,
            "output_fps": out_fps,
            "frame_count": total_out,
        }


_service: Optional[InterpolateService] = None

def get_interpolate_service() -> InterpolateService:
    global _service
    if _service is None:
        _service = InterpolateService()
    return _service
