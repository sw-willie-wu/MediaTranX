"""Tests for the shared parity harness itself (SSIM/PSNR math + GPU gate)."""
import numpy as np
import pytest

from tests.parity.harness import psnr, ssim, assert_image_parity, assert_gpu_or_skip


def test_psnr_identical_is_inf():
    a = np.zeros((8, 8, 3), dtype=np.uint8)
    assert psnr(a, a) == float("inf")


def test_ssim_identical_is_one():
    a = (np.random.RandomState(0).rand(16, 16, 3) * 255).astype(np.uint8)
    assert ssim(a, a) == pytest.approx(1.0, abs=1e-6)


def test_assert_image_parity_passes_on_identical():
    a = (np.random.RandomState(1).rand(16, 16, 3) * 255).astype(np.uint8)
    assert_image_parity(a, a, min_ssim=0.99, min_psnr=40.0)


def test_assert_image_parity_fails_on_garbage():
    a = np.zeros((16, 16, 3), dtype=np.uint8)
    b = (np.random.RandomState(2).rand(16, 16, 3) * 255).astype(np.uint8)
    with pytest.raises(AssertionError):
        assert_image_parity(a, b, min_ssim=0.99, min_psnr=40.0)


def test_assert_image_parity_rejects_float_arrays():
    # The 255-peak metrics assume uint8; a float [0,1] image must fail LOUDLY
    # instead of passing vacuously (PSNR would inflate by ~48 dB).
    a = np.random.RandomState(3).rand(16, 16, 3).astype(np.float32)
    with pytest.raises(AssertionError, match="uint8"):
        assert_image_parity(a, a, min_ssim=0.99, min_psnr=40.0)


# `assert_gpu_or_skip` imports `preferred_gpu_provider` INSIDE the function from
# app.adapters.device, so monkeypatch the SOURCE module attribute. These
# tests are hermetic (do not depend on the host having/lacking a GPU EP).
def test_assert_gpu_or_skip_skips_when_no_gpu_ep(monkeypatch):
    monkeypatch.setattr("app.adapters.device.preferred_gpu_provider", lambda: None)
    with pytest.raises(pytest.skip.Exception):
        assert_gpu_or_skip(ran_on_gpu=False, name="x")


def test_assert_gpu_or_skip_fails_when_gpu_available_but_cpu_ran(monkeypatch):
    monkeypatch.setattr("app.adapters.device.preferred_gpu_provider",
                        lambda: "DmlExecutionProvider")
    with pytest.raises(AssertionError):
        assert_gpu_or_skip(ran_on_gpu=False, name="x")


def test_assert_gpu_or_skip_passes_when_gpu_available_and_gpu_ran(monkeypatch):
    monkeypatch.setattr("app.adapters.device.preferred_gpu_provider",
                        lambda: "DmlExecutionProvider")
    assert_gpu_or_skip(ran_on_gpu=True, name="x")  # must not raise


def test_assert_gpu_or_skip_explicit_availability_bypasses_ort_probe():
    # Vulkan-sidecar phases pass gpu_available=has_vulkan(): no ORT probe runs.
    with pytest.raises(AssertionError):
        assert_gpu_or_skip(ran_on_gpu=False, name="x", gpu_available=True)
    with pytest.raises(pytest.skip.Exception):
        assert_gpu_or_skip(ran_on_gpu=False, name="x", gpu_available=False)
