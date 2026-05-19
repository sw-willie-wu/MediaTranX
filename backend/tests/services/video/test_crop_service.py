"""Tests for VideoCropService."""
from __future__ import annotations
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tests.conftest import make_file_service_mock
from app.services.video.crop_service import VideoCropService, TASK_TYPE_VIDEO_CROP

PROGRESS_KEY = re.compile(r"^task\.progress\.[a-z_]+(\|.+)*$")


def _ensure_input(fs):
    Path(fs.require_file("f").file_path).write_bytes(b"v")


class TestInit:
    def test_registers_handler_with_history_output_policy(self, tmp_path):
        ffmpeg = MagicMock()
        fs = make_file_service_mock(tmp_path)
        tm = MagicMock()
        VideoCropService(ffmpeg=ffmpeg, file_service=fs, task_manager=tm)
        args, kwargs = tm.register_handler.call_args
        assert args[0] == TASK_TYPE_VIDEO_CROP
        assert kwargs.get("output_policy") == "history"


class TestSubmit:
    async def test_submit_forwards_box_and_returns_task_id(self, tmp_path):
        ffmpeg = MagicMock()
        fs = make_file_service_mock(tmp_path)
        tm = MagicMock()

        async def _async_submit(*a, **k):
            return "tid"
        tm.submit.side_effect = lambda *a, **k: _async_submit(*a, **k)

        svc = VideoCropService(ffmpeg=ffmpeg, file_service=fs, task_manager=tm)
        tid = await svc.submit_crop(file_id="fid", x=10, y=20, width=100, height=200)
        assert tid == "tid"
        args, _ = tm.submit.call_args
        assert args[0] == TASK_TYPE_VIDEO_CROP
        assert args[1]["x"] == 10
        assert args[1]["y"] == 20
        assert args[1]["width"] == 100
        assert args[1]["height"] == 200


class TestExecute:
    def _build(self, tmp_path):
        ffmpeg = MagicMock()
        fs = make_file_service_mock(tmp_path)
        tm = MagicMock()
        svc = VideoCropService(ffmpeg=ffmpeg, file_service=fs, task_manager=tm)
        return svc, ffmpeg, fs

    def test_even_alignment_subtracts_odd_remainder(self, tmp_path):
        svc, ffmpeg, fs = self._build(tmp_path)
        _ensure_input(fs)
        result = svc._execute(
            {"file_id": "f", "x": 0, "y": 0, "width": 101, "height": 99},
            lambda p, m: None,
        )
        kwargs = ffmpeg.crop_sync.call_args.kwargs
        assert kwargs["width"] == 100
        assert kwargs["height"] == 98
        assert result["crop_width"] == 100
        assert result["crop_height"] == 98

    def test_zero_dimension_after_alignment_raises_value_error(self, tmp_path):
        svc, ffmpeg, fs = self._build(tmp_path)
        _ensure_input(fs)
        with pytest.raises(ValueError, match="Invalid crop size"):
            svc._execute(
                {"file_id": "f", "x": 0, "y": 0, "width": 1, "height": 1},
                lambda p, m: None,
            )

    def test_returns_crop_metadata(self, tmp_path):
        svc, ffmpeg, fs = self._build(tmp_path)
        _ensure_input(fs)
        result = svc._execute(
            {"file_id": "f", "x": 10, "y": 20, "width": 100, "height": 100},
            lambda p, m: None,
        )
        assert result["crop_x"] == 10
        assert result["crop_y"] == 20
        assert result["crop_width"] == 100
        assert result["crop_height"] == 100
        assert "output_file_id" in result

    def test_progress_callback_emits_i18n_keys(self, tmp_path):
        svc, ffmpeg, fs = self._build(tmp_path)
        _ensure_input(fs)
        progress = []
        svc._execute(
            {"file_id": "f", "x": 0, "y": 0, "width": 100, "height": 100},
            lambda p, m: progress.append((p, m)),
        )
        messages = [m for _, m in progress]
        assert messages
        for msg in messages:
            assert PROGRESS_KEY.match(msg), f"non-i18n message: {msg}"
