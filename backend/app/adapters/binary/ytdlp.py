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


def _classify_error(stderr: str) -> str:
    """Map yt-dlp stderr to a stable reason code for the confirm card."""
    s = (stderr or "").lower()
    if "private video" in s:
        return "private"
    if "age" in s and ("confirm" in s or "restrict" in s or "sign in" in s):
        return "age_restricted"
    if "not available in your country" in s or "geo" in s or "blocked it in your country" in s:
        return "geo"
    if "unsupported url" in s or "no video formats" in s or "is not a valid url" in s:
        return "unsupported"
    if "timed out" in s or "unable to download" in s or "network" in s or "connection" in s:
        return "network"
    return "unknown"


_PCT_RE = re.compile(r"\[dl\]\s*([\d.]+)%")


def _parse_percent(line: str) -> Optional[float]:
    """Parse a `[dl] NN.N%` progress line → fraction 0..1, else None."""
    m = _PCT_RE.search(line)
    if not m:
        return None
    try:
        return min(float(m.group(1)) / 100.0, 1.0)
    except ValueError:
        return None


def _is_merge_line(line: str) -> bool:
    return "[merger]" in line.lower() or "merging formats" in line.lower()


def _kill_tree(proc: "subprocess.Popen") -> None:
    """Terminate the whole process tree (yt-dlp + its ffmpeg grandchild).

    stdlib only — no psutil. Windows: `taskkill /F /T`. POSIX: the process was
    started in its own session (start_new_session=True), so kill the group.
    """
    if proc.poll() is not None:
        return
    try:
        if sys.platform == "win32":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True, **_no_window(),
            )
        else:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    except (ProcessLookupError, OSError) as e:
        logger.warning("yt-dlp process-tree kill failed: %s", e)


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

    def probe(self, url: str) -> ProbeResult:
        """Run `yt-dlp --dump-single-json` and structure the result."""
        exe = self._resolve()
        args = [exe, "--dump-single-json", "--no-playlist", "--no-warnings", url]
        try:
            proc = subprocess.run(
                args, capture_output=True, text=True, timeout=60, **_no_window()
            )
        except subprocess.TimeoutExpired:
            return ProbeResult(downloadable=False, reason="network")
        if proc.returncode != 0:
            return ProbeResult(downloadable=False, reason=_classify_error(proc.stderr))
        try:
            info = json.loads(proc.stdout)
        except json.JSONDecodeError:
            return ProbeResult(downloadable=False, reason="unknown")
        formats = [
            {
                "format_id": f.get("format_id", ""),
                "height": f.get("height") or 0,
                "ext": f.get("ext", ""),
                "note": f.get("format_note", ""),
            }
            for f in (info.get("formats") or [])
            if f.get("vcodec") not in (None, "none")  # video-bearing only
        ]
        return ProbeResult(
            downloadable=True,
            title=info.get("title") or "video",
            duration=float(info.get("duration") or 0.0),
            uploader=info.get("uploader") or "",
            thumbnail=info.get("thumbnail") or "",
            formats=formats,
        )

    def download(
        self,
        url: str,
        format_selector: str,
        out_path: Path,
        ffmpeg_dir: str,
        progress_cb: Callable[[float, str], None],
    ) -> Path:
        """Download `url` with the pre-built `format_selector`, merging to MP4.

        Cancellation: `progress_cb` raises TaskCancelledError when the task is
        cancelled; we catch it, kill the whole process tree, and re-raise. The
        merge stage emits few progress lines, so cancel during merge is
        best-effort (may wait for the next line or merge end) — see spec §3.6.
        """
        exe = self._resolve()
        args = [
            exe,
            "-f", format_selector,
            "--merge-output-format", "mp4",  # always produce MP4 (spec §3.4)
            "--ffmpeg-location", ffmpeg_dir,
            "--no-playlist",
            "--newline",
            "--no-warnings",
            "--progress-template", "download:[dl]%(progress._percent_str)s",
            "-o", str(out_path),
            url,
        ]
        popen_kwargs: dict = dict(
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            **_no_window(),
        )
        if sys.platform != "win32":
            popen_kwargs["start_new_session"] = True  # own group for killpg

        proc = subprocess.Popen(args, **popen_kwargs)
        try:
            assert proc.stdout is not None
            for line in proc.stdout:
                pct = _parse_percent(line)
                if pct is not None:
                    progress_cb(pct * 0.95, "task.progress.downloading_video")
                elif _is_merge_line(line):
                    progress_cb(0.97, "task.progress.merging_video")
            proc.wait()
        except BaseException:
            # Covers TaskCancelledError (cooperative cancel) AND any read error.
            _kill_tree(proc)
            raise
        if proc.returncode != 0:
            raise YtDlpError(f"yt-dlp download failed (exit {proc.returncode})")
        return out_path

    @classmethod
    def is_installed(cls) -> bool:
        bin_dir = _ytdlp_bin_dir()
        return (bin_dir / _exe_name()).exists() or shutil.which("yt-dlp") is not None
