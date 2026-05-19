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


class TestStartBindingAndIdempotency:
    def _patch_settings(self, tmp_path):
        """Return a patcher making SETTINGS.path.llama/.log point at tmp dirs
        and a fake llama-server.exe exist."""
        llama_dir = tmp_path / "llama"
        llama_dir.mkdir()
        (llama_dir / "llama-server.exe").write_bytes(b"")
        (llama_dir / "llama-server").write_bytes(b"")
        log_dir = tmp_path / "log"
        fake = MagicMock()
        fake.path.llama = llama_dir
        fake.path.log = log_dir
        return patch("app.init.configs.SETTINGS", fake)

    def test_start_assigns_child_to_job(self, tmp_path):
        server = LlamaServer()
        fake_proc = MagicMock()
        fake_proc._handle = 4321
        fake_proc.poll.return_value = None
        with self._patch_settings(tmp_path), \
             patch("app.adapters.binary.llama_server.subprocess.Popen",
                   return_value=fake_proc), \
             patch.object(LlamaServer, "_wait_ready"), \
             patch("app.adapters.binary._proc_lifetime.create_kill_on_close_job",
                   return_value=555) as mk, \
             patch("app.adapters.binary._proc_lifetime.assign_process_to_job",
                   return_value=True) as asg:
            server.start(model_path=tmp_path / "m.gguf", n_ctx=4096, n_gpu_layers=99)
        mk.assert_called_once()
        asg.assert_called_once_with(555, 4321)  # int(popen._handle)
        assert server._job == 555

    def test_start_job_assign_failure_is_graceful(self, tmp_path):
        """Assign failure → job closed, _job stays None, server still started."""
        server = LlamaServer()
        fake_proc = MagicMock()
        fake_proc._handle = 4321
        fake_proc.poll.return_value = None
        with self._patch_settings(tmp_path), \
             patch("app.adapters.binary.llama_server.subprocess.Popen",
                   return_value=fake_proc), \
             patch.object(LlamaServer, "_wait_ready"), \
             patch("app.adapters.binary._proc_lifetime.create_kill_on_close_job",
                   return_value=555), \
             patch("app.adapters.binary._proc_lifetime.assign_process_to_job",
                   return_value=False), \
             patch("app.adapters.binary._proc_lifetime.close_job") as cj:
            server.start(model_path=tmp_path / "m.gguf", n_ctx=4096, n_gpu_layers=99)
        cj.assert_called_once_with(555)
        assert server._job is None
        assert server._process is fake_proc  # still started

    def test_start_job_create_failure_is_graceful(self, tmp_path):
        server = LlamaServer()
        fake_proc = MagicMock()
        fake_proc._handle = 4321
        fake_proc.poll.return_value = None
        with self._patch_settings(tmp_path), \
             patch("app.adapters.binary.llama_server.subprocess.Popen",
                   return_value=fake_proc), \
             patch.object(LlamaServer, "_wait_ready"), \
             patch("app.adapters.binary._proc_lifetime.create_kill_on_close_job",
                   return_value=None):
            server.start(model_path=tmp_path / "m.gguf", n_ctx=4096, n_gpu_layers=99)
        assert server._job is None
        assert server._process is fake_proc

    def test_start_with_live_process_stops_old_and_closes_old_job_first(self, tmp_path):
        """AC#2: a live prior server is real-stopped AND its job closed before
        the new Popen — verified via the real stop() path, not a stubbed stop."""
        server = LlamaServer()
        old_proc = MagicMock()
        old_proc.poll.return_value = 0  # confirmed dead so real stop() clears state
        server._process = old_proc
        server._port = 18080
        server._job = 999
        new_proc = MagicMock()
        new_proc._handle = 4321
        new_proc.poll.return_value = None
        order = MagicMock()  # parent recorder to assert call ordering
        with self._patch_settings(tmp_path), \
             patch("app.adapters.binary.llama_server.subprocess.Popen",
                   return_value=new_proc) as popen, \
             patch.object(LlamaServer, "_wait_ready"), \
             patch("app.adapters.binary._proc_lifetime.close_job") as cj, \
             patch("app.adapters.binary._proc_lifetime.create_kill_on_close_job",
                   return_value=None):
            order.attach_mock(cj, "close_job")
            order.attach_mock(popen, "popen")
            server.start(model_path=tmp_path / "m.gguf", n_ctx=4096, n_gpu_layers=99)
        old_proc.terminate.assert_called_once()        # old server really stopped
        cj.assert_called_once_with(999)                # old job closed
        # ordering: old job closed strictly before the new child was spawned
        names = [c[0] for c in order.mock_calls]
        assert names.index("close_job") < names.index("popen")
        assert server._process is new_proc
        assert server._job is None                     # create returned None here
