"""
Tests for the startup system-info diagnostic log.

The block must be best-effort: it logs the tester's environment (OS, GPU,
compute capability, driver, torch CUDA build) once at startup so a bug report's
app.log is self-describing. Crucially it must NEVER raise — a missing AI env
(no torch) or any detection failure must degrade gracefully, not break startup.
"""
import logging

from app.init.system_info import log_system_info


class _Settings:
    is_frozen = False

    class path:
        root = "/tmp/mediatranx"


def test_log_system_info_does_not_raise_and_logs_block(caplog):
    with caplog.at_level(logging.INFO):
        log_system_info(_Settings())  # must not raise
    text = caplog.text
    assert "System Info" in text
    # stdlib-only fields are always present regardless of AI env / hardware
    assert "OS:" in text
    assert "Python:" in text


def test_log_system_info_survives_device_detection_failure(monkeypatch, caplog):
    """If device detection blows up, the block still logs and never raises."""
    import app.adapters.device as device

    def _boom():
        raise RuntimeError("simulated detection failure")

    monkeypatch.setattr(device, "get_device_info", _boom)
    with caplog.at_level(logging.INFO):
        log_system_info(_Settings())  # must still not raise
    text = caplog.text
    assert "System Info" in text
    assert "OS:" in text  # basics still logged even though device section failed


def test_log_system_info_survives_broken_settings(caplog):
    """A settings object missing attributes must not break logging."""
    with caplog.at_level(logging.INFO):
        log_system_info(object())  # no is_frozen / path -> must not raise
    assert "System Info" in caplog.text


def test_log_system_info_torch_absent_logs_not_available(monkeypatch, caplog):
    """Bare machine (no AI env / torch): log 'not available', never raise."""
    import app.adapters.device as device

    def _no_torch():
        # what get_device_info returns when torch can't be imported: torch_* None
        return {
            "device": "cpu", "compute_type": "float32", "device_name": "CPU",
            "compute_capability": None, "memory_total": None, "memory_free": None,
            "torch_version": None, "torch_cuda_build": None, "has_nvidia_gpu": False,
            "cuda_toolkit_installed": False, "driver_version": None,
            "ram_total": None, "ram_available": None,
            "os_name": "x", "os_version": "x", "cpu_name": "x", "cpu_count": 1,
        }

    monkeypatch.setattr(device, "get_device_info", _no_torch)
    with caplog.at_level(logging.INFO):
        log_system_info(_Settings())
    assert "Torch:    not available" in caplog.text
