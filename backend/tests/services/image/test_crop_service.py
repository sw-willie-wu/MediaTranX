"""Tests for ImageCropService."""
from __future__ import annotations
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from tests.conftest import make_file_service_mock
from app.services.image.crop_service import (
    ImageCropService,
    TASK_TYPE_IMAGE_CROP,
)

PROGRESS_KEY = re.compile(r"^task\.progress\.[a-z_]+(\|.+)*$")


def _save_static_png(fs, size=(100, 100), color=(0, 0, 0)):
    img_path = Path(fs.require_file("f").file_path)
    Image.new("RGB", size, color).save(img_path)
    return img_path


class TestInit:
    def test_registers_handler_with_history_policy(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        tm = MagicMock()
        ImageCropService(file_service=fs, task_manager=tm)
        args, kwargs = tm.register_handler.call_args
        assert args[0] == TASK_TYPE_IMAGE_CROP
        assert kwargs.get("output_policy") == "history"


class TestSubmit:
    async def test_submit_forwards_box(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        tm = MagicMock()

        async def _async_submit(*a, **k):
            return "tid"
        tm.submit.side_effect = lambda *a, **k: _async_submit(*a, **k)

        svc = ImageCropService(file_service=fs, task_manager=tm)
        tid = await svc.submit_crop(file_id="fid", x=10, y=20, width=50, height=60)
        assert tid == "tid"
        args, _ = tm.submit.call_args
        assert args[0] == TASK_TYPE_IMAGE_CROP
        assert args[1]["x"] == 10
        assert args[1]["width"] == 50


class TestExecute:
    def _build(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        svc = ImageCropService(file_service=fs, task_manager=MagicMock())
        return svc, fs

    def test_static_image_crop_writes_output(self, tmp_path):
        svc, fs = self._build(tmp_path)
        _save_static_png(fs)
        result = svc._execute(
            {"file_id": "f", "x": 10, "y": 20, "width": 50, "height": 60},
            lambda p, m: None,
        )
        assert "output_file_id" in result
        assert result["crop_x"] == 10
        assert result["crop_y"] == 20
        assert result["crop_width"] == 50
        assert result["crop_height"] == 60
        assert result["source_width"] == 100
        assert result["source_height"] == 100

    def test_clamps_x_y_to_image_bounds(self, tmp_path):
        svc, fs = self._build(tmp_path)
        _save_static_png(fs, size=(100, 100))
        result = svc._execute(
            {"file_id": "f", "x": 500, "y": 500, "width": 200, "height": 200},
            lambda p, m: None,
        )
        # x/y clamped to img_width - 1 = 99
        assert result["crop_x"] == 99
        assert result["crop_y"] == 99
        # crop_width clamped to img_width - x = 1
        assert result["crop_width"] == 1
        assert result["crop_height"] == 1

    def test_clamps_width_height_to_image_bounds(self, tmp_path):
        svc, fs = self._build(tmp_path)
        _save_static_png(fs, size=(100, 100))
        result = svc._execute(
            {"file_id": "f", "x": 0, "y": 0, "width": 500, "height": 500},
            lambda p, m: None,
        )
        # crop sized clamped to (img_width - x) = 100
        assert result["crop_width"] == 100
        assert result["crop_height"] == 100

    def test_animated_path_delegates_to_apply_and_save(self, tmp_path):
        svc, fs = self._build(tmp_path)
        img_path = Path(fs.require_file("f").file_path)
        Image.new("RGB", (32, 32), (255, 0, 0)).save(
            img_path, format="GIF", save_all=True,
            append_images=[Image.new("RGB", (32, 32), (0, 255, 0))],
            duration=100, loop=0,
        )
        with patch("app.utils.gif_utils.apply_and_save") as mock_apply:
            svc._execute(
                {"file_id": "f", "x": 0, "y": 0, "width": 16, "height": 16},
                lambda p, m: None,
            )
            mock_apply.assert_called_once()

    def test_progress_callback_emits_i18n_keys(self, tmp_path):
        svc, fs = self._build(tmp_path)
        _save_static_png(fs)
        progress = []
        svc._execute(
            {"file_id": "f", "x": 0, "y": 0, "width": 50, "height": 50},
            lambda p, m: progress.append((p, m)),
        )
        for _, msg in progress:
            assert PROGRESS_KEY.match(msg), f"non-i18n message: {msg}"
        assert progress[-1][0] == 1.0
