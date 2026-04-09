"""
DI Container — single source of truth for all singleton lifecycles.
"""
from dependency_injector import containers, providers

# ── Infrastructure ──
from app.services.files.file_service import FileService
from app.workers.progress_tracker import ProgressTracker
from app.workers.task_manager import TaskManager

# ── Engine ──
from app.engine.ffmpeg import FFmpegWrapper
from app.engine.ai.model_manager import ModelManager

# ── Setup Services ──
from app.services.setup.config_service import ConfigService
from app.services.setup.device_service import DeviceService
from app.services.setup.language_service import LanguageService
from app.services.setup.model_metadata_service import ModelMetadataService
from app.services.setup.remote_service import RemoteService
from app.services.setup.manager_service import SetupService

# ── Task History ──
from app.services.tasks.history_service import TaskHistoryService

# ── Audio Services ──
from app.services.audio.transcode_service import AudioTranscodeService
from app.services.audio.cut_service import AudioCutService
from app.services.audio.volume_service import AudioVolumeService
from app.services.audio.transcribe_service import AudioTranscribeService
from app.services.audio.separate_service import AudioSeparateService
from app.services.audio.lyrics_service import AudioLyricsService
from app.services.audio.audio_midi_service import AudioMidiService

# ── Image Services ──
from app.services.image.upscale_service import ImageUpscaleService
from app.services.image.crop_service import ImageCropService
from app.services.image.convert_service import ImageConvertService
from app.services.image.filter_service import ImageFilterService
from app.services.image.ocr_service import ImageOcrService
from app.services.image.remove_bg_service import ImageRemoveBgService
from app.services.image.remove_object_service import ImageRemoveObjectService

# ── Video Services ──
from app.services.video.transcode_service import TranscodeService
from app.services.video.subtitle_service import SubtitleService
from app.services.video.interpolate_service import InterpolateService
from app.services.video.enhance_service import EnhanceService

# ── Document Services ──
from app.services.document.doc_ocr_service import DocumentOcrService
from app.services.document.pdf_convert_service import DocumentPdfConvertService
from app.services.document.split_service import DocumentSplitService
from app.services.document.translate_service import TranslateService


class AppContainer(containers.DeclarativeContainer):
    """Application DI container. All singletons registered here."""

    # ── Infrastructure ──
    file_service = providers.Singleton(FileService)
    progress_tracker = providers.Singleton(ProgressTracker)
    task_manager = providers.Singleton(
        TaskManager,
        progress_tracker=progress_tracker,
    )

    # ── Engine ──
    ffmpeg = providers.Singleton(FFmpegWrapper)
    model_manager = providers.Singleton(ModelManager)

    # ── Setup Services ──
    config_service = providers.Singleton(ConfigService)
    device_service = providers.Singleton(DeviceService)
    language_service = providers.Singleton(LanguageService)
    model_metadata = providers.Singleton(ModelMetadataService)
    remote_service = providers.Singleton(RemoteService)
    setup_service = providers.Singleton(
        SetupService,
        task_manager=task_manager,
    )

    # ── Task History ──
    task_history = providers.Singleton(TaskHistoryService)

    # ── Audio Services ──
    audio_transcode = providers.Singleton(
        AudioTranscodeService,
        ffmpeg=ffmpeg, file_service=file_service, task_manager=task_manager,
    )
    audio_cut = providers.Singleton(
        AudioCutService,
        ffmpeg=ffmpeg, file_service=file_service, task_manager=task_manager,
    )
    audio_volume = providers.Singleton(
        AudioVolumeService,
        ffmpeg=ffmpeg, file_service=file_service, task_manager=task_manager,
    )
    audio_transcribe = providers.Singleton(
        AudioTranscribeService,
        file_service=file_service, task_manager=task_manager,
    )
    audio_separate = providers.Singleton(
        AudioSeparateService,
        file_service=file_service, task_manager=task_manager,
    )
    audio_lyrics = providers.Singleton(
        AudioLyricsService,
        file_service=file_service, task_manager=task_manager,
    )
    audio_midi = providers.Singleton(
        AudioMidiService,
        file_service=file_service, task_manager=task_manager,
    )

    # ── Image Services ──
    image_upscale = providers.Singleton(
        ImageUpscaleService,
        file_service=file_service, task_manager=task_manager,
    )
    image_crop = providers.Singleton(
        ImageCropService,
        file_service=file_service, task_manager=task_manager,
    )
    image_convert = providers.Singleton(
        ImageConvertService,
        file_service=file_service, task_manager=task_manager,
    )
    image_filter = providers.Singleton(
        ImageFilterService,
        file_service=file_service, task_manager=task_manager,
    )
    image_ocr = providers.Singleton(
        ImageOcrService,
        file_service=file_service, task_manager=task_manager,
    )
    image_remove_bg = providers.Singleton(
        ImageRemoveBgService,
        file_service=file_service, task_manager=task_manager,
    )
    image_remove_object = providers.Singleton(
        ImageRemoveObjectService,
        file_service=file_service, task_manager=task_manager,
    )

    # ── Video Services ──
    video_transcode = providers.Singleton(
        TranscodeService,
        ffmpeg=ffmpeg, file_service=file_service, task_manager=task_manager,
    )
    video_subtitle = providers.Singleton(
        SubtitleService,
        ffmpeg=ffmpeg, file_service=file_service, task_manager=task_manager,
    )
    video_interpolate = providers.Singleton(
        InterpolateService,
        file_service=file_service, task_manager=task_manager,
    )
    video_enhance = providers.Singleton(
        EnhanceService,
        file_service=file_service, task_manager=task_manager,
    )

    # ── Document Services ──
    doc_ocr = providers.Singleton(
        DocumentOcrService,
        file_service=file_service, task_manager=task_manager,
    )
    doc_pdf_convert = providers.Singleton(
        DocumentPdfConvertService,
        file_service=file_service, task_manager=task_manager,
    )
    doc_split = providers.Singleton(
        DocumentSplitService,
        file_service=file_service, task_manager=task_manager,
    )
    doc_translate = providers.Singleton(
        TranslateService,
        file_service=file_service, task_manager=task_manager,
    )


# Global container instance — initialized in main.py
_container_instance: AppContainer | None = None


def get_container() -> AppContainer:
    """Get the global container instance."""
    if _container_instance is None:
        raise RuntimeError("AppContainer not initialized. Call init_container() first.")
    return _container_instance


def init_container() -> AppContainer:
    """Initialize the global container. Called once at startup."""
    global _container_instance
    _container_instance = AppContainer()
    _container_instance.wire(packages=["app.api.routes"])
    return _container_instance
