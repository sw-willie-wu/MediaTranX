"""
Application bootstrap — runs all startup tasks in order.
"""
import logging


def bootstrap(settings) -> None:
    """
    Execute all startup tasks.

    Order matters:
    1. DLL/path injection (so subsequent imports find packages and DLLs)
    2. Compat patches (fix third-party API changes)
    3. Logging config
    4. Nuitka patches (frozen mode only)
    5. Diagnostics (frozen mode only)
    """
    from app.init.dll_injection import inject_paths
    inject_paths(settings)

    from app.init.compat import apply_compat_patches
    apply_compat_patches(settings)

    from app.init.logging_config import configure_logging
    configure_logging(settings)

    if settings.is_frozen:
        from app.init.nuitka_compat import apply_nuitka_patches
        apply_nuitka_patches()

    if settings.is_frozen:
        _run_diagnostics()


def _run_diagnostics() -> None:
    """Frozen mode startup diagnostics."""
    try:
        from app.init.container import get_container
        llama_ok = get_container().model_manager().is_llama_ready()
        logging.info(f"Startup Diagnostic: llama-server binary {'found' if llama_ok else 'NOT found'}")
    except Exception as e:
        logging.error(f"Startup Diagnostic: llama-server check failed: {e}")
