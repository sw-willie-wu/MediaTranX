"""Media category inference utility.

Maps file extensions to the four UX categories used by Results drawer
and cross-tool routing. Keep this aligned with
`core/frontend/src/utils/mediaType.ts` (frontend mirror).
"""
from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional


class MediaKind(str, Enum):
    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    DOCUMENT = "document"


_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".tiff", ".tif", ".svg", ".ico", ".avif", ".heic", ".heif"}
_AUDIO_EXTS = {".mp3", ".wav", ".flac", ".ogg", ".aac", ".m4a", ".wma", ".opus", ".mid", ".midi"}
_VIDEO_EXTS = {".mp4", ".mov", ".webm", ".avi", ".mkv", ".flv", ".wmv", ".m4v"}
_DOCUMENT_EXTS = {".pdf", ".doc", ".docx", ".txt", ".srt", ".vtt", ".md", ".csv", ".json", ".html", ".odt"}


def infer_kind(filename: str) -> Optional[MediaKind]:
    """Return the MediaKind for a filename's extension, or None if unknown."""
    ext = Path(filename).suffix.lower()
    if ext in _IMAGE_EXTS:
        return MediaKind.IMAGE
    if ext in _AUDIO_EXTS:
        return MediaKind.AUDIO
    if ext in _VIDEO_EXTS:
        return MediaKind.VIDEO
    if ext in _DOCUMENT_EXTS:
        return MediaKind.DOCUMENT
    return None
