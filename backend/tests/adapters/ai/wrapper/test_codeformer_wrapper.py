"""Tests for CodeFormerWrapper (PthWrapper face restorer)."""
from __future__ import annotations
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from app.adapters.ai.wrapper.codeformer import CodeFormerWrapper


def test_init_slot_is_face_restore():
    """Bug-#3 regression."""
    w = CodeFormerWrapper()
    assert w.slot == "face_restore"


def test_init_not_loaded():
    w = CodeFormerWrapper()
    assert not w.is_loaded()


def test_unknown_variant_raises():
    w = CodeFormerWrapper()
    with pytest.raises(ValueError, match="(?i)variant|model_id"):
        w.restore(Image.new("RGB", (64, 64)), model_id="bogus-codeformer-variant")


def test_restore_with_mocked_facepipeline_and_acquire():
    """KNOWN BUG (bug #5, deferred follow-up): `fidelity` is currently a no-op in
    CodeFormer — the model is called as `model(face_tensor)` without `w=fidelity`,
    and `face_upscale=2` is hardcoded (codeformer.py:76-83 IMPLEMENTER NOTE).
    Once production is fixed, change this test to assert fidelity is forwarded.
    For now, assert the FacePipeline.restore call happens with the expected kwargs.
    """
    w = CodeFormerWrapper()
    fake_output = Image.new("RGB", (256, 256), (100, 100, 100))

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
        result = w.restore(Image.new("RGB", (64, 64)), fidelity=0.6)

    assert result is fake_output
    fake_pipeline_instance.restore.assert_called_once()
    kwargs = fake_pipeline_instance.restore.call_args.kwargs
    # Confirm what IS forwarded today (face_upscale=2 hardcoded, on_progress wired)
    assert kwargs.get("face_upscale") == 2
    assert "on_progress" in kwargs


def test_face_pipeline_cached_across_calls():
    """_face_pipeline is lazy-init'd once, reused across restore() calls."""
    w = CodeFormerWrapper()

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
