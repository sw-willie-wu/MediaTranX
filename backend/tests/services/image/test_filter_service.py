"""Tests for ImageFilterService — covers 11 effect branches + preview."""
from __future__ import annotations
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from PIL import Image

from tests.conftest import make_file_service_mock
from app.services.image.filter_service import (
    ImageFilterService,
    TASK_TYPE_IMAGE_FILTER,
)

PROGRESS_KEY = re.compile(r"^task\.progress\.[a-z_]+(\|.+)*$")


NEUTRAL_PARAMS = {
    "brightness": 1.0, "contrast": 1.0, "saturation": 1.0, "hue": 0.0,
    "sharpness": 1.0, "warmth": 0.0, "grayscale": 0.0, "sepia": 0.0,
    "invert": 0.0, "blur": 0.0, "vignette": 0.0,
}


def _save_rgb(fs, size=(32, 32), color=(128, 128, 128)):
    img_path = Path(fs.require_file("f").file_path)
    Image.new("RGB", size, color).save(img_path)
    return img_path


class TestInit:
    def test_registers_handler_with_history_policy(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        tm = MagicMock()
        ImageFilterService(file_service=fs, task_manager=tm)
        args, kwargs = tm.register_handler.call_args
        assert args[0] == TASK_TYPE_IMAGE_FILTER
        assert kwargs.get("output_policy") == "history"


class TestSubmit:
    async def test_submit_forwards_all_effect_params(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        tm = MagicMock()

        async def _async_submit(*a, **k):
            return "tid"
        tm.submit.side_effect = lambda *a, **k: _async_submit(*a, **k)

        svc = ImageFilterService(file_service=fs, task_manager=tm)
        tid = await svc.submit_filter(
            file_id="fid", brightness=1.5, contrast=1.5, saturation=0.5,
            hue=45.0, sharpness=2.0, warmth=0.3, grayscale=0.5,
            sepia=0.7, invert=0.8, blur=3.0, vignette=0.6,
        )
        assert tid == "tid"
        args, _ = tm.submit.call_args
        assert args[0] == TASK_TYPE_IMAGE_FILTER
        assert args[1]["brightness"] == 1.5
        assert args[1]["hue"] == 45.0
        assert args[1]["vignette"] == 0.6


class TestApplyEffectBranches:
    """Cover each of the 11 effect branches by toggling one at a time."""

    @pytest.mark.parametrize("effect_kwargs", [
        {"brightness": 1.5},
        {"contrast": 1.5},
        {"saturation": 1.5},
        {"hue": 45.0},
        {"sharpness": 2.0},
        {"warmth": 0.5},
        {"warmth": -0.5},
        {"grayscale": 1.0},
        {"grayscale": 0.5},  # partial blend branch
        {"sepia": 0.8},
        {"invert": 1.0},
        {"blur": 3.0},
        {"vignette": 0.7},
    ])
    def test_each_effect_executes_without_error(self, tmp_path, effect_kwargs):
        fs = make_file_service_mock(tmp_path)
        svc = ImageFilterService(file_service=fs, task_manager=MagicMock())
        _save_rgb(fs)
        params = {"file_id": "f", **NEUTRAL_PARAMS, **effect_kwargs}
        result = svc._execute(params, lambda p, m: None)
        assert "output_file_id" in result


class TestExecute:
    def test_progress_callback_emits_i18n_keys(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        svc = ImageFilterService(file_service=fs, task_manager=MagicMock())
        _save_rgb(fs)
        progress = []
        svc._execute(
            {"file_id": "f", **NEUTRAL_PARAMS, "brightness": 1.2},
            lambda p, m: progress.append((p, m)),
        )
        for _, msg in progress:
            assert PROGRESS_KEY.match(msg), f"non-i18n message: {msg}"
        assert progress[-1][0] == 1.0


class TestGeneratePreview:
    """generate_preview(self, file_id, params: dict, max_size=900) — positional dict.
    LRU cache is on _load_preview_thumb(file_path: str, max_size: int)."""

    def test_returns_base64_data_uri(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        svc = ImageFilterService(file_service=fs, task_manager=MagicMock())
        _save_rgb(fs)
        preview = svc.generate_preview("f", {**NEUTRAL_PARAMS, "brightness": 1.2})
        assert isinstance(preview, str)
        assert preview.startswith("data:image/")

    def test_same_args_returns_same_preview(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        svc = ImageFilterService(file_service=fs, task_manager=MagicMock())
        _save_rgb(fs)
        a = svc.generate_preview("f", dict(NEUTRAL_PARAMS))
        b = svc.generate_preview("f", dict(NEUTRAL_PARAMS))
        assert a == b

    def test_alpha_image_returns_png(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        svc = ImageFilterService(file_service=fs, task_manager=MagicMock())
        img_path = Path(fs.require_file("f").file_path)
        Image.new("RGBA", (32, 32), (200, 200, 200, 128)).save(img_path)
        preview = svc.generate_preview("f", dict(NEUTRAL_PARAMS))
        assert preview.startswith("data:image/png")

    def test_rgb_image_returns_jpeg(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        svc = ImageFilterService(file_service=fs, task_manager=MagicMock())
        _save_rgb(fs)
        preview = svc.generate_preview("f", dict(NEUTRAL_PARAMS))
        assert preview.startswith("data:image/jpeg")
