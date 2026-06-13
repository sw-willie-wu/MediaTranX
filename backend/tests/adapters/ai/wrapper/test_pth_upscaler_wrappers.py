"""Tests for 5 PthWrapper upscaler subclasses (bsrgan/real_cugan/realesrgan/swinir/waifu2x).

Shared shape: enhance(image, model_id, scale, on_progress) -> Image. Parametrized
to exercise: __init__ slot value, unknown-variant ValueError, default-arg validity,
mock-acquire path returning a fake image, acquire call args.
"""
from __future__ import annotations
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from app.adapters.ai.wrapper.bsrgan import BSRGANWrapper
from app.adapters.ai.wrapper.real_cugan import RealCUGANWrapper
from app.adapters.ai.wrapper.swinir import SwinIRWrapper


# realesrgan + waifu2x migrated to ncnn-vulkan wrappers in Phase 1 (T10/T11) and
# their torch wrappers were deleted; bsrgan/swinir/real-cugan stay on torch.
UPSCALERS = [
    pytest.param(BSRGANWrapper,     "bsrgan",     "default",           4, id="bsrgan"),
    pytest.param(RealCUGANWrapper,  "real-cugan", "up4x-conservative", 4, id="real_cugan"),
    pytest.param(SwinIRWrapper,     "swinir",     "realworld-x4",      4, id="swinir"),
]


@pytest.mark.parametrize("cls,family,default_variant,scale", UPSCALERS)
def test_init_slot_is_upscale(cls, family, default_variant, scale):
    """Bug-#3 regression: all upscaler wrappers register slot='upscale'."""
    w = cls()
    assert w.slot == "upscale", (
        f"{cls.__name__} slot must be 'upscale' to match container "
        f"register_dispatcher('upscale', ...); got {w.slot!r}"
    )


@pytest.mark.parametrize("cls,family,default_variant,scale", UPSCALERS)
def test_init_not_loaded(cls, family, default_variant, scale):
    w = cls()
    assert not w.is_loaded()


@pytest.mark.parametrize("cls,family,default_variant,scale", UPSCALERS)
def test_unknown_variant_raises_value_error(cls, family, default_variant, scale):
    w = cls()
    with pytest.raises(ValueError, match="(?i)variant"):
        w.enhance(Image.new("RGB", (32, 32)), model_id="bogus-variant", scale=scale)


@pytest.mark.parametrize("cls,family,default_variant,scale", UPSCALERS)
def test_default_model_id_is_valid_variant(cls, family, default_variant, scale):
    """Bug-#4 regression: default model_id resolves in registry without raising.

    Without wiring a ModelManager we expect either:
    - ValueError("Unknown ... variant") if default is broken (FAIL)
    - RuntimeError("not registered with ModelManager") since wrapper.acquire()
      hits the guard at base.py:86-90 (PASS — variant lookup succeeded).
    """
    w = cls()
    try:
        w.enhance(Image.new("RGB", (32, 32)))
    except ValueError as e:
        if "variant" in str(e).lower():
            pytest.fail(f"{cls.__name__} default model_id rejected: {e}")
        raise
    except RuntimeError as e:
        assert "ModelManager" in str(e) or "not registered" in str(e), str(e)


def _make_fake_output_tensor(scale: int):
    """Build a MagicMock that supports the chain output.squeeze(0).permute(1,2,0).cpu().numpy()."""
    fake = MagicMock()
    out_arr = np.zeros((scale * 32, scale * 32, 3), dtype=np.float32)
    (fake.squeeze.return_value
         .permute.return_value
         .cpu.return_value
         .numpy.return_value) = out_arr
    return fake


@pytest.mark.parametrize("cls,family,default_variant,scale", UPSCALERS)
def test_enhance_with_mocked_acquire_returns_image(cls, family, default_variant, scale):
    """Full enhance flow with mocked acquire + mocked model inference."""
    w = cls()

    @contextmanager
    def _acquire(model_id=None, variant=None, on_progress=None):
        w._model = MagicMock()
        w._device = "cpu"
        yield w

    fake_tensor = _make_fake_output_tensor(scale)
    with patch.object(w, "acquire", _acquire), \
         patch.object(w, "run_inference", return_value=fake_tensor):
        result = w.enhance(Image.new("RGB", (32, 32)), model_id=default_variant, scale=scale)
    assert isinstance(result, Image.Image)
    assert result.size == (scale * 32, scale * 32)


@pytest.mark.parametrize("cls,family,default_variant,scale", UPSCALERS)
def test_acquire_called_with_family_and_variant(cls, family, default_variant, scale):
    """Verify wrapper passes the right model_id (family name) + variant to acquire."""
    w = cls()
    capture = {}

    @contextmanager
    def _acquire(model_id=None, variant=None, on_progress=None):
        capture["model_id"] = model_id
        capture["variant"] = variant
        w._model = MagicMock()
        w._device = "cpu"
        yield w

    fake_tensor = _make_fake_output_tensor(scale)
    with patch.object(w, "acquire", _acquire), \
         patch.object(w, "run_inference", return_value=fake_tensor):
        w.enhance(Image.new("RGB", (32, 32)), model_id=default_variant, scale=scale)

    assert capture["model_id"] == family
    assert capture["variant"] == default_variant
