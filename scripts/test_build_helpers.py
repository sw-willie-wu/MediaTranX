"""Tests for build.py unit-testable helpers (run from repo root):
uv run --project backend --extra dev python -m pytest scripts/test_build_helpers.py -v

Loaded via importlib because `import build` would collide with the repo-root
build/ output directory.
"""
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "mtx_build", Path(__file__).parent / "build.py")
build = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(build)


def test_uv_run_prefix_frozen():
    p = build._uv_run_prefix(True)
    assert p[:3] == ["uv", "run", "--frozen"]
    assert "nuitka==4.0.8" in p


def test_uv_run_prefix_default_has_no_frozen():
    p = build._uv_run_prefix(False)
    assert p[:2] == ["uv", "run"]
    assert "--frozen" not in p
    assert "nuitka==4.0.8" in p


def _make_dlls(dir_: Path, marker: bytes):
    dir_.mkdir(parents=True, exist_ok=True)
    for name in build._VC_RUNTIME_DLLS:
        (dir_ / name).write_bytes(marker)


def test_copy_vc_runtime_prefers_redist_env(tmp_path, monkeypatch):
    redist = tmp_path / "Redist" / "MSVC" / "14.44.35211"
    _make_dlls(redist / "x64" / "Microsoft.VC143.CRT", b"redist")
    sysroot = tmp_path / "winroot"
    _make_dlls(sysroot / "System32", b"system32")
    monkeypatch.setenv("VCToolsRedistDir", str(redist))
    dest = tmp_path / "dest"
    dest.mkdir()
    build._copy_vc_runtime(dest, system_root=str(sysroot))
    assert (dest / "msvcp140.dll").read_bytes() == b"redist"


def test_copy_vc_runtime_falls_back_to_system32(tmp_path, monkeypatch):
    monkeypatch.delenv("VCToolsRedistDir", raising=False)
    sysroot = tmp_path / "winroot"
    _make_dlls(sysroot / "System32", b"system32")
    dest = tmp_path / "dest"
    dest.mkdir()
    build._copy_vc_runtime(dest, system_root=str(sysroot))
    assert (dest / "msvcp140.dll").read_bytes() == b"system32"


def test_copy_vc_runtime_bad_redist_falls_back(tmp_path, monkeypatch):
    monkeypatch.setenv("VCToolsRedistDir", str(tmp_path / "nonexistent"))
    sysroot = tmp_path / "winroot"
    _make_dlls(sysroot / "System32", b"system32")
    dest = tmp_path / "dest"
    dest.mkdir()
    build._copy_vc_runtime(dest, system_root=str(sysroot))
    assert (dest / "msvcp140.dll").read_bytes() == b"system32"
