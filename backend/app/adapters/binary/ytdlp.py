"""yt-dlp wrapper: probe + download a single video as MP4.

Resolves the yt-dlp binary from SETTINGS.path.ytdlp (a directory; see
electron/setup.js downloadYtDlp) with a shutil.which fallback, mirroring
FFmpegWrapper's bundled-binary convention.

SYNCHRONOUS subprocess model (unlike FFmpegWrapper's async readers): the
TaskManager handler runs in a thread-pool executor, and cancellation needs
process-tree termination (yt-dlp spawns ffmpeg as a grandchild during merge),
cleanest with a Popen we own. The binary path is resolved lazily on first
probe/download so construction never fails when yt-dlp is absent.
"""
import json
import logging
import os
import re
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from app.handler.exceptions import TaskCancelledError
from app.init.configs import SETTINGS

logger = logging.getLogger(__name__)


class YtDlpError(Exception):
    """yt-dlp invocation failed (non-zero exit / missing binary)."""


@dataclass
class ProbeResult:
    downloadable: bool
    title: str = ""
    duration: float = 0.0
    uploader: str = ""
    thumbnail: str = ""
    formats: list[dict] = field(default_factory=list)
    reason: str = ""  # set only when downloadable is False


def _ytdlp_bin_dir() -> Path:
    """The directory expected to hold the yt-dlp binary (test seam)."""
    return Path(SETTINGS.path.ytdlp)


def _exe_name() -> str:
    return "yt-dlp.exe" if sys.platform == "win32" else "yt-dlp"


def _no_window() -> dict:
    """Suppress the console window flash on Windows."""
    if sys.platform == "win32":
        return {"creationflags": subprocess.CREATE_NO_WINDOW}
    return {}


class YtDlpWrapper:
    """Owns the yt-dlp subprocess. Path resolved lazily on first use."""

    def __init__(self):
        self._ytdlp_path: Optional[str] = None

    def _find_ytdlp(self) -> str:
        bin_dir = _ytdlp_bin_dir()
        local = bin_dir / _exe_name()
        if local.exists():
            return str(local)
        system = shutil.which("yt-dlp")
        if system:
            return system
        raise YtDlpError(f"yt-dlp not found. Place yt-dlp in {bin_dir} or add it to PATH")

    def _resolve(self) -> str:
        if self._ytdlp_path is None:
            self._ytdlp_path = self._find_ytdlp()
        return self._ytdlp_path

    @classmethod
    def is_installed(cls) -> bool:
        bin_dir = _ytdlp_bin_dir()
        return (bin_dir / _exe_name()).exists() or shutil.which("yt-dlp") is not None
