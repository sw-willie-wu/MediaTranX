"""
FFmpeg 封裝模組
提供影片轉檔、進度解析等功能
"""
import asyncio
import re
import shutil
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from backend.core.paths import get_ffmpeg_dir


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


class FFmpegError(Exception):
    """FFmpeg 錯誤"""
    pass


class FFmpeg:
    """FFmpeg 封裝類別"""

    # FFmpeg 路徑（dev: bin/ffmpeg, packaged: resources/ffmpeg）
    _PROJECT_BIN_DIR = get_ffmpeg_dir()

    def __init__(self):
        self.ffmpeg_path = self._find_ffmpeg()
        self.ffprobe_path = self._find_ffprobe()

    def _find_ffmpeg(self) -> str:
        """
        尋找 FFmpeg 執行檔
        優先使用專案內的 FFmpeg，若無則使用系統 PATH
        """
        # 1. 優先使用專案內的 FFmpeg
        local_ffmpeg = self._PROJECT_BIN_DIR / "ffmpeg.exe"
        if local_ffmpeg.exists():
            return str(local_ffmpeg)

        # 2. 嘗試系統 PATH
        system_path = shutil.which("ffmpeg")
        if system_path:
            return system_path

        raise FFmpegError(
            f"找不到 FFmpeg。請將 FFmpeg 放置於 {self._PROJECT_BIN_DIR} 或加入系統 PATH"
        )

    def _find_ffprobe(self) -> str:
        """
        尋找 FFprobe 執行檔
        優先使用專案內的 FFprobe，若無則使用系統 PATH
        """
        # 1. 優先使用專案內的 FFprobe
        local_ffprobe = self._PROJECT_BIN_DIR / "ffprobe.exe"
        if local_ffprobe.exists():
            return str(local_ffprobe)

        # 2. 嘗試系統 PATH
        system_path = shutil.which("ffprobe")
        if system_path:
            return system_path

        raise FFmpegError(
            f"找不到 FFprobe。請將 FFprobe 放置於 {self._PROJECT_BIN_DIR} 或加入系統 PATH"
        )

    @classmethod
    def get_bin_dir(cls) -> Path:
        """取得 FFmpeg 二進位檔目錄"""
        return cls._PROJECT_BIN_DIR

    @classmethod
    def is_installed(cls) -> bool:
        """檢查 FFmpeg 是否已安裝"""
        local_ffmpeg = cls._PROJECT_BIN_DIR / "ffmpeg.exe"
        return local_ffmpeg.exists() or shutil.which("ffmpeg") is not None

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
        if video_stream and "r_frame_rate" in video_stream:
            num, den = map(int, video_stream["r_frame_rate"].split("/"))
            fps = num / den if den else 0

        return MediaInfo(
            duration=float(format_info.get("duration", 0)),
            width=int(video_stream.get("width", 0)) if video_stream else 0,
            height=int(video_stream.get("height", 0)) if video_stream else 0,
            fps=fps,
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
        start_time: float,
        end_time: float,
        stream_copy: bool = True,
        on_progress: Optional[Callable[["TranscodeProgress"], None]] = None,
    ) -> Path:
        """
        剪輯影片

        Args:
            input_path: 輸入檔案路徑
            output_path: 輸出檔案路徑
            start_time: 開始時間（秒）
            end_time: 結束時間（秒）
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

        duration = end_time - start_time
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
        on_progress: Optional[Callable[["TranscodeProgress"], None]] = None,
    ) -> Path:
        """
        提取音訊

        Args:
            input_path: 輸入檔案路徑
            output_path: 輸出檔案路徑
            audio_format: 音訊格式 (mp3, wav, flac, aac)
            audio_bitrate: 音訊位元率 (e.g. "320k")
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
            "-progress", "pipe:1",
            "-nostats",
        ]

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


# 單例
_ffmpeg: Optional[FFmpeg] = None


def get_ffmpeg() -> FFmpeg:
    """取得 FFmpeg 單例"""
    global _ffmpeg
    if _ffmpeg is None:
        _ffmpeg = FFmpeg()
    return _ffmpeg
