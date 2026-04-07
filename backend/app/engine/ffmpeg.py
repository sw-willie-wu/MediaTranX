"""
FFmpeg 封裝模組
提供影片轉檔、進度解析等功能
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
    """影片編碼器"""
    H264 = "libx264"
    H265 = "libx265"
    VP9 = "libvpx-vp9"
    AV1 = "libsvtav1"
    COPY = "copy"


class AudioCodec(str, Enum):
    """音訊編碼器"""
    AAC = "aac"
    MP3 = "libmp3lame"
    OPUS = "libopus"
    FLAC = "flac"
    COPY = "copy"


class QualityPreset(str, Enum):
    """品質預設"""
    ULTRAFAST = "ultrafast"
    FAST = "fast"
    MEDIUM = "medium"
    SLOW = "slow"
    VERYSLOW = "veryslow"


@dataclass
class MediaInfo:
    """媒體資訊"""
    duration: float  # 秒
    width: int
    height: int
    fps: float
    fps_fraction: Fraction  # 精確分數如 Fraction(30000, 1001)，避免浮點精度問題
    video_codec: str
    audio_codec: str
    bitrate: int  # kbps
    file_size: int  # bytes


@dataclass
class TranscodeProgress:
    """轉檔進度"""
    frame: int
    fps: float
    time: float  # 已處理秒數
    speed: float  # 處理速度倍率
    percent: float  # 百分比 0-100


@dataclass
class TranscodeOptions:
    """轉檔選項"""
    output_format: str = "mp4"
    video_codec: VideoCodec = VideoCodec.H264
    audio_codec: AudioCodec = AudioCodec.AAC
    preset: QualityPreset = QualityPreset.MEDIUM
    crf: int = 23  # 品質 (0-51, 越小越好)
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
    """FFmpeg 封裝類別"""

    # FFmpeg 路徑（dev: bin/ffmpeg, packaged: resources/ffmpeg）
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
        尋找 FFmpeg 執行檔
        優先使用專案內的 FFmpeg，若無則使用系統 PATH
        """
        bin_dir = self._get_bin_dir()
        # 1. 優先使用專案內的 FFmpeg
        exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
        local_ffmpeg = bin_dir / exe
        if local_ffmpeg.exists():
            return str(local_ffmpeg)

        # 2. 嘗試系統 PATH
        system_path = shutil.which("ffmpeg")
        if system_path:
            return system_path

        raise FFmpegError(
            f"找不到 FFmpeg。請將 FFmpeg 放置於 {bin_dir} 或加入系統 PATH"
        )

    def _find_ffprobe(self) -> str:
        """
        尋找 FFprobe 執行檔
        優先使用專案內的 FFprobe，若無則使用系統 PATH
        """
        bin_dir = self._get_bin_dir()
        # 1. 優先使用專案內的 FFprobe
        exe = "ffprobe.exe" if sys.platform == "win32" else "ffprobe"
        local_ffprobe = bin_dir / exe
        if local_ffprobe.exists():
            return str(local_ffprobe)

        # 2. 嘗試系統 PATH
        system_path = shutil.which("ffprobe")
        if system_path:
            return system_path

        raise FFmpegError(
            f"找不到 FFprobe。請將 FFprobe 放置於 {bin_dir} 或加入系統 PATH"
        )

    @classmethod
    def get_bin_dir(cls) -> Path:
        """取得 FFmpeg 二進位檔目錄"""
        return cls._get_bin_dir()

    @classmethod
    def is_installed(cls) -> bool:
        """檢查 FFmpeg 是否已安裝"""
        exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
        return (cls._get_bin_dir() / exe).exists() or shutil.which("ffmpeg") is not None

    async def get_media_info(self, input_path: str | Path) -> MediaInfo:
        """取得媒體資訊"""
        input_path = Path(input_path)
        if not input_path.exists():
            raise FFmpegError(f"檔案不存在: {input_path}")

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
            raise FFmpegError(f"FFprobe 錯誤: {stderr.decode()}")

        import json
        data = json.loads(stdout.decode())

        # 解析影片串流
        video_stream = next(
            (s for s in data.get("streams", []) if s["codec_type"] == "video"),
            None
        )
        audio_stream = next(
            (s for s in data.get("streams", []) if s["codec_type"] == "audio"),
            None
        )
        format_info = data.get("format", {})

        # 計算 FPS
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
            file_size=int(format_info.get("size", 0))
        )

    def _build_transcode_args(
        self,
        input_path: Path,
        output_path: Path,
        options: TranscodeOptions
    ) -> list[str]:
        """建構轉檔命令參數"""
        args = [
            self.ffmpeg_path,
            "-y",  # 覆蓋輸出檔案
            "-i", str(input_path),
            "-progress", "pipe:1",  # 輸出進度到 stdout
            "-nostats",
        ]

        # 影片編碼
        if options.video_codec != VideoCodec.COPY:
            args.extend(["-c:v", options.video_codec.value])
            args.extend(["-preset", options.preset.value])
            args.extend(["-crf", str(options.crf)])
        else:
            args.extend(["-c:v", "copy"])

        # 音訊編碼
        if options.audio_codec != AudioCodec.COPY:
            args.extend(["-c:a", options.audio_codec.value])
            if options.audio_bitrate:
                args.extend(["-b:a", options.audio_bitrate])
        else:
            args.extend(["-c:a", "copy"])

        # 解析度
        if options.resolution:
            w, h = options.resolution.split("x")
            algo = options.scale_algorithm or "bicubic"
            args.extend(["-vf", f"scale={w}:{h}:flags={algo}"])

        # FPS
        if options.fps:
            args.extend(["-r", str(options.fps)])

        # 額外參數
        if options.extra_args:
            args.extend(options.extra_args)

        args.append(str(output_path))
        return args

    def _parse_progress(self, line: str, duration: float) -> Optional[TranscodeProgress]:
        """解析 FFmpeg 進度輸出"""
        # FFmpeg progress 輸出格式:
        # frame=123
        # fps=24.5
        # out_time_ms=5000000
        # speed=1.5x

        if "=" not in line:
            return None

        # 累積進度資訊
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
            # progress=continue 或 progress=end 時回傳進度
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
        剪輯影片/音訊

        Args:
            input_path: 輸入檔案路徑
            output_path: 輸出檔案路徑
            start_time: 開始時間（秒數 float 或 "HH:MM:SS" 字串）
            end_time: 結束時間（同上）
            stream_copy: 是否使用 stream copy（快速但不精確）
            on_progress: 進度回調函數

        Returns:
            輸出檔案路徑
        """
        input_path = Path(input_path)
        output_path = Path(output_path)

        if not input_path.exists():
            raise FFmpegError(f"輸入檔案不存在: {input_path}")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        duration = _parse_time(end_time) - _parse_time(start_time)
        if duration <= 0:
            raise FFmpegError("結束時間必須大於開始時間")

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
            raise FFmpegError(f"剪輯失敗: {stderr.decode()}")

        return output_path

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
        提取音訊

        Args:
            input_path: 輸入檔案路徑
            output_path: 輸出檔案路徑
            audio_format: 音訊格式 (mp3, wav, flac, aac)
            audio_bitrate: 音訊位元率 (e.g. "320k")
            sample_rate: 取樣率 (e.g. 16000)
            channels: 聲道數 (1=mono, 2=stereo)
            on_progress: 進度回調函數

        Returns:
            輸出檔案路徑
        """
        input_path = Path(input_path)
        output_path = Path(output_path)

        if not input_path.exists():
            raise FFmpegError(f"輸入檔案不存在: {input_path}")

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
            raise FFmpegError(f"提取音訊失敗: {stderr.decode()}")

        return output_path

    async def adjust_volume(
        self,
        input_path: str | Path,
        output_path: str | Path,
        af_filter: str,
    ) -> Path:
        """
        套用音訊濾鏡（如音量調整）

        Args:
            input_path: 輸入檔案路徑
            output_path: 輸出檔案路徑
            af_filter: FFmpeg audio filter 字串 (e.g. "volume=3dB")
        """
        input_path = Path(input_path)
        output_path = Path(output_path)

        if not input_path.exists():
            raise FFmpegError(f"輸入檔案不存在: {input_path}")

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
        音訊格式轉換

        Args:
            input_path: 輸入檔案路徑
            output_path: 輸出檔案路徑
            audio_codec: 音訊編碼 (libmp3lame, flac, pcm_s16le, aac, libvorbis...)
            audio_bitrate: 位元率 (e.g. "320k")
            sample_rate: 取樣率 (e.g. 44100)
            channels: 聲道數 (1=mono, 2=stereo)
            extra_args: 額外 FFmpeg 參數
        """
        input_path = Path(input_path)
        output_path = Path(output_path)

        if not input_path.exists():
            raise FFmpegError(f"輸入檔案不存在: {input_path}")

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

    async def transcode(
        self,
        input_path: str | Path,
        output_path: str | Path,
        options: TranscodeOptions,
        on_progress: Optional[Callable[[TranscodeProgress], None]] = None
    ) -> Path:
        """
        執行轉檔

        Args:
            input_path: 輸入檔案路徑
            output_path: 輸出檔案路徑
            options: 轉檔選項
            on_progress: 進度回調函數

        Returns:
            輸出檔案路徑
        """
        input_path = Path(input_path)
        output_path = Path(output_path)

        if not input_path.exists():
            raise FFmpegError(f"輸入檔案不存在: {input_path}")

        # 確保輸出目錄存在
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # 取得媒體資訊（用於計算進度百分比）
        media_info = await self.get_media_info(input_path)
        duration = media_info.duration

        # 建構命令
        args = self._build_transcode_args(input_path, output_path, options)

        # 重置進度資料
        self._progress_data = {}

        # 執行 FFmpeg
        proc = await asyncio.create_subprocess_exec(
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )

        # 讀取進度
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
            raise FFmpegError(f"轉檔失敗: {stderr.decode()}")

        return output_path
