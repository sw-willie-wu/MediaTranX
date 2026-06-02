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


# --- CUDA kernel smoke-test -> CPU fallback (K80-class: GPU detected but no
#     kernel image for its arch). All mocked; never touches a real GPU. ---

def _make_fake_torch(*, fail: bool = False, cuda_available: bool = True):
    """Fake torch where a kernel launch (`.item()`) succeeds or raises, and
    torch.cuda.is_available() is configurable (CPU-only build = False)."""
    import types as _types

    class _Tensor:
        def __add__(self, other):
            return self

        def item(self):
            if fail:
                raise RuntimeError(
                    "CUDA error: no kernel image is available for execution on the device"
                )
            return 1.0

    fake = _types.SimpleNamespace()
    fake.zeros = lambda *a, **k: _Tensor()
    fake.cuda = _types.SimpleNamespace(
        is_available=lambda: cuda_available,
        get_device_name=lambda i: "FakeGPU",
    )
    return fake


def test_cuda_can_run_kernels_true_when_launch_succeeds(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "torch", _make_fake_torch(fail=False))
    assert device._cuda_can_run_kernels() is True


def test_cuda_can_run_kernels_true_when_torch_is_cpu_only(monkeypatch):
    """CPU-only torch (CUDA may come from CTranslate2): must NOT veto the GPU."""
    import sys
    fake = _make_fake_torch(fail=True, cuda_available=False)  # would raise IF probed
    monkeypatch.setitem(sys.modules, "torch", fake)
    # is_available()==False short-circuits before the (failing) launch probe.
    assert device._cuda_can_run_kernels() is True


def test_cuda_can_run_kernels_false_and_logs_when_launch_fails(monkeypatch, caplog):
    import logging
    import sys
    monkeypatch.setitem(sys.modules, "torch", _make_fake_torch(fail=True))
    with caplog.at_level(logging.WARNING):
        assert device._cuda_can_run_kernels() is False
    assert "FakeGPU" in caplog.text and "CPU" in caplog.text


def test_get_device_falls_back_to_cpu_when_gpu_cannot_run_kernels():
    """GPU detected + runtime OK, but kernel launch fails -> must NOT return cuda."""
    device.get_device.cache_clear()
    with patch("app.adapters.device._detect_cuda_via_torch", return_value="cuda"), \
         patch("app.adapters.device._detect_cuda_via_ctranslate2", return_value=None), \
         patch("app.adapters.device.is_cuda_runtime_available", return_value=True), \
         patch("app.adapters.device._cuda_can_run_kernels", return_value=False), \
         patch("app.adapters.device.has_directml", return_value=False), \
         patch("app.adapters.device.has_nvidia_gpu", return_value=True):
        assert device.get_device() == "cpu"
    device.get_device.cache_clear()


def test_get_device_returns_cuda_when_gpu_can_run_kernels():
    """Healthy GPU (kernel launch OK) still returns cuda — no regression."""
    device.get_device.cache_clear()
    with patch("app.adapters.device._detect_cuda_via_torch", return_value="cuda"), \
         patch("app.adapters.device.is_cuda_runtime_available", return_value=True), \
         patch("app.adapters.device._cuda_can_run_kernels", return_value=True):
        assert device.get_device() == "cuda"
    device.get_device.cache_clear()
