"""
Video enhancement service.
Uses Real-ESRGAN to upscale video frames.
"""
import logging
import shutil
from pathlib import Path
from typing import Optional
from uuid import uuid4

from PIL import Image

from app.engine.paths import get_temp_dir
from app.services.files.file_service import get_file_service, FileService
from app.workers.task_manager import get_task_manager, TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_ENHANCE = "video.enhance"


class EnhanceService:
    _instance: Optional["EnhanceService"] = None

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
        self._task_manager.register_handler(TASK_TYPE_ENHANCE, self._handle_task)
        self._initialized = True
        logger.info("EnhanceService initialized")

    async def submit(self, file_id: str, model: str = "realesrgan", variant: str = "x4plus",
                     output_format: str = "mp4", video_codec: str = "h264",
                     output_dir: Optional[str] = None) -> str:
        task_id = await self._task_manager.submit(TASK_TYPE_ENHANCE, {
            "file_id": file_id, "model": model, "variant": variant,
            "output_format": output_format, "video_codec": video_codec,
            "output_dir": output_dir,
        })
        logger.info(f"Enhancement task submitted: {task_id}")
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
        from app.engine.ai.image.realesrgan import get_realesrgan
        from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_PTH
        from app.utils.video_frames import FramePipe
        import numpy as np

        file_id = params["file_id"]
        variant = params.get("variant", "x4plus")
        output_format = params.get("output_format", "mp4")
        video_codec = params.get("video_codec", "h264")
        output_dir = params.get("output_dir")

        file_info = self._file_service.get_file(file_id)
        if not file_info:
            raise ValueError(f"File not found: {file_id}")

        variant_spec = MODELS_REGISTRY[FORMAT_PTH]["realesrgan"]["variants"].get(variant)
        if not variant_spec:
            raise ValueError(f"Unknown variant: {variant}")
        scale = variant_spec.get("scale", 4)

        ffmpeg = get_ffmpeg()
        media_info = await ffmpeg.get_media_info(file_info.file_path)
        source_fps = media_info.fps or 30.0
        width = media_info.width
        height = media_info.height
        out_w = width * scale
        out_h = height * scale

        original_stem = Path(file_info.original_filename).stem
        output_filename = f"{original_stem}.enhanced_{variant}.{output_format}"
        if output_dir:
            output_path = Path(output_dir) / output_filename
        else:
            output_path = get_temp_dir() / "video_frames" / output_filename

        # Pipe: FFmpeg decode → Real-ESRGAN → FFmpeg encode
        # Decoder reads at source resolution, encoder writes at scaled resolution
        progress_callback(0.0, "畫面強化中...")
        realesrgan = get_realesrgan()

        pipe = FramePipe(
            input_path=file_info.file_path,
            output_path=output_path,
            output_fps=source_fps,
            width=out_w, height=out_h,
            video_codec=video_codec,
        )

        # Custom decoder at source resolution (FramePipe default uses output dims)
        import subprocess
        decoder = subprocess.Popen([
            ffmpeg.ffmpeg_path,
            "-i", file_info.file_path,
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-v", "quiet",
            "pipe:1",
        ], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

        pipe._decoder = None  # Don't use FramePipe's decoder
        pipe.open()  # Only starts encoder

        # Manually override: close the encoder's auto-started decoder
        # Actually, FramePipe.open() starts both. Let's just use raw subprocesses.
        pipe.close()

        # Do it manually with two subprocesses
        codec_map = {"h264": "libx264", "h265": "libx265", "vp9": "libvpx-vp9", "av1": "libsvtav1"}
        codec_lib = codec_map.get(video_codec, "libx264")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        encoder = subprocess.Popen([
            ffmpeg.ffmpeg_path, "-y",
            "-f", "rawvideo", "-pix_fmt", "rgb24",
            "-s", f"{out_w}x{out_h}",
            "-r", str(source_fps),
            "-i", "pipe:0",
            "-i", file_info.file_path,
            "-map", "0:v:0", "-map", "1:a?",
            "-c:v", codec_lib, "-crf", "18",
            "-pix_fmt", "yuv420p", "-c:a", "copy", "-shortest",
            str(output_path),
        ], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        frame_size = width * height * 3
        frame_idx = 0
        duration = media_info.duration or 0.0

        def _fmt_time(s: float) -> str:
            s = int(s)
            if s >= 3600:
                return f"{s // 3600}:{(s % 3600) // 60:02d}:{s % 60:02d}"
            return f"{s // 60}:{s % 60:02d}"

        try:
            while True:
                raw = decoder.stdout.read(frame_size)
                if len(raw) < frame_size:
                    break

                frame = np.frombuffer(raw, dtype=np.uint8).reshape(height, width, 3)
                img = Image.fromarray(frame)
                enhanced = realesrgan.enhance(image=img, model_id=variant, scale=scale)
                enhanced_arr = np.array(enhanced)
                encoder.stdin.write(enhanced_arr.tobytes())
                del frame, img, enhanced, enhanced_arr

                frame_idx += 1
                elapsed = frame_idx / source_fps
                if duration > 0:
                    pct = min(elapsed / duration, 0.95)
                    progress_callback(pct, f"畫面強化中... {_fmt_time(elapsed)}/{_fmt_time(duration)}")
                else:
                    progress_callback(0.5, f"畫面強化中... {_fmt_time(elapsed)}")
        finally:
            decoder.stdout.close()
            decoder.wait()
            encoder.stdin.close()
            encoder.wait()

        output_file_id = str(uuid4())
        self._file_service.register_output(
            file_id=output_file_id,
            file_path=output_path,
            original_filename=file_info.original_filename,
        )
        progress_callback(1.0, "畫面強化完成")
        return {
            "output_file_id": output_file_id,
            "output_filename": output_filename,
            "scale": scale,
            "frame_count": frame_idx,
        }


_service: Optional[EnhanceService] = None

def get_enhance_service() -> EnhanceService:
    global _service
    if _service is None:
        _service = EnhanceService()
    return _service
