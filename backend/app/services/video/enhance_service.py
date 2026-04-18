"""
Video enhancement service.
Uses Real-ESRGAN to upscale video frames.
"""
import logging
from fractions import Fraction
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

import numpy as np
from PIL import Image

from app.adapters.binary.ffmpeg import FFmpegWrapper
from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_VIDEO_ENHANCE = "video.enhance"


class EnhanceService:
    """Video frame-by-frame enhancement using Real-ESRGAN super-resolution."""

    def __init__(self, file_service: FileService, task_manager: TaskManager,
                 ffmpeg: FFmpegWrapper):
        self._file_service = file_service
        self._task_manager = task_manager
        self._ffmpeg = ffmpeg
        self._task_manager.register_handler(
            TASK_TYPE_VIDEO_ENHANCE, self._handle_task,
            output_policy="history",
        )
        logger.info("EnhanceService initialized")

    async def submit(self, file_id: str, model: str = "realesrgan", variant: str = "x4plus",
                     output_format: str = "mp4", video_codec: str = "h264") -> str:
        task_id = await self._task_manager.submit(TASK_TYPE_VIDEO_ENHANCE, {
            "file_id": file_id, "model": model, "variant": variant,
            "output_format": output_format, "video_codec": video_codec,
        })
        logger.info(f"Enhancement task submitted: {task_id}")
        return task_id

    def _handle_task(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        return self._execute(params, progress_callback)

    def _execute(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        from app.adapters.ai.wrapper.realesrgan import get_realesrgan
        from app.adapters.ai.registry import MODELS_REGISTRY, FORMAT_PTH
        from app.utils.video_frames import FramePipe

        file_id = params["file_id"]
        variant = params.get("variant", "x4plus")
        output_format = params.get("output_format", "mp4")
        video_codec = params.get("video_codec", "h264")

        file_info = self._file_service.require_file(file_id)

        variant_spec = MODELS_REGISTRY[FORMAT_PTH]["realesrgan"]["variants"].get(variant)
        if not variant_spec:
            raise ValueError(f"Unknown variant: {variant}")
        scale = variant_spec.get("scale", 4)

        ffmpeg = self._ffmpeg
        media_info = ffmpeg.get_media_info_sync(file_info.file_path)
        source_fps = media_info.fps or 30.0
        source_fps_frac = media_info.fps_fraction or Fraction(30)
        width = media_info.width
        height = media_info.height
        out_w = width * scale
        out_h = height * scale

        original_stem = Path(file_info.original_filename).stem
        output_filename = f"{original_stem}.enhanced_{variant}.{output_format}"
        output_path = self._file_service.output_dir / output_filename

        # Pipe: FFmpeg decode → Real-ESRGAN → FFmpeg encode
        # Decoder reads at source resolution, encoder writes at scaled resolution
        progress_callback(0.0, "task.progress.enhance_processing")
        realesrgan = get_realesrgan()

        pipe = FramePipe(
            input_path=file_info.file_path,
            output_path=output_path,
            output_fps=source_fps_frac,
            input_width=width, input_height=height,
            output_width=out_w, output_height=out_h,
            ffmpeg_path=ffmpeg.ffmpeg_path,
            video_codec=video_codec,
        )
        pipe.open()

        frame_idx = 0
        duration = media_info.duration or 0.0

        def _fmt_time(s: float) -> str:
            s = int(s)
            if s >= 3600:
                return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"
            return f"{s // 60}:{s % 60:02d}"

        try:
            for frame in pipe.read_frames():
                img = Image.fromarray(frame)
                enhanced = realesrgan.enhance(image=img, model_id=variant, scale=scale)
                enhanced_arr = np.array(enhanced)
                pipe.write_frame(enhanced_arr)
                del frame, img, enhanced, enhanced_arr

                frame_idx += 1
                elapsed = frame_idx / source_fps
                if duration > 0:
                    pct = min(elapsed / duration, 0.95)
                    progress_callback(pct, f"task.progress.enhance_processing_time|{_fmt_time(elapsed)}|{_fmt_time(duration)}")
                else:
                    progress_callback(0.5, f"task.progress.enhance_processing_elapsed|{_fmt_time(elapsed)}")
        finally:
            pipe.close()

        output_file_id = str(uuid4())
        self._file_service.register_output(
            file_id=output_file_id,
            file_path=output_path,
            original_filename=file_info.original_filename,
        )
        progress_callback(1.0, "task.progress.enhance_complete")
        return {
            "output_file_id": output_file_id,
            "output_filename": output_filename,
            "scale": scale,
            "frame_count": frame_idx,
        }
