"""Pydantic models for the video-download feature."""
from __future__ import annotations
from typing import Literal, Optional

from pydantic import BaseModel, Field


class ProbeRequest(BaseModel):
    url: str


class FormatOption(BaseModel):
    format_id: str
    height: int = 0
    ext: str = ""
    note: str = ""


class ProbeResponse(BaseModel):
    downloadable: bool
    title: str = ""
    duration: float = 0.0
    uploader: str = ""
    thumbnail: str = ""
    formats: list[FormatOption] = Field(default_factory=list)
    reason: str = ""


class FormatIntent(BaseModel):
    mode: Literal["auto", "cap", "ask"] = "auto"
    max_height: Optional[int] = None
    format_id: Optional[str] = None


class DownloadRequest(BaseModel):
    url: str
    title: str = "video"  # from the probe card; sanitised server-side for the filename
    format_intent: FormatIntent = Field(default_factory=FormatIntent)


class DownloadResponse(BaseModel):
    task_id: str


class VideoDownloadSettings(BaseModel):
    agreed: bool = False
    enabled: bool = False
    quality_mode: Literal["auto", "cap", "ask"] = "auto"
    max_height: int = 1080


class UpdateSettingsRequest(BaseModel):
    agreed: Optional[bool] = None
    enabled: Optional[bool] = None
    quality_mode: Optional[Literal["auto", "cap", "ask"]] = None
    max_height: Optional[int] = None
