"""
Application lifespan — startup and shutdown hooks.
"""
import logging
import threading
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import init_db
from app.init.container import get_container
from app.init.migrate_secrets import migrate_plaintext_keys

LOGGER = logging.getLogger(__name__)


def _warmup_setup_services(container) -> None:
    """Pre-initialize setup-critical services so settings page loads instantly."""
    container.config_service()
    container.language_service()
    container.remote_service()
    container.model_manager()
    container.model_metadata()
    container.device_service()
    LOGGER.info("Setup services pre-warmed")


def _warmup_domain_services(container) -> None:
    """Background-import all domain services (heavy AI dependencies).

    Called in a daemon thread after the server is already accepting
    connections, so the user sees the UI immediately while torch/numpy/PIL
    etc. load silently in the background.
    """
    start = time.monotonic()

    # Log the environment first (OS/GPU/compute-capability/driver/torch build) so
    # a tester's app.log is self-describing. In the background thread so the torch
    # import it triggers doesn't block startup; runs well before any task.
    try:
        from app.init.configs import SETTINGS
        from app.init.system_info import log_system_info
        log_system_info(SETTINGS)
    except Exception as e:
        LOGGER.warning(f"system info logging failed: {e}")

    providers = [
        # Audio
        container.audio_transcode,
        container.audio_cut,
        container.audio_volume,
        container.audio_transcribe,
        container.audio_separate,
        container.audio_lyrics,
        container.audio_midi,
        # Image
        container.image_upscale,
        container.image_crop,
        container.image_convert,
        container.image_filter,
        container.image_ocr,
        container.image_remove_bg,
        container.image_remove_object,
        # Video
        container.video_transcode,
        container.video_cut,
        container.video_crop,
        container.video_extract_audio,
        container.video_subtitle,
        container.video_summary,
        container.video_interpolate,
        container.video_enhance,
        # Document
        container.doc_ocr,
        container.doc_pdf_convert,
        container.doc_split,
        container.doc_translate,
    ]
    for provider in providers:
        try:
            provider()
        except Exception as e:
            LOGGER.warning(f"Background warmup failed for {provider}: {e}")
    elapsed = time.monotonic() - start
    LOGGER.info(f"Domain services warmed up in background ({elapsed:.1f}s)")


def _persist_terminal_history(history, file_service, task) -> None:
    """Persist a terminated task to history, resolving its input file name.

    Module-level (not a lifespan closure) so it is unit-testable. Does NOT
    swallow exceptions — the ``_on_terminal`` caller wraps it in try/except.
    """
    result = task.result if isinstance(task.result, dict) else None
    history.save(
        task_id=task.task_id,
        task_type=task.task_type,
        status=task.status.value,
        created_at=task.created_at,
        completed_at=task.updated_at,
        file_name=file_service.get_file_name(task.file_id),
        error=task.error,
        error_code=task.error_code,
        result=result,
    )


def build_lifespan():
    """Build a lifespan context manager for the FastAPI app."""

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # ── Startup ──
        init_db()
        LOGGER.info("Database initialized")

        try:
            migrate_plaintext_keys()
        except Exception:
            LOGGER.exception("secret key migration failed (continuing)")

        container = get_container()
        history = container.task_history()
        tm = container.task_manager()
        file_service = container.file_service()

        def _on_terminal(task):
            try:
                _persist_terminal_history(history, file_service, task)
            except Exception as e:
                LOGGER.warning(f"Failed to save task history: {e}")

        tm.on_terminal(_on_terminal)
        LOGGER.info("Task history hook registered")

        # Restore output files with sidecars from previous session
        container.file_service().scan_output_dir()
        LOGGER.info("Output files restored from sidecars")

        _warmup_setup_services(container)

        # Apply persisted CPU-fallback policy before any task can run.
        try:
            from app.adapters import device as _device
            _cs = container.compute_settings_service().get_settings()
            _device.set_allow_cpu_fallback(_cs.allow_cpu_fallback)
            LOGGER.info("CPU-fallback policy applied: allow=%s", _cs.allow_cpu_fallback)
        except Exception:
            LOGGER.exception("Failed to apply CPU-fallback policy (using default ON)")

        # Import heavy domain services in the background so the server
        # starts accepting connections immediately (cold-start optimization).
        threading.Thread(
            target=_warmup_domain_services,
            args=(container,),
            daemon=True,
            name="domain-warmup",
        ).start()

        yield

        # ── Shutdown ──
        LOGGER.info("Shutting down...")
        tm.shutdown()
        LOGGER.info("Shutdown complete")

    return lifespan
