"""
Video frame extraction and encoding utilities.

Provides FramePipe: zero-disk-I/O streaming pipeline where FFmpeg decode,
Python per-frame processing, and FFmpeg encode are chained via stdin/stdout.
Used by RIFE interpolation and video enhancement.
"""
from __future__ import annotations

import logging
from fractions import Fraction
import subprocess
from pathlib import Path
from typing import Generator

import numpy as np

logger = logging.getLogger(__name__)


class FramePipe:
    """
    Zero-disk pipeline: FFmpeg decode → Python → FFmpeg encode.
    Reads raw RGB frames from FFmpeg stdout, writes processed frames to FFmpeg stdin.

    Usage:
        pipe = FramePipe(input_path, output_path, fps, input_width=W, input_height=H, output_width=W, output_height=H)
        pipe.open()
        for frame in pipe.read_frames():
            processed = process(frame)  # numpy H×W×3 uint8
            pipe.write_frame(processed)
        pipe.close()
    """

    def __init__(
        self,
        input_path: str | Path,
        output_path: str | Path,
        output_fps: Fraction | float,
        *,
        input_width: int,
        input_height: int,
        output_width: int,
        output_height: int,
        video_codec: str = "h264",
        crf: int = 18,
        target_fps: Fraction | float = 0,
    ):
        self.input_path = str(input_path)
        self.output_path = str(output_path)
        self.output_fps = Fraction(output_fps) if not isinstance(output_fps, Fraction) else output_fps
        self.target_fps = Fraction(target_fps) if not isinstance(target_fps, Fraction) else target_fps
        self.input_width = input_width
        self.input_height = input_height
        self.output_width = output_width
        self.output_height = output_height
        self.video_codec = video_codec
        self.crf = crf
        self._decoder: subprocess.Popen | None = None
        self._encoder: subprocess.Popen | None = None
        self._frame_size = self.input_width * self.input_height * 3  # RGB24

    def open(self):
        """Start decoder and encoder FFmpeg processes."""
        ffmpeg = get_container().ffmpeg()
        ffmpeg_path = ffmpeg.ffmpeg_path

        # Decoder: video → raw RGB frames on stdout
        self._decoder = subprocess.Popen([
            ffmpeg_path,
            "-i", self.input_path,
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-v", "quiet",
            "pipe:1",
        ], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

        # Encoder: raw RGB frames on stdin → video file (+ copy audio from source)
        codec_map = {
            "h264": "libx264", "h265": "libx265",
            "vp9": "libvpx-vp9", "av1": "libsvtav1",
        }
        codec_lib = codec_map.get(self.video_codec, "libx264")

        Path(self.output_path).parent.mkdir(parents=True, exist_ok=True)

        # If target_fps differs from output_fps, add fps filter to drop excess frames
        vf_args = []
        if self.target_fps > 0 and abs(float(self.target_fps) - float(self.output_fps)) > 0.5:
            vf_args = ["-vf", f"fps={self.target_fps.numerator}/{self.target_fps.denominator}"]

        self._encoder = subprocess.Popen([
            ffmpeg_path,
            "-y",
            "-f", "rawvideo",
            "-pix_fmt", "rgb24",
            "-s", f"{self.output_width}x{self.output_height}",
            "-r", f"{self.output_fps.numerator}/{self.output_fps.denominator}",
            "-i", "pipe:0",
            "-i", self.input_path,
            "-map", "0:v:0",
            "-map", "1:a?",
            *vf_args,
            "-c:v", codec_lib,
            "-crf", str(self.crf),
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-shortest",
            self.output_path,
        ], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

        logger.info(f"FramePipe opened: {self.input_width}x{self.input_height} → {self.output_width}x{self.output_height} @ {float(self.output_fps):.3f}fps")

    def read_frames(self) -> Generator[np.ndarray, None, None]:
        """Yield decoded frames as numpy arrays (H, W, 3) uint8."""
        assert self._decoder is not None, "Call open() first"
        while True:
            raw = self._decoder.stdout.read(self._frame_size)
            if len(raw) < self._frame_size:
                break
            frame = np.frombuffer(raw, dtype=np.uint8).reshape(self.input_height, self.input_width, 3)
            yield frame

    def write_frame(self, frame: np.ndarray):
        """Write a processed frame (H, W, 3) uint8 to encoder."""
        assert self._encoder is not None, "Call open() first"
        self._encoder.stdin.write(frame.tobytes())

    def close(self):
        """Close both processes."""
        if self._decoder:
            self._decoder.stdout.close()
            self._decoder.wait()
            self._decoder = None
        if self._encoder:
            self._encoder.stdin.close()
            self._encoder.wait()
            self._encoder = None
        logger.info("FramePipe closed")


