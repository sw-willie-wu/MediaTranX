"""Soundfont sample file endpoints for frontend playback (web fallback)."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse

from app.handler.exceptions import FileNotFoundError_
from app.init.configs import SETTINGS

router = APIRouter(prefix="/soundfonts", tags=["audio"])


@router.get("/info")
async def soundfonts_info():
    """Return soundfonts directory path and existence check."""
    sf_path = SETTINGS.path.soundfonts.resolve()
    return {"path": str(sf_path), "exists": sf_path.exists()}


@router.get("/sample/{instrument}/{note}")
async def get_sample(instrument: str, note: str):
    """Serve individual instrument sample file (web fallback)."""
    sample_path = SETTINGS.path.soundfonts / instrument / note
    if not sample_path.exists():
        raise FileNotFoundError_(f"Sample not found: {instrument}/{note}")
    return FileResponse(path=sample_path, media_type="audio/mpeg")
