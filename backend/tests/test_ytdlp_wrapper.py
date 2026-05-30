"""YtDlpWrapper unit tests (mock subprocess / path resolution)."""
import sys
from pathlib import Path

import pytest

import app.adapters.binary.ytdlp as ytdlp_mod
from app.adapters.binary.ytdlp import YtDlpWrapper, YtDlpError


def _exe(tmp_path: Path) -> Path:
    name = "yt-dlp.exe" if sys.platform == "win32" else "yt-dlp"
    p = tmp_path / name
    p.write_text("#!stub")
    return p


def test_resolve_prefers_bundled_binary(tmp_path, monkeypatch):
    _exe(tmp_path)
    monkeypatch.setattr(ytdlp_mod, "_ytdlp_bin_dir", lambda: tmp_path)
    w = YtDlpWrapper()  # construction never resolves
    assert Path(w._resolve()).parent == tmp_path


def test_resolve_falls_back_to_system_which(tmp_path, monkeypatch):
    monkeypatch.setattr(ytdlp_mod, "_ytdlp_bin_dir", lambda: tmp_path)  # empty dir
    monkeypatch.setattr(ytdlp_mod.shutil, "which", lambda name: "/usr/bin/yt-dlp")
    w = YtDlpWrapper()
    assert w._resolve() == "/usr/bin/yt-dlp"


def test_resolve_raises_when_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(ytdlp_mod, "_ytdlp_bin_dir", lambda: tmp_path)
    monkeypatch.setattr(ytdlp_mod.shutil, "which", lambda name: None)
    w = YtDlpWrapper()
    with pytest.raises(YtDlpError):
        w._resolve()


def test_construction_never_raises_when_binary_absent(tmp_path, monkeypatch):
    monkeypatch.setattr(ytdlp_mod, "_ytdlp_bin_dir", lambda: tmp_path)
    monkeypatch.setattr(ytdlp_mod.shutil, "which", lambda name: None)
    YtDlpWrapper()  # must not raise — settings/403 path needs this


def test_is_installed_reflects_presence(tmp_path, monkeypatch):
    monkeypatch.setattr(ytdlp_mod, "_ytdlp_bin_dir", lambda: tmp_path)
    monkeypatch.setattr(ytdlp_mod.shutil, "which", lambda name: None)
    assert YtDlpWrapper.is_installed() is False
    _exe(tmp_path)
    assert YtDlpWrapper.is_installed() is True


# ---------------------------------------------------------------------------
# Task 5: probe + _classify_error
# ---------------------------------------------------------------------------
import json
import subprocess
from unittest.mock import MagicMock


def _completed(returncode=0, stdout="", stderr=""):
    cp = MagicMock(spec=subprocess.CompletedProcess)
    cp.returncode = returncode
    cp.stdout = stdout
    cp.stderr = stderr
    return cp


@pytest.fixture
def installed(monkeypatch):
    """A wrapper whose binary resolves to a stub path."""
    monkeypatch.setattr(YtDlpWrapper, "_resolve", lambda self: "yt-dlp")
    return YtDlpWrapper()


def test_probe_parses_single_json(installed, monkeypatch):
    info = {
        "title": "My Clip", "duration": 123, "uploader": "Chan",
        "thumbnail": "http://t/x.jpg",
        "formats": [
            {"format_id": "137", "height": 1080, "ext": "mp4",
             "format_note": "1080p", "vcodec": "avc1"},
            {"format_id": "140", "height": None, "ext": "m4a",
             "format_note": "audio", "vcodec": "none"},  # audio-only filtered out
        ],
    }
    monkeypatch.setattr(ytdlp_mod.subprocess, "run",
                        lambda *a, **k: _completed(0, json.dumps(info)))
    res = installed.probe("http://x")
    assert res.downloadable is True
    assert res.title == "My Clip"
    assert res.duration == 123.0
    assert res.uploader == "Chan"
    assert [f["format_id"] for f in res.formats] == ["137"]  # only video-bearing


def test_probe_nonzero_classifies_reason(installed, monkeypatch):
    monkeypatch.setattr(ytdlp_mod.subprocess, "run",
                        lambda *a, **k: _completed(1, "", "ERROR: Private video. Sign in"))
    res = installed.probe("http://x")
    assert res.downloadable is False
    assert res.reason == "private"


def test_probe_timeout_is_network(installed, monkeypatch):
    def _raise(*a, **k):
        raise subprocess.TimeoutExpired(cmd="yt-dlp", timeout=60)
    monkeypatch.setattr(ytdlp_mod.subprocess, "run", _raise)
    res = installed.probe("http://x")
    assert res.downloadable is False
    assert res.reason == "network"


def test_probe_bad_json_is_unknown(installed, monkeypatch):
    monkeypatch.setattr(ytdlp_mod.subprocess, "run",
                        lambda *a, **k: _completed(0, "<<not json>>"))
    res = installed.probe("http://x")
    assert res.downloadable is False
    assert res.reason == "unknown"


@pytest.mark.parametrize("stderr,expected", [
    ("ERROR: Unsupported URL: http://x", "unsupported"),
    ("ERROR: This video is not available in your country", "geo"),
    ("ERROR: Sign in to confirm your age", "age_restricted"),
    ("ERROR: Private video", "private"),
    ("ERROR: Unable to download webpage: timed out", "network"),
    ("ERROR: something weird", "unknown"),
])
def test_classify_error_table(stderr, expected):
    assert ytdlp_mod._classify_error(stderr) == expected
