"""Bundled ffmpeg must be discoverable by bare name (PATH lookup).

Third-party libs shell out to ``ffmpeg``/``ffprobe`` without a path — demucs'
``AudioFile`` runs ``sp.check_output(['ffprobe', ...])``. On a machine with no
system ffmpeg that raises FileNotFoundError and demucs reports "FFmpeg is not
installed" (1.7.1 field report: audio.transcribe + vocal_separation on .aac,
where the torchaudio fallback also can't decode). Our own FFmpegWrapper uses an
absolute path and never saw the problem.
"""
import os
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace

from app.init.setup import register_bundled_binaries

EXE = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"


def _settings(bin_dir: Path):
    return SimpleNamespace(path=SimpleNamespace(ffmpeg=bin_dir))


def _make_bundle(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin" / "ffmpeg"
    bin_dir.mkdir(parents=True)
    (bin_dir / EXE).write_text("")
    return bin_dir


def test_bundled_ffmpeg_dir_is_prepended_to_path(tmp_path, monkeypatch):
    bin_dir = _make_bundle(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path / "elsewhere"))

    register_bundled_binaries(_settings(bin_dir))

    assert os.environ["PATH"].split(os.pathsep)[0] == str(bin_dir)


def test_bare_name_lookup_finds_the_bundled_binary(tmp_path, monkeypatch):
    """The property demucs actually depends on."""
    bin_dir = _make_bundle(tmp_path)
    monkeypatch.setenv("PATH", "")

    register_bundled_binaries(_settings(bin_dir))

    found = shutil.which("ffmpeg")
    assert found is not None and Path(found).parent == bin_dir


def test_noop_when_no_bundled_copy_exists(tmp_path, monkeypatch):
    """Non-Windows / dev without bin/: leave PATH alone, system ffmpeg wins."""
    monkeypatch.setenv("PATH", "/usr/bin")

    register_bundled_binaries(_settings(tmp_path / "bin" / "ffmpeg"))

    assert os.environ["PATH"] == "/usr/bin"


def test_is_idempotent(tmp_path, monkeypatch):
    bin_dir = _make_bundle(tmp_path)
    monkeypatch.setenv("PATH", str(tmp_path / "elsewhere"))

    register_bundled_binaries(_settings(bin_dir))
    before = os.environ["PATH"]
    register_bundled_binaries(_settings(bin_dir))

    assert os.environ["PATH"] == before
