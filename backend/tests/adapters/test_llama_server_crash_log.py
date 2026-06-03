"""Tests for llama-server crash-log surfacing.

When llama-server exits unexpectedly during _wait_ready(), the backend now
reads the tail of llama_server.log and emits it via logger.error so it lands
in app.log and core_error.log — making clean-machine crash diagnosis self-serve.
"""
from __future__ import annotations

import logging
import pytest

from app.adapters.binary.llama_server import LlamaServer


# ---------------------------------------------------------------------------
# _read_log_tail
# ---------------------------------------------------------------------------

def test_read_log_tail_returns_last_lines(tmp_path):
    """Returns the last max_lines lines of the file at _log_path."""
    p = tmp_path / "llama_server.log"
    p.write_text("\n".join(f"line{i}" for i in range(100)), encoding="utf-8")
    s = LlamaServer()
    s._log_path = p
    tail = s._read_log_tail(max_lines=10)
    assert "line99" in tail
    assert "line90" in tail
    assert "line50" not in tail


def test_read_log_tail_returns_full_content_when_file_shorter_than_max(tmp_path):
    """If the file has fewer lines than max_lines, all lines are returned."""
    p = tmp_path / "llama_server.log"
    p.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")
    s = LlamaServer()
    s._log_path = p
    tail = s._read_log_tail(max_lines=40)
    assert "alpha" in tail
    assert "gamma" in tail


def test_read_log_tail_safe_when_no_path_set():
    """Returns '' when _log_path is None (path never assigned)."""
    s = LlamaServer()
    assert s._read_log_tail() == ""


def test_read_log_tail_safe_when_file_missing(tmp_path):
    """Returns '' when _log_path points at a non-existent file."""
    s = LlamaServer()
    s._log_path = tmp_path / "nope.log"
    assert s._read_log_tail() == ""


def test_read_log_tail_handles_encoding_errors(tmp_path):
    """Returns content (with replacement chars) rather than raising on bad bytes."""
    p = tmp_path / "llama_server.log"
    p.write_bytes(b"good line\n\xff\xfe bad bytes\nend line\n")
    s = LlamaServer()
    s._log_path = p
    tail = s._read_log_tail()
    # Should not raise; result is a string
    assert isinstance(tail, str)
    assert "good line" in tail or "end line" in tail  # at least some content


# ---------------------------------------------------------------------------
# _wait_ready — unexpected-exit path
# ---------------------------------------------------------------------------

class _DeadProc:
    """Minimal Popen stand-in that looks already-exited."""
    returncode = 3221225477

    def poll(self):
        return self.returncode


def test_wait_ready_raises_runtime_error_with_exit_code_when_proc_dead(tmp_path):
    """_wait_ready raises RuntimeError containing the exit code."""
    p = tmp_path / "llama_server.log"
    p.write_text("ggml_cuda_init: failed\nCUDA error: no kernel image is available\n", encoding="utf-8")

    s = LlamaServer()
    s._log_path = p
    s._port = 18099
    s._process = _DeadProc()

    with pytest.raises(RuntimeError) as ei:
        s._wait_ready()
    assert "3221225477" in str(ei.value)


def test_wait_ready_logs_crash_tail_at_error_level(tmp_path, caplog):
    """When the process is already dead, the log tail is emitted at ERROR level."""
    p = tmp_path / "llama_server.log"
    p.write_text(
        "ggml_cuda_init: failed\nCUDA error: no kernel image is available\n",
        encoding="utf-8",
    )

    s = LlamaServer()
    s._log_path = p
    s._port = 18099
    s._process = _DeadProc()

    with caplog.at_level(logging.ERROR, logger="app.adapters.binary.llama_server"):
        with pytest.raises(RuntimeError):
            s._wait_ready()

    assert "no kernel image" in caplog.text


def test_wait_ready_log_tail_appears_in_error_record(tmp_path, caplog):
    """Full integration: crash tail text surfaces into the logger.error call."""
    p = tmp_path / "llama_server.log"
    crash_lines = "\n".join([
        "llama_model_load: loading model from /models/foo.gguf",
        "ggml_cuda_init: CUDA error 35",
        "CUDA error: no kernel image is available for execution on the device",
        "error loading model",
    ])
    p.write_text(crash_lines, encoding="utf-8")

    s = LlamaServer()
    s._log_path = p
    s._port = 18099
    s._process = _DeadProc()

    with caplog.at_level(logging.ERROR, logger="app.adapters.binary.llama_server"):
        with pytest.raises(RuntimeError):
            s._wait_ready()

    # The tail text must be surfaced in the ERROR log record
    assert any(
        "no kernel image" in record.message
        for record in caplog.records
        if record.levelno == logging.ERROR
    )
    assert any(
        "3221225477" in record.message
        for record in caplog.records
        if record.levelno == logging.ERROR
    )


def test_wait_ready_no_log_call_when_tail_is_empty(tmp_path, caplog):
    """If the log file is missing, no ERROR is logged for the tail (but RuntimeError still raised)."""
    s = LlamaServer()
    s._log_path = tmp_path / "missing.log"  # doesn't exist
    s._port = 18099
    s._process = _DeadProc()

    with caplog.at_level(logging.ERROR, logger="app.adapters.binary.llama_server"):
        with pytest.raises(RuntimeError):
            s._wait_ready()

    # No tail-specific ERROR should be logged (tail is empty → skip logger.error)
    tail_records = [
        r for r in caplog.records
        if r.levelno == logging.ERROR and "Last llama-server output" in r.message
    ]
    assert tail_records == []


def test_wait_ready_raises_quickly_with_dead_proc(tmp_path):
    """_wait_ready must raise on iteration 1 (not wait for timeout) when proc is dead."""
    import time

    p = tmp_path / "llama_server.log"
    p.write_text("crash\n", encoding="utf-8")

    s = LlamaServer()
    s._log_path = p
    s._port = 18099
    s._process = _DeadProc()

    start = time.monotonic()
    with pytest.raises(RuntimeError):
        s._wait_ready(timeout=180)
    elapsed = time.monotonic() - start

    # Should complete well within 5 seconds (not wait the full 180s timeout)
    assert elapsed < 5.0, f"_wait_ready took {elapsed:.1f}s with dead proc — should be instant"


# ---------------------------------------------------------------------------
# __init__ attrs
# ---------------------------------------------------------------------------

def test_init_has_log_path_attr():
    """LlamaServer.__init__ must initialise _log_path to None."""
    s = LlamaServer()
    assert hasattr(s, "_log_path")
    assert s._log_path is None


# ---------------------------------------------------------------------------
# _classify_exit_code + LlamaServerCrashError
# ---------------------------------------------------------------------------

from app.adapters.binary.llama_server import _classify_exit_code, LlamaServerCrashError


def test_classify_exit_code_access_violation():
    is_hard, reason = _classify_exit_code(3221225477)  # 0xC0000005
    assert is_hard is True
    assert "ACCESS_VIOLATION" in reason
    assert "0xC0000005" in reason


def test_classify_exit_code_other_nt_exceptions():
    assert _classify_exit_code(0xC0000409)[0] is True   # STACK_BUFFER_OVERRUN
    assert _classify_exit_code(0xC000001D)[0] is True   # ILLEGAL_INSTRUCTION


def test_classify_exit_code_graceful_exit_is_not_hard_crash():
    is_hard, reason = _classify_exit_code(1)
    assert is_hard is False
    assert "1" in reason


def test_wait_ready_raises_llama_crash_error_with_attrs(tmp_path):
    p = tmp_path / "llama_server.log"
    p.write_text("CUDA error: no kernel image is available\n", encoding="utf-8")
    s = LlamaServer()
    s._log_path = p
    s._port = 18099
    s._process = _DeadProc()  # returncode = 3221225477

    with pytest.raises(LlamaServerCrashError) as ei:
        s._wait_ready()
    exc = ei.value
    assert exc.is_hard_crash is True
    assert "ACCESS_VIOLATION" in exc.reason
    assert exc.code == 3221225477
    assert "3221225477" in str(exc)  # raw code preserved for existing assertions
