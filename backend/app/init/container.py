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
from app.services.setup.compute_settings_service import ComputeSettingsService
from app.services.setup.config_service import ConfigService
from app.services.setup.device_service import DeviceService
from app.services.llm.language_service import LanguageService
from app.services.setup.model_metadata_service import ModelMetadataService
from app.services.setup.remote_service import RemoteService
from app.services.setup.manager_service import SetupService

# ── Task History (lightweight) ──
from app.services.tasks.history_service import TaskHistoryService

# ── Agent Session Persistence (lightweight) ──
from app.services.agent.agent_session_service import AgentSessionService


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


def _lazy_wrapper(module_path: str, class_name: str):
    """Like `_lazy`, but attaches `_model_manager` (passed as the first arg by
    the DI provider) to the constructed wrapper. Replaces the former eager
    attach loop in init_container: every AI wrapper now gets its ModelManager at
    CONSTRUCTION time, wherever/whenever it is first built (warmup thread,
    service injection, or mm._ensure_runtime) — so a service calling
    wrapper.acquire() directly never hits the `_model_manager is None` guard
    (base.py), and construction stays lazy / off the bind path.
    """
    base = _lazy(module_path, class_name)

    def factory(model_manager, *args, **kwargs):
        wrapper = base(*args, **kwargs)
        wrapper._model_manager = model_manager
        return wrapper

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
    yt_dlp_wrapper = providers.Singleton(_lazy("app.adapters.binary.ytdlp", "YtDlpWrapper"))
    model_manager = providers.Singleton(ModelManager)
    llama_runtime = providers.Singleton(
        _lazy_wrapper("app.adapters.ai.wrapper.llm", "LlmWrapper"),
        model_manager,
        slot="llm",
    )

    # ── AI Wrappers (lazy singletons, _model_manager attached at construction) ──
    # Concrete wrapper classes live in `app.adapters.ai.wrapper.*`. The
    # _lazy_wrapper factory attaches `_model_manager` (the model_manager
    # singleton injected as the first arg) when the wrapper is first built, so
    # services that call wrapper.acquire() directly never hit base.py's
    # `_model_manager is None` guard — without an eager construction loop.
    whisper_wrapper = providers.Singleton(
        _lazy_wrapper("app.adapters.ai.wrapper.whisper", "WhisperWrapper"),
        model_manager,
    )
    demucs_wrapper = providers.Singleton(
        _lazy_wrapper("app.adapters.ai.wrapper.demucs", "DemucsWrapper"),
        model_manager,
    )
    alignment_engine = providers.Singleton(
        _lazy_wrapper("app.adapters.ai.wrapper.wav2vec2", "AlignmentEngine"),
        model_manager,
    )
    basic_pitch_wrapper = providers.Singleton(
        _lazy_wrapper("app.adapters.ai.wrapper.basic_pitch", "BasicPitchWrapper"),
        model_manager,
    )
    mobilesam_wrapper = providers.Singleton(
        _lazy_wrapper("app.adapters.ai.wrapper.mobilesam", "MobileSAMWrapper"),
        model_manager,
    )
    rife_wrapper = providers.Singleton(
        _lazy_wrapper("app.adapters.ai.wrapper.rife", "RIFEWrapper"),
        model_manager,
    )
    realesrgan_wrapper = providers.Singleton(
        _lazy_wrapper("app.adapters.ai.wrapper.realesrgan", "RealESRGANWrapper"),
        model_manager,
    )
    swinir_wrapper = providers.Singleton(
        _lazy_wrapper("app.adapters.ai.wrapper.swinir", "SwinIRWrapper"),
        model_manager,
    )
    bsrgan_wrapper = providers.Singleton(
        _lazy_wrapper("app.adapters.ai.wrapper.bsrgan", "BSRGANWrapper"),
        model_manager,
    )
    real_cugan_wrapper = providers.Singleton(
        _lazy_wrapper("app.adapters.ai.wrapper.real_cugan", "RealCUGANWrapper"),
        model_manager,
    )
    waifu2x_wrapper = providers.Singleton(
        _lazy_wrapper("app.adapters.ai.wrapper.waifu2x", "Waifu2xWrapper"),
        model_manager,
    )
    gfpgan_wrapper = providers.Singleton(
        _lazy_wrapper("app.adapters.ai.wrapper.gfpgan", "GFPGANWrapper"),
        model_manager,
    )

    # Family-keyed dicts for dispatcher slots (upscale / face_restore).
    # Services inject these; ModelManager also uses them via registered
    # dispatchers. `providers.Dict` returns a plain dict each call.
    upscalers = providers.Dict(
        realesrgan=realesrgan_wrapper,
        swinir=swinir_wrapper,
        bsrgan=bsrgan_wrapper,
        **{"real-cugan": real_cugan_wrapper},  # hyphenated key
        waifu2x=waifu2x_wrapper,
    )
    face_restorers = providers.Dict(
        gfpgan=gfpgan_wrapper,
    )

    # ── LLM Service ──
    chat_service = providers.Singleton(
        _lazy("app.services.llm.chat_service", "ChatService"),
        llama_runtime=llama_runtime,
    )

    # ── Setup Services ──
    compute_settings_service = providers.Singleton(ComputeSettingsService)
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

    # ── Agent Service ──
    agent_service = providers.Singleton(
        _lazy("app.services.agent.agent_service", "AgentService"),
        chat_service=chat_service,
        remote_service=remote_service,
    )

    # ── Agent Session Persistence ──
    agent_session_service = providers.Singleton(AgentSessionService)

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
        ffmpeg=ffmpeg,
        model_manager=model_manager,
        remote_service=remote_service,
        chat_service=chat_service,
        whisper=whisper_wrapper,
        demucs=demucs_wrapper,
        alignment_engine=alignment_engine,
    )
    audio_separate = providers.Singleton(
        _lazy("app.services.audio.separate_service", "AudioSeparateService"),
        file_service=file_service, task_manager=task_manager,
        model_manager=model_manager,
        demucs=demucs_wrapper,
        basic_pitch=basic_pitch_wrapper,
        ffmpeg=ffmpeg,
    )
    audio_lyrics = providers.Singleton(
        _lazy("app.services.audio.lyrics_service", "AudioLyricsService"),
        file_service=file_service, task_manager=task_manager,
        ffmpeg=ffmpeg,
        model_manager=model_manager,
        remote_service=remote_service,
        chat_service=chat_service,
        whisper=whisper_wrapper,
        demucs=demucs_wrapper,
        alignment_engine=alignment_engine,
    )
    audio_midi = providers.Singleton(
        _lazy("app.services.audio.audio_midi_service", "AudioMidiService"),
        file_service=file_service, task_manager=task_manager,
        ffmpeg=ffmpeg,
    )

    # ── Image Services (lazy) ──
    image_upscale = providers.Singleton(
        _lazy("app.services.image.upscale_service", "ImageUpscaleService"),
        file_service=file_service, task_manager=task_manager,
        model_manager=model_manager,
        upscalers=upscalers,
        face_restorers=face_restorers,
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
        model_manager=model_manager, chat_service=chat_service,
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
        mobilesam=mobilesam_wrapper,
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
        model_manager=model_manager,
        remote_service=remote_service,
        chat_service=chat_service,
        whisper=whisper_wrapper,
        demucs=demucs_wrapper,
        alignment_engine=alignment_engine,
    )
    video_summary = providers.Singleton(
        _lazy("app.services.video.summary_service", "VideoSummaryService"),
        ffmpeg=ffmpeg,
        file_service=file_service,
        task_manager=task_manager,
        chat_service=chat_service,
        model_manager=model_manager,
        remote_service=remote_service,
        whisper=whisper_wrapper,
        demucs=demucs_wrapper,
        alignment_engine=alignment_engine,
    )
    video_interpolate = providers.Singleton(
        _lazy("app.services.video.interpolate_service", "InterpolateService"),
        file_service=file_service, task_manager=task_manager,
        ffmpeg=ffmpeg,
        rife=rife_wrapper,
    )
    video_enhance = providers.Singleton(
        _lazy("app.services.video.enhance_service", "EnhanceService"),
        file_service=file_service, task_manager=task_manager,
        ffmpeg=ffmpeg,
        realesrgan=realesrgan_wrapper,
    )
    video_download = providers.Singleton(
        _lazy("app.services.video.download_service", "VideoDownloadService"),
        yt_dlp_wrapper=yt_dlp_wrapper, ffmpeg=ffmpeg,
        file_service=file_service, task_manager=task_manager,
    )

    # ── Document Services (lazy) ──
    doc_ocr = providers.Singleton(
        _lazy("app.services.document.doc_ocr_service", "DocumentOcrService"),
        file_service=file_service, task_manager=task_manager,
        model_manager=model_manager, chat_service=chat_service,
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
        model_manager=model_manager, chat_service=chat_service,
        remote_service=remote_service,
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
    c = AppContainer()

    # Register wrapper providers with the ModelManager so `_ensure_runtime`
    # resolves wrappers via the same lazy-singleton path the container uses.
    mm = c.model_manager()
    mm.register_runtime_provider("whisper", c.whisper_wrapper)
    mm.register_runtime_provider("demucs", c.demucs_wrapper)
    mm.register_runtime_provider("align", c.alignment_engine)
    mm.register_runtime_provider("basic_pitch", c.basic_pitch_wrapper)
    mm.register_runtime_provider("mobilesam", c.mobilesam_wrapper)
    mm.register_runtime_provider("rife", c.rife_wrapper)

    # LLM registered LAZILY (provider, not eager instance) so LlmWrapper — and
    # the torch import it triggers via base.py — stays off the bind path. The
    # _lazy_wrapper factory attaches _model_manager at construction, which is
    # what satisfies ChatService.session() → llama_runtime.acquire()'s
    # `_model_manager is None` guard (base.py) on the direct-acquire path.
    # (register_runtime_provider only stores the callable; _ensure_runtime
    # constructs + caches on first acquire — model_manager.py.)
    mm.register_runtime_provider("llm", c.llama_runtime)

    # Dispatcher slots: container exposes family→wrapper dicts.
    mm.register_dispatcher("upscale", lambda family: c.upscalers()[family])
    mm.register_dispatcher("face_restore", lambda family: c.face_restorers()[family])

    # NOTE: the former eager attach loop (which constructed every wrapper just
    # to set _model_manager) is REMOVED. _model_manager is now attached at
    # wrapper CONSTRUCTION by the _lazy_wrapper factory, so construction stays
    # lazy and lands off the bind path (background warmup thread / first use),
    # while services that call wrapper.acquire() directly still find it set.

    c.wire(packages=["app.api.routes"])
    _container_instance = c
    return _container_instance
