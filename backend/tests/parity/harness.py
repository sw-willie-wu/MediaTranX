"""Parity assertions reused by every model-migration phase.

Image models: SSIM + PSNR (uint8 only — asserted) vs a checked-in
torch-reference output. GPU gate (NFR2): a wrapper that MUST run on GPU but
fell back to CPU skips with a loud reason rather than silently 'passing' on
CPU in CI. Audio parity helpers (word-ts deviation, SDR) land with the first
audio phase that needs them.
"""
from __future__ import annotations

from typing import Optional

import numpy as np
import pytest


def psnr(a: np.ndarray, b: np.ndarray) -> float:
    a = a.astype(np.float64); b = b.astype(np.float64)
    mse = np.mean((a - b) ** 2)
    if mse == 0:
        return float("inf")
    return 20.0 * np.log10(255.0) - 10.0 * np.log10(mse)


def ssim(a: np.ndarray, b: np.ndarray) -> float:
    """Global single-window SSIM (luma). Sufficient for parity (inputs are the
    same image through two runtimes), avoids a skimage dependency."""
    a = a.astype(np.float64).mean(axis=-1) if a.ndim == 3 else a.astype(np.float64)
    b = b.astype(np.float64).mean(axis=-1) if b.ndim == 3 else b.astype(np.float64)
    mu_a, mu_b = a.mean(), b.mean()
    va, vb = a.var(), b.var()
    cov = ((a - mu_a) * (b - mu_b)).mean()
    c1, c2 = (0.01 * 255) ** 2, (0.03 * 255) ** 2
    return ((2 * mu_a * mu_b + c1) * (2 * cov + c2)) / ((mu_a**2 + mu_b**2 + c1) * (va + vb + c2))


def assert_image_parity(out: np.ndarray, ref: np.ndarray, *, min_ssim: float, min_psnr: float) -> None:
    assert out.dtype == np.uint8 and ref.dtype == np.uint8, (
        f"parity metrics assume uint8 [0,255]; got {out.dtype}/{ref.dtype} — "
        f"convert the model output with the SAME postprocess as the reference"
    )
    assert out.shape == ref.shape, f"shape {out.shape} != ref {ref.shape}"
    s, p = ssim(out, ref), psnr(out, ref)
    assert s >= min_ssim, f"SSIM {s:.4f} < {min_ssim}"
    assert p >= min_psnr, f"PSNR {p:.2f}dB < {min_psnr}"


def assert_gpu_or_skip(ran_on_gpu: bool, name: str, *,
                       gpu_available: Optional[bool] = None) -> None:
    """NFR2: in a GPU-capable env the model must run on GPU; on CPU-only CI, skip.

    Availability defaults to the ORT GPU-EP probe (in-process ONNX models).
    Vulkan/Metal sidecar phases pass gpu_available=has_vulkan() (or their own
    probe) instead — the gate itself is runtime-agnostic.
    """
    if gpu_available is None:
        from app.adapters.device import preferred_gpu_provider
        gpu_available = preferred_gpu_provider() is not None
    if not gpu_available:
        pytest.skip(f"{name}: no GPU on this host (CPU-only) — GPU gate not asserted")
    assert ran_on_gpu, f"{name}: GPU available but model fell back to CPU (NFR2 violation)"
