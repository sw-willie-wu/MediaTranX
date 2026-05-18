"""Unit tests for FacePipeline (mocked facexlib helper)."""
import numpy as np
import pytest
from unittest.mock import MagicMock, patch
from PIL import Image

from app.adapters.ai.face_pipeline import FacePipeline


def _make_image(size=(256, 256), color=(128, 128, 128)) -> Image.Image:
    return Image.new("RGB", size, color)


def test_no_face_returns_input_unchanged():
    """When detector returns 0 faces, FacePipeline returns original PIL image."""
    pipeline = FacePipeline(device="cpu")
    img = _make_image()

    fake_helper = MagicMock()
    fake_helper.get_face_landmarks_5.return_value = 0  # zero faces detected
    fake_helper.cropped_faces = []
    pipeline._helper = fake_helper  # bypass lazy init

    restore_fn = MagicMock()
    result = pipeline.restore(img, restore_fn, face_upscale=2)

    assert isinstance(result, Image.Image)
    assert result.size == img.size
    restore_fn.assert_not_called()


def test_single_face_restored_and_pasted_back():
    """One detected face → restore_fn called once → paste_faces_to_input_image yields composite."""
    import torch
    pipeline = FacePipeline(device="cpu")
    img = _make_image((512, 512))

    # Fake 512x512 face crop as ndarray (HWC uint8)
    fake_face = np.full((512, 512, 3), 200, dtype=np.uint8)

    fake_helper = MagicMock()
    fake_helper.get_face_landmarks_5.return_value = 1
    fake_helper.cropped_faces = [fake_face]
    composited = np.full((1024, 1024, 3), 50, dtype=np.uint8)  # 2x upscaled
    fake_helper.paste_faces_to_input_image.return_value = composited
    pipeline._helper = fake_helper

    # restore_fn receives a tensor, returns a tensor
    def restore_fn(face_tensor: torch.Tensor) -> torch.Tensor:
        # Verify shape: NCHW, 1x3x512x512, float [0,1]
        assert face_tensor.shape == (1, 3, 512, 512)
        assert face_tensor.dtype == torch.float32
        return face_tensor  # identity for test

    result = pipeline.restore(img, restore_fn, face_upscale=2)
    assert isinstance(result, Image.Image)
    fake_helper.add_restored_face.assert_called_once()
    fake_helper.paste_faces_to_input_image.assert_called_once()


def test_helper_is_lazy_initialised():
    """First restore() call triggers _ensure_helper; subsequent calls reuse it."""
    pipeline = FacePipeline(device="cpu")
    assert pipeline._helper is None

    with patch("app.adapters.ai.face_pipeline.FaceRestoreHelper") as mock_helper_cls:
        instance = MagicMock()
        instance.get_face_landmarks_5.return_value = 0
        instance.cropped_faces = []
        mock_helper_cls.return_value = instance

        pipeline.restore(_make_image(), MagicMock(), face_upscale=2)
        pipeline.restore(_make_image(), MagicMock(), face_upscale=2)

    # Helper constructed only once
    assert mock_helper_cls.call_count == 1


def test_clean_all_called_between_invocations():
    """FaceRestoreHelper.clean_all() must run between restore() calls to reset state."""
    pipeline = FacePipeline(device="cpu")

    fake_helper = MagicMock()
    fake_helper.get_face_landmarks_5.return_value = 0
    fake_helper.cropped_faces = []
    pipeline._helper = fake_helper

    pipeline.restore(_make_image(), MagicMock(), face_upscale=2)
    pipeline.restore(_make_image(), MagicMock(), face_upscale=2)

    assert fake_helper.clean_all.call_count == 2
