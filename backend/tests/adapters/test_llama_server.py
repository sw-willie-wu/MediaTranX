"""Unit tests for pure LlamaServer binary adapter (subprocess + HTTP)."""
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.binary.llama_server import LlamaServer
from app.adapters.ai.wrapper.base import BaseWrapper


def test_llama_server_is_not_a_base_runtime():
    """LlamaServer must be a plain class (binary adapter), not a BaseWrapper subclass."""
    assert not issubclass(LlamaServer, BaseWrapper)


def test_init_creates_empty_server():
    server = LlamaServer()
    assert server.port is None
    assert not server.is_running()


def test_stop_when_not_started_is_noop():
    server = LlamaServer()
    server.stop()  # must not raise
    assert server.port is None


class TestStopDeterminism:
    def test_stop_nulls_state_and_closes_job_on_success(self):
        server = LlamaServer()
        proc = MagicMock()
        proc.poll.return_value = 0  # confirmed dead after wait
        server._process = proc
        server._port = 18080
        server._job = 555
        with patch("app.adapters.binary._proc_lifetime.close_job") as cj:
            server.stop()
        proc.terminate.assert_called_once()
        proc.wait.assert_called_once_with(timeout=10.0)
        cj.assert_called_once_with(555)
        assert server._process is None
        assert server._job is None
        assert server._port is None

    def test_stop_keeps_handle_when_terminate_and_kill_fail(self):
        server = LlamaServer()
        proc = MagicMock()
        proc.terminate.side_effect = OSError("no")
        proc.kill.side_effect = OSError("no")
        proc.poll.return_value = None  # still alive
        server._process = proc
        server._job = 555
        with patch("app.adapters.binary._proc_lifetime.close_job") as cj:
            server.stop()  # must not raise
        assert server._process is proc       # handle retained
        assert server._job == 555            # job retained
        cj.assert_not_called()

    def test_stop_escalates_to_kill_on_terminate_timeout(self):
        server = LlamaServer()
        proc = MagicMock()
        proc.wait.side_effect = [TimeoutError(), None]  # terminate-wait times out
        proc.poll.return_value = 0
        server._process = proc
        server.stop(timeout=2.0)
        proc.terminate.assert_called_once()
        proc.kill.assert_called_once()
        assert server._process is None

    def test_stop_passes_timeout_through_to_wait(self):
        server = LlamaServer()
        proc = MagicMock()
        proc.poll.return_value = 0
        server._process = proc
        server.stop(timeout=3.5)
        proc.wait.assert_called_with(timeout=3.5)
