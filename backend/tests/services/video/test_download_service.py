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


from pathlib import Path

from tests.conftest import make_file_service_mock
from app.schemas.video_download import FormatIntent
import app.services.video.download_service as dl_mod


def test_build_format_selector_auto():
    assert dl_mod._build_format_selector(FormatIntent(mode="auto")) == \
        "bestvideo*+bestaudio/best"


def test_build_format_selector_cap():
    sel = dl_mod._build_format_selector(FormatIntent(mode="cap", max_height=720))
    assert sel == "bestvideo[height<=720]+bestaudio/best[height<=720]"


def test_build_format_selector_ask():
    sel = dl_mod._build_format_selector(FormatIntent(mode="ask", format_id="137"))
    assert sel == "137+bestaudio/best"


def test_build_format_selector_cap_without_height_falls_back_to_auto():
    assert dl_mod._build_format_selector(FormatIntent(mode="cap")) == \
        "bestvideo*+bestaudio/best"


def test_safe_title_strips_illegal_and_separators():
    # illegal chars: / \ : * ? " < > | → each replaced with _
    assert dl_mod._safe_title(r'a/b\c:d*?"<>|') == "a_b_c_d______"
    assert dl_mod._safe_title("   ") == "video"


async def test_submit_forwards_params(real_db, tmp_path):
    ytdlp = MagicMock(); ffmpeg = MagicMock()
    fs = make_file_service_mock(tmp_path); tm = MagicMock()

    async def _async(*a, **k):
        return "tid"
    tm.submit.side_effect = lambda *a, **k: _async(*a, **k)
    svc = VideoDownloadService(yt_dlp_wrapper=ytdlp, ffmpeg=ffmpeg,
                               file_service=fs, task_manager=tm)
    tid = await svc.submit_download("http://x", FormatIntent(mode="cap", max_height=1080), "My Vid")
    assert tid == "tid"
    args, _ = tm.submit.call_args
    assert args[0] == TASK_TYPE_VIDEO_DOWNLOAD
    assert args[1]["url"] == "http://x"
    assert args[1]["title"] == "My Vid"
    assert args[1]["format_intent"]["mode"] == "cap"


def test_handle_task_downloads_and_registers(real_db, tmp_path):
    ytdlp = MagicMock(); ffmpeg = MagicMock()
    ffmpeg.ffmpeg_path = str(tmp_path / "ffmpeg.exe")
    fs = make_file_service_mock(tmp_path); tm = MagicMock()

    def _fake_download(**kw):
        Path(kw["out_path"]).write_bytes(b"video")  # wrapper produces the file
        return kw["out_path"]
    ytdlp.download.side_effect = _fake_download

    svc = VideoDownloadService(yt_dlp_wrapper=ytdlp, ffmpeg=ffmpeg,
                               file_service=fs, task_manager=tm)
    seen = []
    result = svc._handle_task(
        {"url": "http://x", "title": "Clip", "format_intent": {"mode": "auto"}},
        lambda p, m: seen.append((p, m)),
    )
    assert result["title"] == "Clip"
    assert result["output_file_id"]
    # ffmpeg_dir passed as the directory containing ffmpeg
    assert ytdlp.download.call_args.kwargs["ffmpeg_dir"] == str(tmp_path)
    assert ytdlp.download.call_args.kwargs["format_selector"] == "bestvideo*+bestaudio/best"
    assert seen[-1] == (1.0, "task.progress.download_complete")


def test_handle_task_cleans_half_file_on_failure(real_db, tmp_path):
    from app.handler.exceptions import TaskCancelledError
    ytdlp = MagicMock(); ffmpeg = MagicMock()
    ffmpeg.ffmpeg_path = str(tmp_path / "ffmpeg.exe")
    fs = make_file_service_mock(tmp_path); tm = MagicMock()

    written = {}

    def _fake_download(**kw):
        Path(kw["out_path"]).write_bytes(b"partial")
        written["path"] = Path(kw["out_path"])
        raise TaskCancelledError("cancel")
    ytdlp.download.side_effect = _fake_download

    svc = VideoDownloadService(yt_dlp_wrapper=ytdlp, ffmpeg=ffmpeg,
                               file_service=fs, task_manager=tm)
    with pytest.raises(TaskCancelledError):
        svc._handle_task({"url": "http://x", "title": "Clip",
                          "format_intent": {"mode": "auto"}}, lambda p, m: None)
    assert not written["path"].exists()  # half-file removed
