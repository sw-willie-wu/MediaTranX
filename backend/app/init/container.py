"""
DI Container — single source of truth for all singleton lifecycles.

Domain services (audio/image/video/document) use lazy factories so they are
not imported at startup.  A background thread in lifespan.py triggers the
actual import after the server is already accepting connections, making cold
start feel instant.
"""
from dependency_injector import containers, providers

# ── Infrastructure (lightweight — always eager) ──
from app.services.files.file_service import FileService
from app.workers.progress_tracker import ProgressTracker
from app.workers.task_manager import TaskManager

# ── Engine (lightweight) ──
from app.adapters.binary.ffmpeg import FFmpegWrapper
from app.adapters.ai.model_manager import ModelManager

# ── Setup Services (lightweight — needed for settings page) ──
from app.services.setup.config_service import ConfigService
from app.services.setup.device_service import DeviceService
from app.services.llm.language_service import LanguageService
from app.services.setup.model_metadata_service import ModelMetadataService
from app.services.setup.remote_service import RemoteService
from app.services.setup.manager_service import SetupService

# ── Task History (lightweight) ──
from app.services.tasks.history_service import TaskHistoryService


# ── Lazy factory helper ─────────────────────────────────────────────────────
# Defers `import module; cls(...)` until the Singleton is first accessed.

def _lazy(module_path: str, class_name: str):
    """Return a callable that lazily imports *class_name* from *module_path*.

    `_cls` cache is not lock-protected on purpose: the container is wired at
    startup and every Singleton is resolved from a single event loop or request
    worker; the narrow race (two concurrent first-access) would at worst load
    the module twice (a no-op) under Python's GIL.
    """
    _cls = None

    def factory(*args, **kwargs):
        nonlocal _cls
        if _cls is None:
            mod = __import__(module_path, fromlist=[class_name])
            _cls = getattr(mod, class_name)
        return _cls(*args, **kwargs)

    return factory


class AppContainer(containers.DeclarativeContainer):
    """Application DI container. All singletons registered here."""

    # ── Infrastructure ──
    file_service = providers.Singleton(FileService)
    progress_tracker = providers.Singleton(ProgressTracker)
    task_manager = providers.Singleton(
        TaskManager,
        progress_tracker=progress_tracker,
        file_service=file_service,
    )

    # ── Engine ──
    ffmpeg = providers.Singleton(FFmpegWrapper)
    model_manager = providers.Singleton(ModelManager)
    llama_runtime = providers.Singleton(
        _lazy("app.adapters.ai.wrapper.llm", "LlmWrapper"),
        slot="llm",
    )

    # ── LLM Service ──
    chat_service = providers.Singleton(
        _lazy("app.services.llm.chat_service", "ChatService"),
        llama_runtime=llama_runtime,
    )

    # ── Setup Services ──
    config_service = providers.Singleton(ConfigService)
    device_service = providers.Singleton(DeviceService)
    language_service = providers.Singleton(LanguageService, model_manager=model_manager)
    model_metadata = providers.Singleton(ModelMetadataService, model_manager=model_manager)
    remote_service = providers.Singleton(RemoteService)
    setup_service = providers.Singleton(
        SetupService,
        task_manager=task_manager,
        model_manager=model_manager,
    )

    # ── Task History ──
    task_history = providers.Singleton(TaskHistoryService)

    # ── Audio Services (lazy) ──
    audio_transcode = providers.Singleton(
        _lazy("app.services.audio.transcode_service", "AudioTranscodeService"),
        ffmpeg=ffmpeg, file_service=file_service, task_manager=task_manager,
    )
    audio_cut = providers.Singleton(
        _lazy("app.services.audio.cut_service", "AudioCutService"),
        ffmpeg=ffmpeg, file_service=file_service, task_manager=task_manager,
    )
    audio_volume = providers.Singleton(
        _lazy("app.services.audio.volume_service", "AudioVolumeService"),
        ffmpeg=ffmpeg, file_service=file_service, task_manager=task_manager,
    )
    audio_transcribe = providers.Singleton(
        _lazy("app.services.audio.transcribe_service", "AudioTranscribeService"),
        file_service=file_service, task_manager=task_manager,
        llama_runtime=llama_runtime,
    )
    audio_separate = providers.Singleton(
        _lazy("app.services.audio.separate_service", "AudioSeparateService"),
        file_service=file_service, task_manager=task_manager,
        model_manager=model_manager,
    )
    audio_lyrics = providers.Singleton(
        _lazy("app.services.audio.lyrics_service", "AudioLyricsService"),
        file_service=file_service, task_manager=task_manager,
    )
    audio_midi = providers.Singleton(
        _lazy("app.services.audio.audio_midi_service", "AudioMidiService"),
        file_service=file_service, task_manager=task_manager,
    )

    # ── Image Services (lazy) ──
    image_upscale = providers.Singleton(
        _lazy("app.services.image.upscale_service", "ImageUpscaleService"),
        file_service=file_service, task_manager=task_manager,
        model_manager=model_manager,
    )
    image_crop = providers.Singleton(
        _lazy("app.services.image.crop_service", "ImageCropService"),
        file_service=file_service, task_manager=task_manager,
    )
    image_convert = providers.Singleton(
        _lazy("app.services.image.convert_service", "ImageConvertService"),
        file_service=file_service, task_manager=task_manager,
    )
    image_filter = providers.Singleton(
        _lazy("app.services.image.filter_service", "ImageFilterService"),
        file_service=file_service, task_manager=task_manager,
    )
    image_ocr = providers.Singleton(
        _lazy("app.services.image.ocr_service", "ImageOcrService"),
        file_service=file_service, task_manager=task_manager,
        model_manager=model_manager, llama_runtime=llama_runtime,
        language_service=language_service, remote_service=remote_service,
    )
    image_remove_bg = providers.Singleton(
        _lazy("app.services.image.remove_bg_service", "ImageRemoveBgService"),
        file_service=file_service, task_manager=task_manager,
        model_manager=model_manager,
    )
    image_remove_object = providers.Singleton(
        _lazy("app.services.image.remove_object_service", "ImageRemoveObjectService"),
        file_service=file_service, task_manager=task_manager,
        model_manager=model_manager,
    )

    # ── Video Services (lazy) ──
    video_transcode = providers.Singleton(
        _lazy("app.services.video.transcode_service", "VideoTranscodeService"),
        ffmpeg=ffmpeg, file_service=file_service, task_manager=task_manager,
    )
    video_cut = providers.Singleton(
        _lazy("app.services.video.cut_service", "VideoCutService"),
        ffmpeg=ffmpeg, file_service=file_service, task_manager=task_manager,
    )
    video_crop = providers.Singleton(
        _lazy("app.services.video.crop_service", "VideoCropService"),
        ffmpeg=ffmpeg, file_service=file_service, task_manager=task_manager,
    )
    video_extract_audio = providers.Singleton(
        _lazy("app.services.video.extract_audio_service", "VideoExtractAudioService"),
        ffmpeg=ffmpeg, file_service=file_service, task_manager=task_manager,
    )
    video_subtitle = providers.Singleton(
        _lazy("app.services.video.subtitle_service", "SubtitleService"),
        ffmpeg=ffmpeg, file_service=file_service, task_manager=task_manager,
    )
    video_summary = providers.Singleton(
        _lazy("app.services.video.summary_service", "VideoSummaryService"),
        ffmpeg=ffmpeg,
        file_service=file_service,
        task_manager=task_manager,
        chat_service=chat_service,
    )
    video_interpolate = providers.Singleton(
        _lazy("app.services.video.interpolate_service", "InterpolateService"),
        file_service=file_service, task_manager=task_manager,
        ffmpeg=ffmpeg,
    )
    video_enhance = providers.Singleton(
        _lazy("app.services.video.enhance_service", "EnhanceService"),
        file_service=file_service, task_manager=task_manager,
        ffmpeg=ffmpeg,
    )

    # ── Document Services (lazy) ──
    doc_ocr = providers.Singleton(
        _lazy("app.services.document.doc_ocr_service", "DocumentOcrService"),
        file_service=file_service, task_manager=task_manager,
        model_manager=model_manager, llama_runtime=llama_runtime,
        language_service=language_service, remote_service=remote_service,
    )
    doc_pdf_convert = providers.Singleton(
        _lazy("app.services.document.pdf_convert_service", "DocumentPdfConvertService"),
        file_service=file_service, task_manager=task_manager,
    )
    doc_split = providers.Singleton(
        _lazy("app.services.document.split_service", "DocumentSplitService"),
        file_service=file_service, task_manager=task_manager,
    )
    doc_translate = providers.Singleton(
        _lazy("app.services.document.translate_service", "TranslateService"),
        file_service=file_service, task_manager=task_manager,
        model_manager=model_manager, llama_runtime=llama_runtime,
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
