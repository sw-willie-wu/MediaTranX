"""
Global FastAPI exception handlers.
Registered on app at startup — routes don't need try/except.
"""
import logging

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from .exceptions import (
    MediaTranXError,
    FileNotFoundError_,
    FFmpegError,
    FeedbackSubmitError,
    RemoteApiError,
    ModelNotFoundError,
    NotFoundError,
)

logger = logging.getLogger(__name__)


def register_exception_handlers(app: FastAPI) -> None:
    """Register all global exception handlers on the FastAPI app."""

    @app.exception_handler(FileNotFoundError_)
    async def handle_not_found(request: Request, exc: FileNotFoundError_):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ModelNotFoundError)
    async def handle_model_not_found(request: Request, exc: ModelNotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(NotFoundError)
    async def handle_generic_not_found(request: Request, exc: NotFoundError):
        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(RemoteApiError)
    async def handle_remote_error(request: Request, exc: RemoteApiError):
        logger.warning(f"Remote API error: {exc}")
        return JSONResponse(status_code=502, content=exc.to_dict())

    @app.exception_handler(FeedbackSubmitError)
    async def handle_feedback_submit_error(request: Request, exc: FeedbackSubmitError):
        logger.warning(f"Feedback submit error: {exc}")
        return JSONResponse(status_code=502, content=exc.to_dict())

    @app.exception_handler(FFmpegError)
    async def handle_ffmpeg_error(request: Request, exc: FFmpegError):
        logger.error(f"FFmpeg error: {exc}")
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    @app.exception_handler(MediaTranXError)
    async def handle_app_error(request: Request, exc: MediaTranXError):
        logger.error(f"Application error: {exc}")
        return JSONResponse(status_code=500, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def handle_value_error(request: Request, exc: ValueError):
        return JSONResponse(status_code=400, content={"detail": str(exc)})
