"""Video URL download service: gate, settings persistence, probe, orchestration."""
import logging

from app.adapters.binary.ffmpeg import FFmpegWrapper
from app.adapters.binary.ytdlp import ProbeResult, YtDlpWrapper
from app.db.dao.app_setting_dao import AppSettingDAO
from app.schemas.video_download import ProbeResponse, VideoDownloadSettings
from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_VIDEO_DOWNLOAD = "video.download"
SETTINGS_KEY = "video_download"


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
            output_policy="results",  # a downloaded video is a new artefact
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

    # ── Task orchestration (download) — implemented in Task 9 ──
    def _handle_task(self, params: dict, progress_callback) -> dict:
        raise NotImplementedError  # Task 9
