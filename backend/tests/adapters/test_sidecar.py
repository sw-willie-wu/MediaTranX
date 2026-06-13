"""Tests for CliSidecar (adapters/binary/sidecar.py) — real subprocesses
via sys.executable; no model binaries needed."""
import sys

import pytest

from app.adapters.binary.sidecar import CliSidecar, SidecarError


def test_runs_and_returns_zero_exit():
    sc = CliSidecar(exe=sys.executable)
    assert sc.run(["-c", "print('hello')"]) == 0


def test_nonzero_exit_raises_sidecar_error_with_tail():
    sc = CliSidecar(exe=sys.executable)
    with pytest.raises(SidecarError) as ei:
        sc.run(["-c", "import sys; print('boom-detail'); sys.exit(3)"])
    assert ei.value.code == 3
    assert "boom-detail" in str(ei.value)


def test_progress_callback_receives_merged_lines():
    seen = []
    sc = CliSidecar(exe=sys.executable, on_line=seen.append)
    sc.run(["-c", "import sys; print('p:0.5', file=sys.stderr)"])
    assert any("p:0.5" in line for line in seen)


def test_on_line_exception_does_not_break_run():
    def boom(line):
        raise ValueError("callback bug")
    sc = CliSidecar(exe=sys.executable, on_line=boom)
    assert sc.run(["-c", "print('x'); print('y')"]) == 0


def test_timeout_kills_child_and_raises_sidecar_error():
    sc = CliSidecar(exe=sys.executable)
    with pytest.raises(SidecarError, match="timeout") as ei:
        sc.run(["-c", "import time; time.sleep(60)"], timeout=1.0)
    assert ei.value.code == -1
    assert ei.value.is_hard_crash is False


def test_missing_exe_raises_file_not_found():
    sc = CliSidecar(exe="definitely-not-a-real-binary-xyz")
    with pytest.raises(FileNotFoundError):
        sc.run(["--version"])


def test_non_utf8_output_does_not_crash_pump():
    # cp950/utf-8 mix: errors="replace" must keep the pump alive to EOF.
    sc = CliSidecar(exe=sys.executable)
    code = sc.run(["-c", "import sys; sys.stdout.buffer.write(b'\\xff\\xfe ok\\n')"])
    assert code == 0
