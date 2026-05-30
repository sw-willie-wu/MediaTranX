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
