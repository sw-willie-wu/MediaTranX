"""Tests for adapters.device compute-type selection.

Regression coverage for the float16-on-old-GPU bug: CTranslate2 only supports
float16 on CUDA compute capability >= 7.0. Older NVIDIA GPUs (Pascal/Maxwell)
are detected as "cuda" but reject float16, so get_compute_type() must verify
what the backend actually supports instead of assuming float16.
"""
from __future__ import annotations
from unittest.mock import patch, MagicMock

from app.adapters import device


def _clear():
    device.get_compute_type.cache_clear()


def test_compute_type_cuda_with_float16_support():
    """Modern GPU (float16 supported) -> float16, unchanged behaviour."""
    _clear()
    with patch("app.adapters.device.get_device", return_value="cuda"), patch(
        "app.adapters.device._supported_compute_types",
        return_value={"float32", "int8", "int8_float16", "float16"},
    ):
        assert device.get_compute_type() == "float16"
    _clear()


def test_compute_type_cuda_without_float16_falls_back():
    """Old GPU detected as cuda but float16 unsupported -> must NOT return float16."""
    _clear()
    # Typical Pascal report: no float16, but int8 variants available.
    with patch("app.adapters.device.get_device", return_value="cuda"), patch(
        "app.adapters.device._supported_compute_types",
        return_value={"float32", "int8", "int8_float32"},
    ):
        result = device.get_compute_type()
    _clear()
    assert result != "float16"
    assert result in {"int8", "int8_float32", "float32"}


def test_compute_type_cpu_returns_int8():
    """CPU keeps int8 quantisation."""
    _clear()
    with patch("app.adapters.device.get_device", return_value="cpu"), patch(
        "app.adapters.device._supported_compute_types",
        return_value={"float32", "int8"},
    ):
        assert device.get_compute_type() == "int8"
    _clear()


def test_compute_type_cuda_unknown_support_preserves_float16():
    """If CTranslate2 can't report supported types, preserve legacy float16 on cuda."""
    _clear()
    with patch("app.adapters.device.get_device", return_value="cuda"), patch(
        "app.adapters.device._supported_compute_types", return_value=set()
    ):
        assert device.get_compute_type() == "float16"
    _clear()


# ── compute_type_for (uncached, device-explicit) ──────────────────────────


def test_compute_type_for_cuda_without_float16():
    with patch("app.adapters.device._supported_compute_types",
               return_value={"float32", "int8", "int8_float32"}):
        assert device.compute_type_for("cuda") != "float16"
        assert device.compute_type_for("cuda") in {"int8", "int8_float32", "float32"}


def test_compute_type_for_cpu():
    with patch("app.adapters.device._supported_compute_types",
               return_value={"float32", "int8"}):
        assert device.compute_type_for("cpu") == "int8"


def test_get_compute_type_delegates_to_for():
    _clear()
    with patch("app.adapters.device.get_device", return_value="cuda"), patch(
        "app.adapters.device.compute_type_for", return_value="int8") as m:
        assert device.get_compute_type() == "int8"
    _clear()
    m.assert_called_once_with("cuda")


# ── VRAM helpers ──────────────────────────────────────────────────────────


def test_get_free_vram_mb_via_nvidia_smi():
    fake = MagicMock(returncode=0, stdout="6144\n")
    with patch("subprocess.run", return_value=fake):
        assert device.get_free_vram_mb() == 6144


def test_get_free_vram_mb_none_when_all_fail():
    with patch("subprocess.run", side_effect=FileNotFoundError), patch(
        "app.adapters.device._free_vram_via_torch", return_value=None):
        assert device.get_free_vram_mb() is None


def test_fits_in_vram_unknown_returns_true():
    with patch("app.adapters.device.get_free_vram_mb", return_value=None):
        assert device.fits_in_vram(9999) is True


def test_fits_in_vram_insufficient_false():
    with patch("app.adapters.device.get_free_vram_mb", return_value=2048):
        assert device.fits_in_vram(2130, headroom_mb=512) is False


def test_fits_in_vram_sufficient_true():
    with patch("app.adapters.device.get_free_vram_mb", return_value=10000):
        assert device.fits_in_vram(2130) is True
