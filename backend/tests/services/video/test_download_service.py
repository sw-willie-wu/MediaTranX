"""VideoDownloadService: registration, settings persistence, gate, probe."""
from __future__ import annotations
from unittest.mock import MagicMock

import pytest

from app.adapters.binary.ytdlp import ProbeResult
from app.services.video.download_service import (
    VideoDownloadService, TASK_TYPE_VIDEO_DOWNLOAD,
)


def _build(real_db):
    ytdlp = MagicMock()
    ffmpeg = MagicMock()
    fs = MagicMock()
    tm = MagicMock()
    svc = VideoDownloadService(yt_dlp_wrapper=ytdlp, ffmpeg=ffmpeg,
                               file_service=fs, task_manager=tm)
    return svc, ytdlp, ffmpeg, fs, tm


def test_registers_handler_with_results_policy(real_db):
    svc, _, _, _, tm = _build(real_db)
    tm.register_handler.assert_called_once()
    args, kwargs = tm.register_handler.call_args
    assert args[0] == TASK_TYPE_VIDEO_DOWNLOAD
    assert kwargs.get("output_policy") == "results"


def test_settings_default_disabled_when_db_empty(real_db):
    svc, *_ = _build(real_db)
    s = svc.get_settings()
    assert s.enabled is False and s.agreed is False
    assert svc.is_enabled() is False


def test_update_settings_persists_and_returns(real_db):
    svc, *_ = _build(real_db)
    out = svc.update_settings({"agreed": True, "enabled": True, "max_height": 720})
    assert out.enabled is True and out.max_height == 720
    # New service instance reads the same DB row.
    svc2, *_ = _build(real_db)
    assert svc2.get_settings().enabled is True


def test_enable_requires_agreement(real_db):
    svc, *_ = _build(real_db)
    out = svc.update_settings({"enabled": True})  # agreed still False
    assert out.enabled is False


def test_probe_delegates_to_wrapper(real_db):
    svc, ytdlp, *_ = _build(real_db)
    ytdlp.probe.return_value = ProbeResult(
        downloadable=True, title="T", duration=10.0, uploader="U",
        formats=[{"format_id": "1", "height": 720, "ext": "mp4", "note": "720p"}],
    )
    resp = svc.probe("http://x")
    assert resp.downloadable is True
    assert resp.title == "T"
    assert resp.formats[0].format_id == "1"
