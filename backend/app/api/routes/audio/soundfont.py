"""SoundFont info & download endpoints for frontend playback."""
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from app.engine.fluidsynth import SF2_FILENAME
from app.init.configs import get_settings

router = APIRouter(prefix="/soundfont", tags=["audio"])


@router.get("/info")
async def soundfont_info():
    sf2_path = Path(get_settings().path.fluidsynth) / SF2_FILENAME
    return {"path": str(sf2_path), "exists": sf2_path.exists()}


@router.get("/download")
async def soundfont_download():
    sf2_path = Path(get_settings().path.fluidsynth) / SF2_FILENAME
    if not sf2_path.exists():
        raise HTTPException(status_code=404, detail="SoundFont not found")
    return FileResponse(
        path=sf2_path,
        filename=SF2_FILENAME,
        media_type="application/octet-stream",
    )
