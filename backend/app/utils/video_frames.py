"""
Video frame extraction and encoding utilities.
Shared by interpolation and enhancement services.
"""
import asyncio
import logging
import re
from pathlib import Path
from typing import Callable, Optional

from app.engine.ffmpeg import get_ffmpeg

logger = logging.getLogger(__name__)


async def extract_frames(
    input_path: str | Path,
    output_dir: Path,
    fmt: str = "png",
    on_progress: Optional[Callable[[float, str], None]] = None,
) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    input_path = Path(input_path)

    ffmpeg = get_ffmpeg()
    media_info = await ffmpeg.get_media_info(input_path)
    duration = media_info.duration or 0.0

    pattern = str(output_dir / f"%06d.{fmt}")
    qscale = ["-qscale:v", "2"] if fmt == "jpg" else []

    cmd = [
        ffmpeg.ffmpeg_path,
        "-i", str(input_path),
        *qscale,
        pattern,
    ]

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stderr_data = b""
    while True:
        chunk = await process.stderr.read(4096)
        if not chunk:
            break
        stderr_data += chunk
        text = chunk.decode("utf-8", errors="replace")
        m = re.search(r"time=(\d+):(\d+):(\d+\.\d+)", text)
        if m and duration > 0 and on_progress:
            t = int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))
            on_progress(min(t / duration, 0.99), f"拆幀中... {t:.1f}/{duration:.1f}s")

    await process.wait()
    if process.returncode != 0:
        err = stderr_data.decode("utf-8", errors="replace")[-500:]
        raise RuntimeError(f"Frame extraction failed: {err}")

    frame_count = len(list(output_dir.glob(f"*.{fmt}")))
    logger.info(f"Extracted {frame_count} frames to {output_dir}")
    return frame_count


async def encode_frames(
    frames_dir: Path,
    output_path: Path,
    fps: float,
    audio_source: str | Path,
    fmt: str = "png",
    video_codec: str = "h264",
    crf: int = 18,
    on_progress: Optional[Callable[[float, str], None]] = None,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    ffmpeg = get_ffmpeg()

    codec_map = {
        "h264": "libx264",
        "h265": "libx265",
        "vp9": "libvpx-vp9",
        "av1": "libsvtav1",
    }
    codec_lib = codec_map.get(video_codec, "libx264")

    pattern = str(frames_dir / f"%06d.{fmt}")
    cmd = [
        ffmpeg.ffmpeg_path,
        "-y",
        "-framerate", str(fps),
        "-i", pattern,
        "-i", str(audio_source),
        "-map", "0:v:0",
        "-map", "1:a?",
        "-c:v", codec_lib,
        "-crf", str(crf),
        "-pix_fmt", "yuv420p",
        "-c:a", "copy",
        "-shortest",
        str(output_path),
    ]

    total_frames = len(list(frames_dir.glob(f"*.{fmt}")))

    process = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stderr_data = b""
    while True:
        chunk = await process.stderr.read(4096)
        if not chunk:
            break
        stderr_data += chunk
        text = chunk.decode("utf-8", errors="replace")
        m = re.search(r"frame=\s*(\d+)", text)
        if m and total_frames > 0 and on_progress:
            frame = int(m.group(1))
            on_progress(min(frame / total_frames, 0.99), f"編碼中... {frame}/{total_frames} 幀")

    await process.wait()
    if process.returncode != 0:
        err = stderr_data.decode("utf-8", errors="replace")[-500:]
        raise RuntimeError(f"Frame encoding failed: {err}")

    logger.info(f"Encoded {total_frames} frames → {output_path}")
