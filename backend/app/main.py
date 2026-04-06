"""
FastAPI application entry point.
"""
from app.init import SETTINGS, bootstrap

bootstrap()

# DI Container (before route imports to satisfy factory functions)
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
        SETTINGS.server.mode = args.mode
        if args.mode == "dev" and SETTINGS.server.log_level == "warning":
            SETTINGS.server.log_level = "debug"
    if args.host:
        SETTINGS.server.host = args.host
    if args.port:
        SETTINGS.server.port = args.port

    # Adjust app log level
    import logging as _logging
    _logging.getLogger().setLevel(
        _logging.DEBUG if SETTINGS.server.mode == "dev" else _logging.WARNING
    )

    uvicorn.run(
        app,
        host=SETTINGS.server.host,
        port=SETTINGS.server.port,
        log_level=SETTINGS.server.log_level,
    )
