"""configure_logging must switch stdout/stderr to line buffering.

Packaged core.exe's stdout/stderr is a non-tty pipe → CPython block-buffers it
(4–8KB), so app.log stalls during long tasks and only flushes at process exit.
Line buffering makes the Electron pipe receive output line-by-line.
"""
import io
import sys
from unittest.mock import MagicMock, patch

from app.init.logging_config import configure_logging


def _make_settings(frozen: bool = False) -> MagicMock:
    s = MagicMock()
    s.is_frozen = frozen
    return s


def test_configure_logging_reconfigures_line_buffering():
    fake_out = MagicMock()
    fake_err = MagicMock()
    with patch.object(sys, "stdout", fake_out), patch.object(sys, "stderr", fake_err):
        configure_logging(_make_settings())
    fake_out.reconfigure.assert_called_once_with(line_buffering=True)
    fake_err.reconfigure.assert_called_once_with(line_buffering=True)


def test_configure_logging_tolerates_stream_without_reconfigure():
    class Bare:  # 非標準 stream（無 reconfigure）不得 crash
        def write(self, *_):
            ...

        def flush(self):
            ...

    with patch.object(sys, "stdout", Bare()), patch.object(sys, "stderr", Bare()):
        configure_logging(_make_settings())  # 不拋例外即過


def test_configure_logging_swallows_reconfigure_failure():
    bad = MagicMock()
    bad.reconfigure.side_effect = ValueError("stream not seekable")
    with patch.object(sys, "stdout", bad), patch.object(sys, "stderr", MagicMock()):
        configure_logging(_make_settings())  # 不拋例外即過


def test_configure_logging_swallows_bad_reconfigure_signature():
    # 非標準 wrapper：有 reconfigure 但不吃 line_buffering kwarg → TypeError，不得 crash
    bad = MagicMock()
    bad.reconfigure.side_effect = TypeError("unexpected keyword argument")
    with patch.object(sys, "stdout", bad), patch.object(sys, "stderr", MagicMock()):
        configure_logging(_make_settings())  # 不拋例外即過


def test_configure_logging_actually_sets_line_buffering_on_real_stream():
    # 真 TextIOWrapper（非 mock）：驗證屬性語意真的被設起來，而非只驗呼叫契約
    real_out = io.TextIOWrapper(io.BytesIO(), line_buffering=False)
    real_err = io.TextIOWrapper(io.BytesIO(), line_buffering=False)
    assert real_out.line_buffering is False
    with patch.object(sys, "stdout", real_out), patch.object(sys, "stderr", real_err):
        configure_logging(_make_settings())
    assert real_out.line_buffering is True
    assert real_err.line_buffering is True
