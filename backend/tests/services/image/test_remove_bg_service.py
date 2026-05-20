"""Tests for ImageRemoveBgService."""
from __future__ import annotations
import os
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

from tests.conftest import make_file_service_mock, make_model_manager_mock
from app.services.image.remove_bg_service import (
    ImageRemoveBgService,
    TASK_TYPE_IMAGE_REMOVE_BG,
    _MODE_TO_MODEL,
)

PROGRESS_KEY = re.compile(r"^task\.progress\.[a-z_]+(\|.+)*$")


def _save_rgb(fs, size=(32, 32)):
    img_path = Path(fs.require_file("f").file_path)
    Image.new("RGB", size, (100, 100, 100)).save(img_path)
    return img_path


class TestInit:
    def test_registers_handler_with_history_policy(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        tm = MagicMock()
        ImageRemoveBgService(file_service=fs, task_manager=tm,
                             model_manager=make_model_manager_mock())
        args, kwargs = tm.register_handler.call_args
        assert args[0] == TASK_TYPE_IMAGE_REMOVE_BG
        assert kwargs.get("output_policy") == "history"


class TestSubmit:
    async def test_submit_forwards_mode(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        tm = MagicMock()

        async def _async_submit(*a, **k):
            return "tid"
        tm.submit.side_effect = lambda *a, **k: _async_submit(*a, **k)

        svc = ImageRemoveBgService(file_service=fs, task_manager=tm,
                                    model_manager=make_model_manager_mock())
        tid = await svc.submit_remove_bg(file_id="fid", mode="anime")
        assert tid == "tid"
        args, _ = tm.submit.call_args
        assert args[0] == TASK_TYPE_IMAGE_REMOVE_BG
        assert args[1]["mode"] == "anime"


class TestMode2Model:
    """The module-level _MODE_TO_MODEL dict is API surface."""

    def test_all_5_modes_mapped(self):
        assert set(_MODE_TO_MODEL.keys()) == {"auto", "person", "product", "animal", "anime"}

    def test_anime_mode_uses_isnet_anime(self):
        assert _MODE_TO_MODEL["anime"] == "isnet-anime"

    def test_person_mode_uses_human_seg(self):
        assert "human" in _MODE_TO_MODEL["person"]


class TestExecute:
    def _build(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        mm = make_model_manager_mock()
        svc = ImageRemoveBgService(file_service=fs, task_manager=MagicMock(),
                                    model_manager=mm)
        return svc, fs, mm

    @pytest.mark.parametrize("mode,expected_model", [
        ("auto", "u2net"),
        ("person", "u2net_human_seg"),
        ("product", "isnet-general-use"),
        ("animal", "u2net"),
        ("anime", "isnet-anime"),
    ])
    def test_mode_to_model_dispatch(self, tmp_path, mode, expected_model):
        svc, fs, _ = self._build(tmp_path)
        _save_rgb(fs)
        with patch("app.services.image.remove_bg_service.new_session") as mns, \
             patch("app.services.image.remove_bg_service.remove",
                   side_effect=lambda img, session: img.convert("RGBA")):
            svc._execute({"file_id": "f", "mode": mode}, lambda p, m: None)
            mns.assert_called_once_with(expected_model)

    def test_unknown_mode_falls_back_to_u2net(self, tmp_path):
        svc, fs, _ = self._build(tmp_path)
        _save_rgb(fs)
        with patch("app.services.image.remove_bg_service.new_session") as mns, \
             patch("app.services.image.remove_bg_service.remove",
                   side_effect=lambda img, session: img.convert("RGBA")):
            svc._execute({"file_id": "f", "mode": "bogus"}, lambda p, m: None)
            mns.assert_called_once_with("u2net")

    def test_u2net_home_env_var_set(self, tmp_path, monkeypatch):
        svc, fs, _ = self._build(tmp_path)
        _save_rgb(fs)
        monkeypatch.delenv("U2NET_HOME", raising=False)
        with patch("app.services.image.remove_bg_service.new_session"), \
             patch("app.services.image.remove_bg_service.remove",
                   side_effect=lambda img, session: img.convert("RGBA")):
            svc._execute({"file_id": "f", "mode": "auto"}, lambda p, m: None)
        assert "U2NET_HOME" in os.environ
        assert "rembg" in os.environ["U2NET_HOME"]

    def test_gpu_session_entered(self, tmp_path):
        svc, fs, mm = self._build(tmp_path)
        _save_rgb(fs)
        with patch("app.services.image.remove_bg_service.new_session"), \
             patch("app.services.image.remove_bg_service.remove",
                   side_effect=lambda img, session: img.convert("RGBA")):
            svc._execute({"file_id": "f", "mode": "auto"}, lambda p, m: None)
        mm.gpu_session.assert_called_once()

    def test_progress_callback_emits_i18n_keys(self, tmp_path):
        svc, fs, _ = self._build(tmp_path)
        _save_rgb(fs)
        progress = []
        with patch("app.services.image.remove_bg_service.new_session"), \
             patch("app.services.image.remove_bg_service.remove",
                   side_effect=lambda img, session: img.convert("RGBA")):
            svc._execute({"file_id": "f", "mode": "auto"},
                         lambda p, m: progress.append((p, m)))
        for _, msg in progress:
            assert PROGRESS_KEY.match(msg), f"non-i18n message: {msg}"

    def test_result_has_output_file_id(self, tmp_path):
        svc, fs, _ = self._build(tmp_path)
        _save_rgb(fs)
        with patch("app.services.image.remove_bg_service.new_session"), \
             patch("app.services.image.remove_bg_service.remove",
                   side_effect=lambda img, session: img.convert("RGBA")):
            result = svc._execute({"file_id": "f", "mode": "auto"}, lambda p, m: None)
        assert "output_file_id" in result
