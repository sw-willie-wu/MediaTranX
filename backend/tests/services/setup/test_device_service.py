"""Tests for DeviceService — thin wrapper over adapters.device."""
from __future__ import annotations
from unittest.mock import patch

from app.services.setup.device_service import DeviceService


def test_get_device_info_delegates():
    fake_info = {"cuda_available": True, "gpu_name": "Test GPU"}
    with patch("app.adapters.device.get_device_info", return_value=fake_info):
        svc = DeviceService()
        result = svc.get_device_info()
    assert result == fake_info


def test_refresh_cache_delegates():
    with patch("app.adapters.device.refresh_device_cache") as mock_refresh:
        DeviceService().refresh_cache()
    mock_refresh.assert_called_once()


def test_get_device_delegates():
    with patch("app.adapters.device.get_device", return_value="cuda"):
        assert DeviceService().get_device() == "cuda"


def test_get_compute_type_delegates():
    with patch("app.adapters.device.get_compute_type", return_value="float16"):
        assert DeviceService().get_compute_type() == "float16"


def test_select_torch_index_delegates():
    with patch("app.adapters.device.select_torch_index", return_value="cu128"):
        assert DeviceService().select_torch_index() == "cu128"
