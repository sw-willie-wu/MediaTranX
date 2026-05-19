"""Tests for ImageConvertService."""
from __future__ import annotations
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from tests.conftest import make_file_service_mock
from app.services.image.convert_service import (
    ImageConvertService,
    TASK_TYPE_IMAGE_CONVERT,
)

PROGRESS_KEY = re.compile(r"^task\.progress\.[a-z_]+(\|.+)*$")


class TestInit:
    def test_registers_handler_with_history_policy(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        tm = MagicMock()
        ImageConvertService(file_service=fs, task_manager=tm)
        args, kwargs = tm.register_handler.call_args
        assert args[0] == TASK_TYPE_IMAGE_CONVERT
        assert kwargs.get("output_policy") == "history"


class TestSubmit:
    async def test_submit_forwards_params(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        tm = MagicMock()

        async def _async_submit(*a, **k):
            return "tid"
        tm.submit.side_effect = lambda *a, **k: _async_submit(*a, **k)

        svc = ImageConvertService(file_service=fs, task_manager=tm)
        tid = await svc.submit_convert(
            file_id="fid", output_format="webp", quality=90,
            width=200, height=None, scale=None,
        )
        assert tid == "tid"
        args, _ = tm.submit.call_args
        assert args[0] == TASK_TYPE_IMAGE_CONVERT
        assert args[1]["output_format"] == "webp"
        assert args[1]["quality"] == 90
        assert args[1]["width"] == 200


class TestExecute:
    def _build(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        svc = ImageConvertService(file_service=fs, task_manager=MagicMock())
        return svc, fs

    def _save_rgba(self, fs):
        img_path = Path(fs.require_file("f").file_path)
        Image.new("RGBA", (64, 64), (255, 0, 0, 128)).save(img_path)
        return img_path

    def _save_static_rgb(self, fs):
        img_path = Path(fs.require_file("f").file_path)
        Image.new("RGB", (64, 64), (0, 0, 255)).save(img_path)
        return img_path

    def test_static_png_to_jpeg_converts_rgba_to_rgb(self, tmp_path):
        svc, fs = self._build(tmp_path)
        self._save_rgba(fs)
        result = svc._execute(
            {"file_id": "f", "output_format": "jpeg", "quality": 90,
             "width": None, "height": None, "scale": None},
            lambda p, m: None,
        )
        assert "output_file_id" in result
        # Output file should exist on disk
        out_path = fs.output_dir / "input_converted.jpg"
        assert out_path.exists()

    def test_resize_with_scale(self, tmp_path):
        svc, fs = self._build(tmp_path)
        self._save_static_rgb(fs)
        result = svc._execute(
            {"file_id": "f", "output_format": "png", "quality": 90,
             "width": None, "height": None, "scale": 0.5},
            lambda p, m: None,
        )
        out_path = fs.output_dir / "input_converted.png"
        assert out_path.exists()
        with Image.open(out_path) as out:
            assert out.size == (32, 32)

    def test_resize_width_only_preserves_aspect(self, tmp_path):
        svc, fs = self._build(tmp_path)
        self._save_static_rgb(fs)  # 64x64
        svc._execute(
            {"file_id": "f", "output_format": "png", "quality": 90,
             "width": 32, "height": None, "scale": None},
            lambda p, m: None,
        )
        out_path = fs.output_dir / "input_converted.png"
        with Image.open(out_path) as out:
            assert out.size == (32, 32)

    def test_animated_gif_uses_apply_and_save(self, tmp_path):
        svc, fs = self._build(tmp_path)
        img_path = Path(fs.require_file("f").file_path)
        # Two-frame animated GIF
        Image.new("RGB", (32, 32), (255, 0, 0)).save(
            img_path, format="GIF", save_all=True,
            append_images=[Image.new("RGB", (32, 32), (0, 255, 0))],
            duration=100, loop=0,
        )
        with patch("app.utils.gif_utils.apply_and_save") as mock_apply:
            mock_apply.return_value = None
            svc._execute(
                {"file_id": "f", "output_format": "gif", "quality": 90,
                 "width": None, "height": None, "scale": None},
                lambda p, m: None,
            )
            mock_apply.assert_called_once()

    def test_progress_callback_emits_i18n_keys(self, tmp_path):
        svc, fs = self._build(tmp_path)
        self._save_static_rgb(fs)
        progress = []
        svc._execute(
            {"file_id": "f", "output_format": "png", "quality": 90,
             "width": None, "height": None, "scale": None},
            lambda p, m: progress.append((p, m)),
        )
        for _, msg in progress:
            assert PROGRESS_KEY.match(msg), f"non-i18n message: {msg}"
        assert progress[-1][0] == 1.0


class TestQueryMethods:
    async def test_get_image_info_returns_dict(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        img_path = Path(fs.require_file("f").file_path)
        Image.new("RGB", (100, 50), (0, 0, 0)).save(img_path)
        svc = ImageConvertService(file_service=fs, task_manager=MagicMock())
        info = await svc.get_image_info("f")
        assert info["width"] == 100
        assert info["height"] == 50
        assert info["format"] in {"PNG", "APNG"}
        assert info["mode"] == "RGB"
