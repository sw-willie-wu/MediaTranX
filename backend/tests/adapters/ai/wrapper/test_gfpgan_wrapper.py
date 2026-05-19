"""Tests for GFPGANWrapper (PthWrapper face restorer)."""
from __future__ import annotations
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app.adapters.ai.wrapper.gfpgan import GFPGANWrapper


def test_init_slot_is_face_restore():
    """Bug-#3 regression."""
    w = GFPGANWrapper()
    assert w.slot == "face_restore"


def test_init_not_loaded():
    w = GFPGANWrapper()
    assert not w.is_loaded()


def test_unknown_variant_raises():
    w = GFPGANWrapper()
    with pytest.raises(ValueError, match="(?i)variant|model_id"):
        w.restore(Image.new("RGB", (64, 64)), model_id="bogus-gfpgan-variant")


def test_restore_forwards_upscale_to_facepipeline():
    """Unlike CodeFormer, GFPGAN does forward `upscale` correctly as `face_upscale=`."""
    w = GFPGANWrapper()
    fake_output = Image.new("RGB", (256, 256))

    @contextmanager
    def _acquire(model_id=None, variant=None, on_progress=None):
        w._model = MagicMock()
        w._device = "cpu"
        yield w

    fake_pipeline_instance = MagicMock()
    fake_pipeline_instance.restore.return_value = fake_output

    with patch.object(w, "acquire", _acquire), \
         patch("app.adapters.ai.face_pipeline.FacePipeline",
               return_value=fake_pipeline_instance):
        result = w.restore(Image.new("RGB", (64, 64)), upscale=3)

    assert result is fake_output
    kwargs = fake_pipeline_instance.restore.call_args.kwargs
    assert kwargs.get("face_upscale") == 3
    assert "on_progress" in kwargs


def test_face_pipeline_cached_across_calls():
    w = GFPGANWrapper()

    @contextmanager
    def _acquire(model_id=None, variant=None, on_progress=None):
        w._model = MagicMock()
        w._device = "cpu"
        yield w

    fake_pipeline_instance = MagicMock()
    fake_pipeline_instance.restore.return_value = Image.new("RGB", (256, 256))

    with patch.object(w, "acquire", _acquire), \
         patch("app.adapters.ai.face_pipeline.FacePipeline",
               return_value=fake_pipeline_instance) as FP:
        w.restore(Image.new("RGB", (64, 64)))
        w.restore(Image.new("RGB", (64, 64)))
    assert FP.call_count == 1
