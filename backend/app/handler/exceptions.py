"""
MediaTranX exception hierarchy.
All custom exceptions in one place.
Route layer uses global exception handlers (error_responses.py) — no try/except needed.
"""


class MediaTranXError(Exception):
    """Base exception for all custom errors."""
    pass


class ModelNotFoundError(MediaTranXError):
    """Model file not found (not downloaded or path invalid)."""
    pass


class ModelLoadError(MediaTranXError):
    """Model loading failed (corrupt weights, format error, OOM)."""
    pass


class InferenceError(MediaTranXError):
    """AI inference error during model execution."""
    pass


class TaskError(MediaTranXError):
    """Task execution error (general business logic)."""
    pass


class FileNotFoundError_(MediaTranXError):
    """File not found in FileService registry."""
    pass


class NotFoundError(MediaTranXError):
    """Generic resource not found (record, task, connection, etc.)."""
    pass


class ConfigError(MediaTranXError):
    """Configuration error (invalid path, illegal value)."""
    pass


class FFmpegError(MediaTranXError):
    """FFmpeg operation failed."""
    pass


class TaskCancelledError(MediaTranXError):
    """Task was cancelled by user."""
    pass


class RemoteApiError(MediaTranXError):
    """
    Remote API error with error code for frontend i18n.

    Attributes:
        code: Error code (maps to frontend i18n key: errors.remote.{code})
        detail: Raw error detail (for debugging)
    """
    def __init__(self, code: str, detail: str = ""):
        self.code = code
        self.detail = detail
        super().__init__(f"[{code}] {detail}")

    def to_dict(self) -> dict:
        return {"error_code": self.code, "detail": self.detail}
