"""Tests for torch-free ONNX EP selection + Vulkan presence probe in adapters.device."""
from unittest.mock import patch

from app.adapters import device


def test_select_onnx_providers_prefers_dml_then_cpu():
    with patch.object(device, "available_onnx_providers",
                      return_value=["DmlExecutionProvider", "CPUExecutionProvider"]):
        assert device.select_onnx_providers() == ["DmlExecutionProvider", "CPUExecutionProvider"]


def test_select_onnx_providers_falls_back_to_cpu_only():
    with patch.object(device, "available_onnx_providers", return_value=["CPUExecutionProvider"]):
        assert device.select_onnx_providers() == ["CPUExecutionProvider"]


def test_select_onnx_providers_coreml_on_mac():
    with patch.object(device, "available_onnx_providers",
                      return_value=["CoreMLExecutionProvider", "CPUExecutionProvider"]):
        assert device.select_onnx_providers()[0] == "CoreMLExecutionProvider"


def test_select_onnx_providers_prefer_override_moves_ep_to_front():
    with patch.object(device, "available_onnx_providers",
                      return_value=["DmlExecutionProvider", "CUDAExecutionProvider",
                                    "CPUExecutionProvider"]):
        assert device.select_onnx_providers(prefer="CUDAExecutionProvider")[0] == \
            "CUDAExecutionProvider"


def test_select_onnx_providers_prefer_ignored_when_unavailable():
    with patch.object(device, "available_onnx_providers",
                      return_value=["DmlExecutionProvider", "CPUExecutionProvider"]):
        assert device.select_onnx_providers(prefer="CUDAExecutionProvider")[0] == \
            "DmlExecutionProvider"


def test_is_gpu_provider():
    assert device.is_gpu_provider("DmlExecutionProvider")
    assert device.is_gpu_provider("CoreMLExecutionProvider")
    assert device.is_gpu_provider("CUDAExecutionProvider")
    assert not device.is_gpu_provider("CPUExecutionProvider")


def test_preferred_gpu_provider_picks_first_gpu_ep():
    with patch.object(device, "available_onnx_providers",
                      return_value=["DmlExecutionProvider", "CPUExecutionProvider"]):
        assert device.preferred_gpu_provider() == "DmlExecutionProvider"


def test_preferred_gpu_provider_none_when_cpu_only():
    with patch.object(device, "available_onnx_providers", return_value=["CPUExecutionProvider"]):
        assert device.preferred_gpu_provider() is None


def test_has_vulkan_true_when_loader_present():
    device.has_vulkan.cache_clear()
    with patch("ctypes.CDLL") as cdll:
        cdll.return_value = object()
        assert device.has_vulkan() is True
    device.has_vulkan.cache_clear()


def test_has_vulkan_false_when_loader_missing():
    device.has_vulkan.cache_clear()
    with patch("ctypes.CDLL", side_effect=OSError("not found")):
        assert device.has_vulkan() is False
    device.has_vulkan.cache_clear()


def test_refresh_device_cache_clears_new_caches():
    device.available_onnx_providers()          # populate
    assert device.available_onnx_providers.cache_info().currsize == 1
    device.refresh_device_cache()
    assert device.available_onnx_providers.cache_info().currsize == 0
