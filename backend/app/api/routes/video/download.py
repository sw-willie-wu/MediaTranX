"""Video URL download routes: probe, download, settings."""
from __future__ import annotations
from typing import TYPE_CHECKING

from dependency_injector.wiring import inject, Provide
from fastapi import APIRouter, Depends, HTTPException

from app.init.container import AppContainer
from app.schemas.video_download import (
    DownloadRequest, DownloadResponse, ProbeRequest, ProbeResponse,
    UpdateSettingsRequest, VideoDownloadSettings,
)

if TYPE_CHECKING:
    from app.services.video.download_service import VideoDownloadService

router = APIRouter()


def _ensure_enabled(service: "VideoDownloadService") -> None:
    """Server-side fail-closed gate (frontend hides; backend rejects)."""
    if not service.is_enabled():
        raise HTTPException(status_code=403, detail={"code": "feature_disabled"})


@router.post("/download/probe", response_model=ProbeResponse)
@inject
async def probe_url(
    request: ProbeRequest,
    service: "VideoDownloadService" = Depends(Provide[AppContainer.video_download]),
):
    _ensure_enabled(service)
    return service.probe(request.url)


@router.post("/download", response_model=DownloadResponse)
@inject
async def start_download(
    request: DownloadRequest,
    service: "VideoDownloadService" = Depends(Provide[AppContainer.video_download]),
):
    _ensure_enabled(service)
    task_id = await service.submit_download(
        request.url, request.format_intent, request.title,
        suppress_results=request.suppress_results,
    )
    return DownloadResponse(task_id=task_id)


@router.get("/download/settings", response_model=VideoDownloadSettings)
@inject
async def read_settings(
    service: "VideoDownloadService" = Depends(Provide[AppContainer.video_download]),
):
    return service.get_settings()


@router.put("/download/settings", response_model=VideoDownloadSettings)
@inject
async def write_settings(
    request: UpdateSettingsRequest,
    service: "VideoDownloadService" = Depends(Provide[AppContainer.video_download]),
):
    return service.update_settings(request.model_dump(exclude_none=True))
