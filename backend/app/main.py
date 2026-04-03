"""
FastAPI application entry point.
"""
import os
import sys


def _detect_frozen() -> bool:
    """Detect if running as Nuitka/PyInstaller compiled binary."""
    if getattr(sys, 'frozen', False) or hasattr(sys, "nuitka_binary"):
        return True
    if "__compiled__" in globals():
        return True
    exe_path = sys.executable.lower()
    if exe_path.endswith('core.exe') or ('resources' in exe_path and 'python.exe' not in exe_path):
        return True
    return False


# --- 0. Fix import paths for frozen mode ---
is_frozen = _detect_frozen()
if is_frozen:
    _internal_path = os.path.dirname(sys.executable)
    if _internal_path not in sys.path:
        sys.path.insert(0, _internal_path)

# --- 1. Initialize settings ---
from app.init.configs import init_settings
settings = init_settings(is_frozen=is_frozen, platform=sys.platform)

# --- 2. Bootstrap (DLL injection, compat patches, logging) ---
from app.init import bootstrap
bootstrap(settings)

# --- 3. DI Container (before route imports to satisfy factory functions) ---
from app.init.container import init_container
container = init_container()

# --- 4. App ---
from fastapi import FastAPI
from app.api import build_router
from app.handler.error_responses import register_exception_handlers

from app.init.lifespan import build_lifespan
app: FastAPI = FastAPI(title="MediaTranX API", lifespan=build_lifespan())
register_exception_handlers(app)
app.container = container

app = build_router(app)

# --- 5. Start ---
if __name__ == "__main__":
    import argparse
    import uvicorn

    parser = argparse.ArgumentParser(description="MediaTranX Backend")
    parser.add_argument("--host", type=str, default=None)
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--mode", type=str, default=None, choices=["production", "dev"])
    args = parser.parse_args()

    # Override settings with CLI args if provided
    if args.mode:
        settings.server.mode = args.mode
        if args.mode == "dev" and settings.server.log_level == "warning":
            settings.server.log_level = "debug"
    if args.host:
        settings.server.host = args.host
    if args.port:
        settings.server.port = args.port

    # Adjust app log level
    import logging as _logging
    _logging.getLogger().setLevel(
        _logging.DEBUG if settings.server.mode == "dev" else _logging.WARNING
    )

    uvicorn.run(
        app,
        host=settings.server.host,
        port=settings.server.port,
        log_level=settings.server.log_level,
    )
