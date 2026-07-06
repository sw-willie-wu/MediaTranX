"""
Unit test for build.py's _copy_vc_runtime helper (Task 2 of the onnxruntime
msvcp140 fix). Verifies the build bundles the MSVC runtime next to core.exe and
degrades gracefully (warn, don't raise) when the source DLLs are absent.

build.py lives at repo-root/scripts/ (outside the `app` package); load it by
path. Its module top level is import-safe (only pure Path constants + an
`if __name__ == "__main__"` guard), so importing it does not run a build.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_BUILD_PY = _REPO_ROOT / "scripts" / "build.py"


def _load_build_module():
    spec = importlib.util.spec_from_file_location("_mediatranx_build", _BUILD_PY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pytestmark = pytest.mark.skipif(
    sys.platform != "win32", reason="_copy_vc_runtime is a no-op off Windows"
)


def _fake_system_root(tmp_path: Path, dll_names) -> Path:
    """Build a fake %SystemRoot% with System32/<dll> files."""
    system32 = tmp_path / "System32"
    system32.mkdir(parents=True)
    for name in dll_names:
        (system32 / name).write_bytes(b"fake dll")
    return tmp_path


def test_copies_both_runtime_dlls(tmp_path, monkeypatch):
    monkeypatch.delenv("VCToolsRedistDir", raising=False)  # redist takes priority over system_root
    build = _load_build_module()
    src_root = _fake_system_root(tmp_path / "win", build._VC_RUNTIME_DLLS)
    dest = tmp_path / "core_service"
    dest.mkdir()

    build._copy_vc_runtime(dest, system_root=str(src_root))

    for name in build._VC_RUNTIME_DLLS:
        assert (dest / name).is_file(), f"{name} should be copied next to core.exe"
        assert (dest / name).read_bytes() == b"fake dll"


def test_missing_source_warns_does_not_raise(tmp_path, capsys, monkeypatch):
    monkeypatch.delenv("VCToolsRedistDir", raising=False)  # redist takes priority over system_root
    build = _load_build_module()
    src_root = _fake_system_root(tmp_path / "win", [])  # empty System32
    dest = tmp_path / "core_service"
    dest.mkdir()

    # Must not raise even when the source DLLs are absent (build must not abort).
    build._copy_vc_runtime(dest, system_root=str(src_root))

    assert not any(dest.iterdir()), "nothing should be copied when source is missing"
    out = capsys.readouterr().out
    assert "WARNING" in out and "msvcp140.dll" in out
