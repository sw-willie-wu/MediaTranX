"""Video URL download service: gate, settings persistence, probe, orchestration."""
import logging
import re
from pathlib import Path

from app.adapters.binary.ffmpeg import FFmpegWrapper
from app.adapters.binary.ytdlp import ProbeResult, YtDlpWrapper
from app.db.dao.app_setting_dao import AppSettingDAO
from app.schemas.video_download import FormatIntent, ProbeResponse, VideoDownloadSettings
from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_VIDEO_DOWNLOAD = "video.download"
SETTINGS_KEY = "video_download"

_ILLEGAL = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def _build_format_selector(intent: FormatIntent) -> str:
    """Service composes the yt-dlp format selector; the wrapper just receives it."""
    if intent.mode == "cap" and intent.max_height:
        n = intent.max_height
        return f"bestvideo[height<={n}]+bestaudio/best[height<={n}]"
    if intent.mode == "ask" and intent.format_id:
        return f"{intent.format_id}+bestaudio/best"
    return "bestvideo*+bestaudio/best"  # auto + all fallbacks


def _safe_title(title: str) -> str:
    """Sanitise an (untrusted) title for use as a filename stem."""
    cleaned = _ILLEGAL.sub("_", (title or "").strip())
    return (cleaned or "video")[:120]


class VideoDownloadService:
    """Owns the feature gate, settings, probe, and download task orchestration."""

    def __init__(
        self,
        yt_dlp_wrapper: YtDlpWrapper,
        ffmpeg: FFmpegWrapper,
        file_service: FileService,
        task_manager: TaskManager,
    ):
        self._ytdlp = yt_dlp_wrapper
        self._ffmpeg = ffmpeg
        self._file_service = file_service
        self._task_manager = task_manager
        self._dao = AppSettingDAO()  # internal, mirrors AgentSessionService (not DI)

        self._task_manager.register_handler(
            TASK_TYPE_VIDEO_DOWNLOAD,
            self._handle_task,
            # "history" → show_in_results=False: the download is loaded straight
            # into the Video tool (not the Results drawer). Single output + no
            # source file, so it is never downgraded to "results". Saving is via
            # the Video tool's titlebar save button.
            output_policy="history",
        )
        logger.info("VideoDownloadService initialized")

    # ── Settings + gate ──
    def get_settings(self) -> VideoDownloadSettings:
        raw = self._dao.get(SETTINGS_KEY) or {}
        return VideoDownloadSettings.model_validate(raw)

    def is_enabled(self) -> bool:
        """Fail-closed: missing/unreadable settings → disabled."""
        return bool(self.get_settings().enabled)

    def update_settings(self, patch: dict) -> VideoDownloadSettings:
        current = self.get_settings().model_dump()
        for key, value in patch.items():
            if value is not None:
                current[key] = value
        merged = VideoDownloadSettings.model_validate(current)
        if merged.enabled and not merged.agreed:
            merged.enabled = False  # defense in depth; UI also enforces
        self._dao.set(SETTINGS_KEY, merged.model_dump())
        return merged

    # ── Probe ──
    def probe(self, url: str) -> ProbeResponse:
        result: ProbeResult = self._ytdlp.probe(url)
        return ProbeResponse.model_validate(result.__dict__)

    # ── Task orchestration (download) ──
    async def submit_download(
        self, url: str, format_intent: FormatIntent, title: str = "video"
    ) -> str:
        params = {
            "url": url,
            "title": title,
            "format_intent": format_intent.model_dump(),
        }
        task_id = await self._task_manager.submit(TASK_TYPE_VIDEO_DOWNLOAD, params)
        logger.info("Video download task submitted: %s", task_id)
        return task_id

    def _handle_task(self, params: dict, progress_callback) -> dict:
        url = params["url"]
        intent = FormatIntent.model_validate(params.get("format_intent") or {})
        title = _safe_title(params.get("title") or "video")
        selector = _build_format_selector(intent)

        output_file_id, output_path = self._file_service.create_output_path(
            original_filename=title, suffix="", ext=".mp4",
        )
        # yt-dlp --ffmpeg-location wants the directory holding ffmpeg + ffprobe.
        ffmpeg_dir = str(Path(self._ffmpeg.ffmpeg_path).parent)

        progress_callback(0.0, "task.progress.download_starting")
        try:
            self._ytdlp.download(
                url=url,
                format_selector=selector,
                out_path=output_path,
                ffmpeg_dir=ffmpeg_dir,
                progress_cb=progress_callback,
            )
        except BaseException:
            # Clean the final file AND yt-dlp's intermediate stream files
            # (e.g. {stem}.f701.mp4.part, {stem}.f140.m4a.part), which share
            # output_path's stem and are left behind when a download is
            # cancelled before the merge step.
            # NOTE: use iterdir()+startswith rather than glob() because the
            # stem may contain glob metacharacters (e.g. '[', ']') from
            # video titles.
            try:
                stem = output_path.stem
                for leftover in output_path.parent.iterdir():
                    if leftover.name.startswith(stem):
                        try:
                            leftover.unlink()
                        except OSError:
                            pass
            except OSError:
                pass
            raise

        output_info = self._file_service.register_output(
            file_id=output_file_id,
            file_path=output_path,
            original_filename=f"{title}.mp4",
            mime_type="video/mp4",
        )
        progress_callback(1.0, "task.progress.download_complete")
        return {
            "output_file_id": output_file_id,
            # Clean, user-facing name (NOT the mangled on-disk name); this is the
            # Video-tool entry label after handoff. register_output keeps the
            # disk file; we surface the title-based name.
            "output_filename": f"{title}.mp4",
            "output_size": output_info.file_size,
            "title": title,
        }
