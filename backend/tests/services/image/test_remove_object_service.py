"""Tests for ImageRemoveObjectService — LaMa + OpenCV fallback + alpha preserve."""
from __future__ import annotations
import base64
import io
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import torch
from PIL import Image

from tests.conftest import make_file_service_mock, make_model_manager_mock
from app.services.image.remove_object_service import (
    ImageRemoveObjectService,
    TASK_TYPE_IMAGE_REMOVE_OBJECT,
)

PROGRESS_KEY = re.compile(r"^task\.progress\.[a-z_]+(\|.+)*$")


def _make_mask_b64(w=32, h=32):
    """Generate a base64-encoded PNG mask with a white center square."""
    mask = Image.new("L", (w, h), 0)
    for y in range(h // 4, 3 * h // 4):
        for x in range(w // 4, 3 * w // 4):
            mask.putpixel((x, y), 255)
    buf = io.BytesIO()
    mask.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode("ascii")


def _build(tmp_path):
    fs = make_file_service_mock(tmp_path)
    mm = make_model_manager_mock()
    svc = ImageRemoveObjectService(
        file_service=fs, task_manager=MagicMock(),
        model_manager=mm, mobilesam=MagicMock(),
    )
    img_path = Path(fs.require_file("f").file_path)
    Image.new("RGB", (32, 32), (200, 200, 200)).save(img_path)
    return svc, fs


class TestInit:
    def test_registers_handler_with_history_policy(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        tm = MagicMock()
        ImageRemoveObjectService(file_service=fs, task_manager=tm,
                                  model_manager=make_model_manager_mock(),
                                  mobilesam=MagicMock())
        args, kwargs = tm.register_handler.call_args
        assert args[0] == TASK_TYPE_IMAGE_REMOVE_OBJECT
        assert kwargs.get("output_policy") == "history"


class TestSubmit:
    async def test_submit_forwards_mask(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        tm = MagicMock()

        async def _async_submit(*a, **k):
            return "tid"
        tm.submit.side_effect = lambda *a, **k: _async_submit(*a, **k)

        svc = ImageRemoveObjectService(file_service=fs, task_manager=tm,
                                        model_manager=make_model_manager_mock(),
                                        mobilesam=MagicMock())
        mask_b64 = _make_mask_b64()
        tid = await svc.submit_remove_object(file_id="fid", mask_data=mask_b64)
        assert tid == "tid"
        args, _ = tm.submit.call_args
        assert args[0] == TASK_TYPE_IMAGE_REMOVE_OBJECT
        assert args[1]["mask_data"] == mask_b64


class TestExecute:
    def test_lama_path_succeeds(self, tmp_path):
        svc, fs = _build(tmp_path)
        mask_b64 = _make_mask_b64()

        # SimpleLama instance mock with .device and .model
        fake_lama_instance = MagicMock()
        fake_lama_instance.device = "cpu"
        fake_lama_instance.model = MagicMock(return_value=torch.zeros((1, 3, 32, 32)))

        with patch("simple_lama_inpainting.SimpleLama", return_value=fake_lama_instance), \
             patch("simple_lama_inpainting.utils.util.prepare_img_and_mask",
                   return_value=(torch.zeros((1, 3, 32, 32)), torch.zeros((1, 1, 32, 32)))):
            result = svc._execute(
                {"file_id": "f", "mask_data": mask_b64},
                lambda p, m: None,
            )
        assert "output_file_id" in result
        # LaMa model invoked
        fake_lama_instance.model.assert_called_once()

    def test_lama_failure_falls_back_to_opencv_inpaint(self, tmp_path):
        svc, fs = _build(tmp_path)
        mask_b64 = _make_mask_b64()

        with patch("simple_lama_inpainting.SimpleLama",
                   side_effect=RuntimeError("lama load failed")), \
             patch("app.services.image.remove_object_service.cv2.inpaint") as mock_cv_inpaint:
            # cv2.inpaint returns BGR numpy
            mock_cv_inpaint.return_value = np.zeros((32, 32, 3), dtype=np.uint8)
            result = svc._execute(
                {"file_id": "f", "mask_data": mask_b64},
                lambda p, m: None,
            )
        mock_cv_inpaint.assert_called_once()
        # cv2.inpaint(img_bgr, mask_cv, 10, cv2.INPAINT_TELEA) — args[3] is the constant
        import cv2 as _cv2
        args = mock_cv_inpaint.call_args.args
        assert args[3] == _cv2.INPAINT_TELEA
        assert "output_file_id" in result

    def test_alpha_preserved_for_rgba_input(self, tmp_path):
        svc, fs = _build(tmp_path)
        # Save RGBA image instead of RGB
        Image.new("RGBA", (32, 32), (200, 200, 200, 128)).save(
            Path(fs.require_file("f").file_path))
        mask_b64 = _make_mask_b64()

        fake_lama_instance = MagicMock()
        fake_lama_instance.device = "cpu"
        fake_lama_instance.model = MagicMock(return_value=torch.zeros((1, 3, 32, 32)))

        with patch("simple_lama_inpainting.SimpleLama", return_value=fake_lama_instance), \
             patch("simple_lama_inpainting.utils.util.prepare_img_and_mask",
                   return_value=(torch.zeros((1, 3, 32, 32)), torch.zeros((1, 1, 32, 32)))):
            result = svc._execute(
                {"file_id": "f", "mask_data": mask_b64},
                lambda p, m: None,
            )
        # Output exists; preserve_alpha wrapper exercised
        assert "output_file_id" in result
        # Output file is PNG with alpha channel
        out_path = fs.output_dir / "input_removed.png"
        assert out_path.exists()
        with Image.open(out_path) as out:
            assert out.mode == "RGBA"

    def test_empty_mask_returns_original_image_via_lama_path(self, tmp_path):
        """Mask with no white pixels: _run_inpaint returns image_pil unchanged at line 76."""
        svc, fs = _build(tmp_path)
        # Mask that's entirely black
        blank_mask = Image.new("L", (32, 32), 0)
        buf = io.BytesIO()
        blank_mask.save(buf, format="PNG")
        empty_b64 = base64.b64encode(buf.getvalue()).decode("ascii")

        fake_lama_instance = MagicMock()
        fake_lama_instance.device = "cpu"
        with patch("simple_lama_inpainting.SimpleLama", return_value=fake_lama_instance):
            result = svc._execute(
                {"file_id": "f", "mask_data": empty_b64},
                lambda p, m: None,
            )
        # LaMa model NOT invoked because we returned early
        fake_lama_instance.model.assert_not_called()
        assert "output_file_id" in result

    def test_data_uri_mask_prefix_stripped(self, tmp_path):
        """`data:image/png;base64,...` prefix gets split before decode."""
        svc, fs = _build(tmp_path)
        mask_b64 = _make_mask_b64()
        full_uri = f"data:image/png;base64,{mask_b64}"

        fake_lama_instance = MagicMock()
        fake_lama_instance.device = "cpu"
        fake_lama_instance.model = MagicMock(return_value=torch.zeros((1, 3, 32, 32)))

        with patch("simple_lama_inpainting.SimpleLama", return_value=fake_lama_instance), \
             patch("simple_lama_inpainting.utils.util.prepare_img_and_mask",
                   return_value=(torch.zeros((1, 3, 32, 32)), torch.zeros((1, 1, 32, 32)))):
            result = svc._execute(
                {"file_id": "f", "mask_data": full_uri},
                lambda p, m: None,
            )
        assert "output_file_id" in result

    def test_progress_callback_emits_i18n_keys(self, tmp_path):
        svc, fs = _build(tmp_path)
        mask_b64 = _make_mask_b64()

        fake_lama_instance = MagicMock()
        fake_lama_instance.device = "cpu"
        fake_lama_instance.model = MagicMock(return_value=torch.zeros((1, 3, 32, 32)))

        progress = []
        with patch("simple_lama_inpainting.SimpleLama", return_value=fake_lama_instance), \
             patch("simple_lama_inpainting.utils.util.prepare_img_and_mask",
                   return_value=(torch.zeros((1, 3, 32, 32)), torch.zeros((1, 1, 32, 32)))):
            svc._execute(
                {"file_id": "f", "mask_data": mask_b64},
                lambda p, m: progress.append((p, m)),
            )
        for _, msg in progress:
            assert PROGRESS_KEY.match(msg), f"non-i18n message: {msg}"

    def test_gpu_session_entered(self, tmp_path):
        svc, fs = _build(tmp_path)
        mask_b64 = _make_mask_b64()

        fake_lama_instance = MagicMock()
        fake_lama_instance.device = "cpu"
        fake_lama_instance.model = MagicMock(return_value=torch.zeros((1, 3, 32, 32)))

        with patch("simple_lama_inpainting.SimpleLama", return_value=fake_lama_instance), \
             patch("simple_lama_inpainting.utils.util.prepare_img_and_mask",
                   return_value=(torch.zeros((1, 3, 32, 32)), torch.zeros((1, 1, 32, 32)))):
            svc._execute(
                {"file_id": "f", "mask_data": mask_b64},
                lambda p, m: None,
            )
        svc._model_manager.gpu_session.assert_called_once()
