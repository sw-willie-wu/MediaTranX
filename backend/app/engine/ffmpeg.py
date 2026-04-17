"""
FFmpeg wrapper module.
Provides video transcoding, progress parsing, and related utilities.
"""
import asyncio
import re
import shutil
import sys
from dataclasses import dataclass
from enum import Enum
from fractions import Fraction
from pathlib import Path
from typing import Callable, Optional

from app.handler.exceptions import FFmpegError
from app.init.configs import SETTINGS


class VideoCodec(str, Enum):
    """Video codec."""
    H264 = "libx264"
    H265 = "libx265"
    VP9 = "libvpx-vp9"
    AV1 = "libsvtav1"
    COPY = "copy"


class AudioCodec(str, Enum):
    """Audio codec."""
    AAC = "aac"
    MP3 = "libmp3lame"
    OPUS = "libopus"
    FLAC = "flac"
    COPY = "copy"


class QualityPreset(str, Enum):
    """Quality preset."""
    ULTRAFAST = "ultrafast"
    FAST = "fast"
    MEDIUM = "medium"
    SLOW = "slow"
    VERYSLOW = "veryslow"


@dataclass
class MediaInfo:
    """Media information."""
    duration: float  # seconds
    width: int
    height: int
    fps: float
    fps_fraction: Fraction  # Exact fraction e.g. Fraction(30000, 1001) to avoid floating-point precision issues
    video_codec: str
    audio_codec: str
    bitrate: int  # kbps
    file_size: int  # bytes
    sample_rate: int = 0  # Hz; 0 if no audio stream
    channels: int = 0     # audio channels; 0 if no audio stream


@dataclass
class TranscodeProgress:
    """Transcode progress."""
    frame: int
    fps: float
    time: float  # processed seconds
    speed: float  # processing speed multiplier
    percent: float  # percentage 0-100


@dataclass
class TranscodeOptions:
    """Transcode options."""
    output_format: str = "mp4"
    video_codec: VideoCodec = VideoCodec.H264
    audio_codec: AudioCodec = AudioCodec.AAC
    preset: QualityPreset = QualityPreset.MEDIUM
    crf: int = 23  # quality (0-51, lower is better)
    resolution: Optional[str] = None  # e.g., "1920x1080"
    scale_algorithm: Optional[str] = None  # e.g., "lanczos", "bicubic", "bilinear"
    fps: Optional[float] = None
    audio_bitrate: Optional[str] = None  # e.g., "128k"
    extra_args: Optional[list[str]] = None


def _parse_time(t: float | str) -> float:
    """Convert time to seconds. Accepts float or 'HH:MM:SS' / 'MM:SS' string."""
    if isinstance(t, (int, float)):
        return float(t)
    parts = str(t).split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    if len(parts) == 2:
        return int(parts[0]) * 60 + float(parts[1])
    return float(t)


class FFmpegWrapper:
    """FFmpeg wrapper class."""

    # FFmpeg path (dev: bin/ffmpeg, packaged: resources/ffmpeg)
    _PROJECT_BIN_DIR: Path = None  # type: ignore  # resolved lazily

    @classmethod
    def _get_bin_dir(cls) -> Path:
        if cls._PROJECT_BIN_DIR is None:
            cls._PROJECT_BIN_DIR = SETTINGS.path.ffmpeg
        return cls._PROJECT_BIN_DIR

    def __init__(self):
        self.ffmpeg_path = self._find_ffmpeg()
        self.ffprobe_path = self._find_ffprobe()

    def _find_ffmpeg(self) -> str:
        """
        Find the FFmpeg executable.
        Prefer the project-bundled FFmpeg; fall back to system PATH.
        """
        bin_dir = self._get_bin_dir()
        # 1. Prefer project-bundled FFmpeg
        exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
        local_ffmpeg = bin_dir / exe
        if local_ffmpeg.exists():
            return str(local_ffmpeg)

        # 2. Try system PATH
        system_path = shutil.which("ffmpeg")
        if system_path:
            return system_path

        raise FFmpegError(
            f"FFmpeg not found. Place FFmpeg in {bin_dir} or add it to system PATH"
        )

    def _find_ffprobe(self) -> str:
        """
        Find the FFprobe executable.
        Prefer the project-bundled FFprobe; fall back to system PATH.
        """
        bin_dir = self._get_bin_dir()
        # 1. Prefer project-bundled FFprobe
        exe = "ffprobe.exe" if sys.platform == "win32" else "ffprobe"
        local_ffprobe = bin_dir / exe
        if local_ffprobe.exists():
            return str(local_ffprobe)

        # 2. Try system PATH
        system_path = shutil.which("ffprobe")
        if system_path:
            return system_path

        raise FFmpegError(
            f"FFprobe not found. Place FFprobe in {bin_dir} or add it to system PATH"
        )

    @classmethod
    def get_bin_dir(cls) -> Path:
        """Get the FFmpeg binary directory."""
        return cls._get_bin_dir()

    @classmethod
    def is_installed(cls) -> bool:
        """Check whether FFmpeg is installed."""
        exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
        return (cls._get_bin_dir() / exe).exists() or shutil.which("ffmpeg") is not None

    async def get_media_info(self, input_path: str | Path) -> MediaInfo:
        """Get media information."""
        input_path = Path(input_path)
        if not input_path.exists():
            raise FFmpegError(f"File not found: {input_path}")

        cmd = [
            self.ffprobe_path,
            "-v", "quiet",
            "-print_format", "json",
            "-show_format",
            "-show_streams",
            str(input_path)
        ]

        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise FFmpegError(f"FFprobe error: {stderr.decode()}")

        import json
        data = json.loads(stdout.decode())

        # Parse video stream
        video_stream = next(
            (s for s in data.get("streams", []) if s["codec_type"] == "video"),
            None
        )
        audio_stream = next(
            (s for s in data.get("streams", []) if s["codec_type"] == "audio"),
            None
        )
        format_info = data.get("format", {})

        # Calculate FPS
        fps = 0.0
        fps_fraction = Fraction(0)
        if video_stream and "r_frame_rate" in video_stream:
            raw_frac = video_stream["r_frame_rate"]  # e.g. "30000/1001"
            num, den = map(int, raw_frac.split("/"))
            fps = num / den if den else 0
            fps_fraction = Fraction(num, den) if den else Fraction(0)

        return MediaInfo(
            duration=float(format_info.get("duration", 0)),
            width=int(video_stream.get("width", 0)) if video_stream else 0,
            height=int(video_stream.get("height", 0)) if video_stream else 0,
            fps=fps,
            fps_fraction=fps_fraction,
            video_codec=video_stream.get("codec_name", "") if video_stream else "",
            audio_codec=audio_stream.get("codec_name", "") if audio_stream else "",
            bitrate=int(format_info.get("bit_rate", 0)) // 1000,
            file_size=int(format_info.get("size", 0)),
            sample_rate=int(audio_stream.get("sample_rate", 0)) if audio_stream else 0,
            channels=int(audio_stream.get("channels", 0)) if audio_stream else 0,
        )

    def get_media_info_sync(self, input_path: str | Path) -> MediaInfo:
        """Sync version of get_media_info() for use in TaskManager handlers."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.get_media_info(input_path)
            )
        finally:
            loop.close()

    def _build_transcode_args(
        self,
        input_path: Path,
        output_path: Path,
        options: TranscodeOptions
    ) -> list[str]:
        """Build transcode command arguments."""
        args = [
            self.ffmpeg_path,
            "-y",  # overwrite output file
            "-i", str(input_path),
            "-progress", "pipe:1",  # output progress to stdout
            "-nostats",
        ]

        # Video codec
        if options.video_codec != VideoCodec.COPY:
            args.extend(["-c:v", options.video_codec.value])
            args.extend(["-preset", options.preset.value])
            args.extend(["-crf", str(options.crf)])
        else:
            args.extend(["-c:v", "copy"])

        # Audio codec
        if options.audio_codec != AudioCodec.COPY:
            args.extend(["-c:a", options.audio_codec.value])
            if options.audio_bitrate:
                args.extend(["-b:a", options.audio_bitrate])
        else:
            args.extend(["-c:a", "copy"])

        # Resolution
        if options.resolution:
            w, h = options.resolution.split("x")
            algo = options.scale_algorithm or "bicubic"
            args.extend(["-vf", f"scale={w}:{h}:flags={algo}"])

        # FPS
        if options.fps:
            args.extend(["-r", str(options.fps)])

        # Extra arguments
        if options.extra_args:
            args.extend(options.extra_args)

        args.append(str(output_path))
        return args

    def _parse_progress(self, line: str, duration: float) -> Optional[TranscodeProgress]:
        """Parse FFmpeg progress output."""
        # FFmpeg progress output format:
        # frame=123
        # fps=24.5
        # out_time_ms=5000000
        # speed=1.5x

        if "=" not in line:
            return None

        # Accumulate progress data
        if not hasattr(self, "_progress_data"):
            self._progress_data = {}

        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()

        if key == "frame":
            self._progress_data["frame"] = int(value) if value.isdigit() else 0
        elif key == "fps":
            try:
                self._progress_data["fps"] = float(value)
            except ValueError:
                self._progress_data["fps"] = 0.0
        elif key == "out_time_ms":
            try:
                self._progress_data["time"] = int(value) / 1_000_000
            except ValueError:
                self._progress_data["time"] = 0.0
        elif key == "speed":
            try:
                self._progress_data["speed"] = float(value.rstrip("x"))
            except ValueError:
                self._progress_data["speed"] = 0.0
        elif key == "progress":
            # Return progress on progress=continue or progress=end
            time = self._progress_data.get("time", 0)
            percent = (time / duration * 100) if duration > 0 else 0

            progress = TranscodeProgress(
                frame=self._progress_data.get("frame", 0),
                fps=self._progress_data.get("fps", 0),
                time=time,
                speed=self._progress_data.get("speed", 0),
                percent=min(percent, 100)
            )

            if value == "end":
                self._progress_data = {}

            return progress

        return None

    async def cut(
        self,
        input_path: str | Path,
        output_path: str | Path,
        start_time: float | str,
        end_time: float | str,
        stream_copy: bool = True,
        on_progress: Optional[Callable[["TranscodeProgress"], None]] = None,
    ) -> Path:
        """
        Cut video/audio.

        Args:
            input_path: Input file path.
            output_path: Output file path.
            start_time: Start time (float seconds or "HH:MM:SS" string).
            end_time: End time (same format as above).
            stream_copy: Whether to use stream copy (fast but less precise).
            on_progress: Progress callback function.

        Returns:
            Output file path.
        """
        input_path = Path(input_path)
        output_path = Path(output_path)

        if not input_path.exists():
            raise FFmpegError(f"Input file not found: {input_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        duration = _parse_time(end_time) - _parse_time(start_time)
        if duration <= 0:
            raise FFmpegError("End time must be greater than start time")

        args = [
            self.ffmpeg_path,
            "-y",
            "-ss", str(start_time),
            "-to", str(end_time),
            "-i", str(input_path),
            "-progress", "pipe:1",
            "-nostats",
        ]

        if stream_copy:
            args.extend(["-c", "copy"])
        else:
            args.extend(["-c:v", "libx264", "-c:a", "aac"])

        args.append(str(output_path))

        self._progress_data = {}

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        async def read_progress():
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                line_str = line.decode().strip()
                progress = self._parse_progress(line_str, duration)
                if progress and on_progress:
                    on_progress(progress)

        await read_progress()
        await proc.wait()

        if proc.returncode != 0:
            stderr = await proc.stderr.read()
            raise FFmpegError(f"Cut failed: {stderr.decode()}")

        return output_path

    def cut_sync(
        self,
        input_path: str | Path,
        output_path: str | Path,
        start_time: float | str,
        end_time: float | str,
        stream_copy: bool = True,
        on_progress: Optional[Callable[["TranscodeProgress"], None]] = None,
    ) -> Path:
        """Sync version of cut() for use in TaskManager handlers."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.cut(input_path, output_path, start_time, end_time,
                         stream_copy, on_progress)
            )
        finally:
            loop.close()

    async def crop(
        self,
        input_path: str | Path,
        output_path: str | Path,
        x: int,
        y: int,
        width: int,
        height: int,
        on_progress: Optional[Callable[["TranscodeProgress"], None]] = None,
    ) -> Path:
        """Crop video spatially using ffmpeg -vf crop=w:h:x:y.

        Video is re-encoded (H.264 default); audio stream-copied.
        """
        input_path = Path(input_path)
        output_path = Path(output_path)

        if not input_path.exists():
            raise FFmpegError(f"Input file not found: {input_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        media_info = await self.get_media_info(input_path)
        duration = media_info.duration

        args = [
            self.ffmpeg_path,
            "-y",
            "-i", str(input_path),
            "-vf", f"crop={width}:{height}:{x}:{y}",
            "-c:v", "libx264",
            "-preset", "medium",
            "-crf", "18",
            "-c:a", "copy",
            "-progress", "pipe:1",
            "-nostats",
            str(output_path),
        ]

        self._progress_data = {}

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        async def read_progress():
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                line_str = line.decode().strip()
                progress = self._parse_progress(line_str, duration)
                if progress and on_progress:
                    on_progress(progress)

        await read_progress()
        await proc.wait()

        if proc.returncode != 0:
            stderr = await proc.stderr.read()
            raise FFmpegError(f"Crop failed: {stderr.decode()}")

        return output_path

    def crop_sync(
        self,
        input_path: str | Path,
        output_path: str | Path,
        x: int,
        y: int,
        width: int,
        height: int,
        on_progress: Optional[Callable[["TranscodeProgress"], None]] = None,
    ) -> Path:
        """Sync version of crop() for use in TaskManager handlers."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.crop(input_path, output_path, x, y, width, height, on_progress)
            )
        finally:
            loop.close()

    async def extract_frame(
        self,
        input_path: str | Path,
        output_path: str | Path,
        timestamp: float,
    ) -> Path:
        """Extract a single frame at ``timestamp`` seconds as a JPEG image.

        Uses ``-ss`` before ``-i`` for fast input seeking plus ``-vframes 1`` to
        grab exactly one frame. ``-q:v 2`` gives high-quality JPEG output.
        """
        input_path = Path(input_path)
        output_path = Path(output_path)

        if not input_path.exists():
            raise FFmpegError(f"Input file not found: {input_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        args = [
            self.ffmpeg_path,
            "-y",
            "-ss", f"{timestamp:.3f}",
            "-i", str(input_path),
            "-vframes", "1",
            "-q:v", "2",
            str(output_path),
        ]

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()

        if proc.returncode != 0:
            raise FFmpegError(f"Frame extraction failed: {stderr.decode()}")

        return output_path

    def extract_frame_sync(
        self,
        input_path: str | Path,
        output_path: str | Path,
        timestamp: float,
    ) -> Path:
        """Sync version of extract_frame() for use in TaskManager handlers."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.extract_frame(input_path, output_path, timestamp)
            )
        finally:
            loop.close()

    async def extract_audio(
        self,
        input_path: str | Path,
        output_path: str | Path,
        audio_format: str = "mp3",
        audio_bitrate: Optional[str] = None,
        sample_rate: Optional[int] = None,
        channels: Optional[int] = None,
        on_progress: Optional[Callable[["TranscodeProgress"], None]] = None,
    ) -> Path:
        """
        Extract audio from media file.

        Args:
            input_path: Input file path.
            output_path: Output file path.
            audio_format: Audio format (mp3, wav, flac, aac).
            audio_bitrate: Audio bitrate (e.g. "320k").
            sample_rate: Sample rate (e.g. 16000).
            channels: Number of channels (1=mono, 2=stereo).
            on_progress: Progress callback function.

        Returns:
            Output file path.
        """
        input_path = Path(input_path)
        output_path = Path(output_path)

        if not input_path.exists():
            raise FFmpegError(f"Input file not found: {input_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        codec_map = {
            "mp3": "libmp3lame",
            "wav": "pcm_s16le",
            "flac": "flac",
            "aac": "aac",
        }
        codec = codec_map.get(audio_format, "libmp3lame")

        media_info = await self.get_media_info(input_path)
        duration = media_info.duration

        args = [
            self.ffmpeg_path,
            "-y",
            "-i", str(input_path),
            "-vn",
            "-c:a", codec,
        ]

        if sample_rate:
            args.extend(["-ar", str(sample_rate)])
        if channels:
            args.extend(["-ac", str(channels)])

        args.extend(["-progress", "pipe:1", "-nostats"])

        if audio_bitrate and audio_format not in ("wav", "flac"):
            args.extend(["-b:a", audio_bitrate])

        args.append(str(output_path))

        self._progress_data = {}

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        async def read_progress():
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                line_str = line.decode().strip()
                progress = self._parse_progress(line_str, duration)
                if progress and on_progress:
                    on_progress(progress)

        await read_progress()
        await proc.wait()

        if proc.returncode != 0:
            stderr = await proc.stderr.read()
            raise FFmpegError(f"Audio extraction failed: {stderr.decode()}")

        return output_path

    def extract_audio_sync(
        self,
        input_path: str | Path,
        output_path: str | Path,
        audio_format: str = "mp3",
        audio_bitrate: Optional[str] = None,
        sample_rate: Optional[int] = None,
        channels: Optional[int] = None,
        on_progress: Optional[Callable[["TranscodeProgress"], None]] = None,
    ) -> Path:
        """Sync version of extract_audio() for use in TaskManager handlers."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.extract_audio(input_path, output_path, audio_format,
                                   audio_bitrate, sample_rate, channels,
                                   on_progress)
            )
        finally:
            loop.close()

    async def adjust_volume(
        self,
        input_path: str | Path,
        output_path: str | Path,
        af_filter: str,
    ) -> Path:
        """
        Apply an audio filter (e.g. volume adjustment).

        Args:
            input_path: Input file path.
            output_path: Output file path.
            af_filter: FFmpeg audio filter string (e.g. "volume=3dB").
        """
        input_path = Path(input_path)
        output_path = Path(output_path)

        if not input_path.exists():
            raise FFmpegError(f"Input file not found: {input_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        proc = await asyncio.create_subprocess_exec(
            self.ffmpeg_path,
            "-i", str(input_path),
            "-af", af_filter,
            "-y", str(output_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise FFmpegError(f"Audio filter failed: {stderr.decode()}")

        return output_path

    def adjust_volume_sync(
        self,
        input_path: str | Path,
        output_path: str | Path,
        af_filter: str,
    ) -> Path:
        """Sync version of adjust_volume() for use in TaskManager handlers."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.adjust_volume(input_path, output_path, af_filter)
            )
        finally:
            loop.close()

    async def audio_convert(
        self,
        input_path: str | Path,
        output_path: str | Path,
        audio_codec: str,
        audio_bitrate: Optional[str] = None,
        sample_rate: Optional[int] = None,
        channels: Optional[int] = None,
        extra_args: Optional[list[str]] = None,
    ) -> Path:
        """
        Convert audio format.

        Args:
            input_path: Input file path.
            output_path: Output file path.
            audio_codec: Audio codec (libmp3lame, flac, pcm_s16le, aac, libvorbis...).
            audio_bitrate: Bitrate (e.g. "320k").
            sample_rate: Sample rate (e.g. 44100).
            channels: Number of channels (1=mono, 2=stereo).
            extra_args: Additional FFmpeg arguments.
        """
        input_path = Path(input_path)
        output_path = Path(output_path)

        if not input_path.exists():
            raise FFmpegError(f"Input file not found: {input_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        args = [
            self.ffmpeg_path,
            "-i", str(input_path),
            "-vn",
            "-acodec", audio_codec,
        ]
        if audio_bitrate:
            args.extend(["-b:a", audio_bitrate])
        if sample_rate:
            args.extend(["-ar", str(sample_rate)])
        if channels:
            args.extend(["-ac", str(channels)])
        if extra_args:
            args.extend(extra_args)
        args.extend(["-y", str(output_path)])

        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise FFmpegError(f"Audio convert failed: {stderr.decode()}")

        return output_path

    def audio_convert_sync(
        self,
        input_path: str | Path,
        output_path: str | Path,
        audio_codec: str,
        audio_bitrate: Optional[str] = None,
        sample_rate: Optional[int] = None,
        channels: Optional[int] = None,
        extra_args: Optional[list[str]] = None,
    ) -> Path:
        """Sync version of audio_convert() for use in TaskManager handlers."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.audio_convert(input_path, output_path, audio_codec,
                                   audio_bitrate, sample_rate, channels,
                                   extra_args)
            )
        finally:
            loop.close()

    async def transcode(
        self,
        input_path: str | Path,
        output_path: str | Path,
        options: TranscodeOptions,
        on_progress: Optional[Callable[[TranscodeProgress], None]] = None
    ) -> Path:
        """
        Execute transcoding.

        Args:
            input_path: Input file path.
            output_path: Output file path.
            options: Transcode options.
            on_progress: Progress callback function.

        Returns:
            Output file path.
        """
        input_path = Path(input_path)
        output_path = Path(output_path)

        if not input_path.exists():
            raise FFmpegError(f"Input file not found: {input_path}")

        # Ensure output directory exists
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Get media info (for calculating progress percentage)
        media_info = await self.get_media_info(input_path)
        duration = media_info.duration

        # Build command
        args = self._build_transcode_args(input_path, output_path, options)

        # Reset progress data
        self._progress_data = {}

        # Execute FFmpeg
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # Read progress
        async def read_progress():
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                line_str = line.decode().strip()
                progress = self._parse_progress(line_str, duration)
                if progress and on_progress:
                    on_progress(progress)

        await read_progress()
        await proc.wait()

        if proc.returncode != 0:
            stderr = await proc.stderr.read()
            raise FFmpegError(f"Transcode failed: {stderr.decode()}")

        return output_path

    def transcode_sync(
        self,
        input_path: str | Path,
        output_path: str | Path,
        options: TranscodeOptions,
        on_progress: Optional[Callable[[TranscodeProgress], None]] = None
    ) -> Path:
        """Sync version of transcode() for use in TaskManager handlers."""
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(
                self.transcode(input_path, output_path, options, on_progress)
            )
        finally:
            loop.close()
