"""Tests for MobileSAMWrapper (PackageWrapper for object segmentation)."""
from __future__ import annotations
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import numpy as np

from app.adapters.ai.wrapper.mobilesam import MobileSAMWrapper


def test_init_slot_is_mobilesam():
    """Bug-#3 regression: matches container register_runtime_provider('mobilesam', ...)."""
    w = MobileSAMWrapper()
    assert w.slot == "mobilesam"


def test_init_not_loaded():
    w = MobileSAMWrapper()
    assert not w.is_loaded()


def test_predict_box_returns_uint8_mask():
    """predict_box returns (H, W) uint8 numpy array with values in {0, 255}."""
    w = MobileSAMWrapper()
    fake_predictor = MagicMock()
    fake_predictor.predict.return_value = (
        np.ones((1, 32, 32), dtype=bool),  # mask: True = object
        np.array([0.95]),
        None,
    )

    @contextmanager
    def _acquire(model_id=None, variant=None, on_progress=None):
        w._model = MagicMock()  # SamPredictor wraps this
        yield w

    image_rgb = np.zeros((32, 32, 3), dtype=np.uint8)
    box = np.array([10, 10, 20, 20])

    with patch.object(w, "acquire", _acquire), \
         patch("mobile_sam.SamPredictor", return_value=fake_predictor):
        result = w.predict_box(image_rgb, box)

    assert isinstance(result, np.ndarray)
    assert result.dtype == np.uint8
    assert result.shape == (32, 32)
    assert set(np.unique(result).tolist()).issubset({0, 255})
    fake_predictor.set_image.assert_called_once_with(image_rgb)


def test_predict_box_with_empty_mask():
    """When SAM returns all-False mask, output is all zeros."""
    w = MobileSAMWrapper()
    fake_predictor = MagicMock()
    fake_predictor.predict.return_value = (
        np.zeros((1, 32, 32), dtype=bool),
        np.array([0.1]),
        None,
    )

    @contextmanager
    def _acquire(model_id=None, variant=None, on_progress=None):
        w._model = MagicMock()
        yield w

    image_rgb = np.zeros((32, 32, 3), dtype=np.uint8)
    box = np.array([0, 0, 32, 32])

    with patch.object(w, "acquire", _acquire), \
         patch("mobile_sam.SamPredictor", return_value=fake_predictor):
        result = w.predict_box(image_rgb, box)

    assert result.sum() == 0  # all zeros
