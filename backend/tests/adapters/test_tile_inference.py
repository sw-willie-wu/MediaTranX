"""Unit tests for extracted tile_inference helper."""
import pytest
import torch

from app.adapters.ai.tile_inference import tile_inference_run


def _identity_scale_model(scale: int):
    """Fake super-resolution model: nearest-neighbor upsample by `scale`."""
    def forward(x: torch.Tensor) -> torch.Tensor:
        return torch.nn.functional.interpolate(x, scale_factor=scale, mode="nearest")
    return forward


def test_single_tile_covers_whole_image():
    """When tile_size >= image edge, one tile covers everything."""
    img = torch.rand(1, 3, 32, 32)
    model = _identity_scale_model(scale=2)

    out = tile_inference_run(model, img, scale=2, tile_size=64, tile_pad=4)

    assert out.shape == (1, 3, 64, 64)


def test_multi_tile_stitching_produces_correct_shape():
    """128x128 input with tile_size=64 → 2x2 grid, stitched output is 256x256 at scale=2."""
    img = torch.arange(1 * 3 * 128 * 128, dtype=torch.float32).reshape(1, 3, 128, 128)
    model = _identity_scale_model(scale=2)

    out = tile_inference_run(model, img, scale=2, tile_size=64, tile_pad=8)

    assert out.shape == (1, 3, 256, 256)


def test_progress_callback_fires_per_tile():
    """128x128 with tile_size=64 → 4 tiles → 4 callbacks in monotonic order."""
    img = torch.rand(1, 3, 128, 128)
    model = _identity_scale_model(scale=2)
    calls = []

    def on_progress(p: float, msg: str):
        calls.append((p, msg))

    tile_inference_run(model, img, scale=2, tile_size=64, tile_pad=8,
                       on_progress=on_progress)

    assert len(calls) == 4
    progresses = [c[0] for c in calls]
    assert progresses == sorted(progresses)
    assert calls[-1][0] == pytest.approx(1.0)
    assert calls[-1][1] == "task.progress.tile_inference|4|4"


def test_actual_scale_detection_from_first_tile():
    """When model produces scale != requested, output shape follows actual scale."""
    img = torch.rand(1, 3, 64, 64)
    model = _identity_scale_model(scale=4)  # actual is 4 even though we "request" 2

    out = tile_inference_run(model, img, scale=2, tile_size=64, tile_pad=0)

    assert out.shape == (1, 3, 64 * 4, 64 * 4)
