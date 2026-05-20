"""Tests for VideoCutService."""
from __future__ import annotations
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tests.conftest import make_file_service_mock
from app.services.video.cut_service import VideoCutService, TASK_TYPE_VIDEO_CUT

PROGRESS_KEY = re.compile(r"^task\.progress\.[a-z_]+(\|.+)*$")


def _ensure_input(fs, content: bytes = b"video bytes"):
    """Ensure the file_path returned by fs.require_file actually exists on disk."""
    Path(fs.require_file("f").file_path).write_bytes(content)


class TestInit:
    def test_registers_handler_with_correct_task_type(self, tmp_path):
        ffmpeg = MagicMock()
        fs = make_file_service_mock(tmp_path)
        tm = MagicMock()
        VideoCutService(ffmpeg=ffmpeg, file_service=fs, task_manager=tm)
        tm.register_handler.assert_called_once()
        args, kwargs = tm.register_handler.call_args
        assert args[0] == TASK_TYPE_VIDEO_CUT
        assert kwargs.get("output_policy") == "history"


class TestSubmit:
    async def test_submit_returns_task_id_and_forwards_params(self, tmp_path):
        ffmpeg = MagicMock()
        fs = make_file_service_mock(tmp_path)
        tm = MagicMock()

        async def _async_submit(*a, **k):
            return "tid"
        tm.submit.side_effect = lambda *a, **k: _async_submit(*a, **k)

        svc = VideoCutService(ffmpeg=ffmpeg, file_service=fs, task_manager=tm)
        tid = await svc.submit_cut(file_id="fid", start_time=1.0, end_time=2.0, stream_copy=True)
        assert tid == "tid"
        tm.submit.assert_called_once()
        args, _ = tm.submit.call_args
        assert args[0] == TASK_TYPE_VIDEO_CUT
        assert args[1]["file_id"] == "fid"
        assert args[1]["start_time"] == 1.0
        assert args[1]["end_time"] == 2.0
        assert args[1]["stream_copy"] is True


class TestExecute:
    def _build(self, tmp_path):
        ffmpeg = MagicMock()
        fs = make_file_service_mock(tmp_path)
        tm = MagicMock()
        svc = VideoCutService(ffmpeg=ffmpeg, file_service=fs, task_manager=tm)
        return svc, ffmpeg, fs

    def test_calls_ffmpeg_cut_sync_with_correct_args(self, tmp_path):
        svc, ffmpeg, fs = self._build(tmp_path)
        _ensure_input(fs)
        result = svc._execute(
            {"file_id": "f", "start_time": 1.0, "end_time": 2.0, "stream_copy": True},
            lambda p, m: None,
        )
        ffmpeg.cut_sync.assert_called_once()
        kwargs = ffmpeg.cut_sync.call_args.kwargs
        assert kwargs["start_time"] == 1.0
        assert kwargs["end_time"] == 2.0
        assert kwargs["stream_copy"] is True
        assert "output_file_id" in result

    def test_progress_callback_emits_i18n_keys(self, tmp_path):
        svc, ffmpeg, fs = self._build(tmp_path)
        _ensure_input(fs)
        progress = []
        svc._execute(
            {"file_id": "f", "start_time": 0.0, "end_time": 1.0, "stream_copy": False},
            lambda p, m: progress.append((p, m)),
        )
        messages = [m for _, m in progress]
        assert messages, "expected at least one progress emission"
        for msg in messages:
            assert PROGRESS_KEY.match(msg), f"non-i18n message: {msg}"
        # Final emission is complete (1.0)
        assert progress[-1][0] == 1.0

    def test_ffmpeg_error_propagates(self, tmp_path):
        svc, ffmpeg, fs = self._build(tmp_path)
        ffmpeg.cut_sync.side_effect = RuntimeError("ffmpeg failed")
        _ensure_input(fs)
        with pytest.raises(RuntimeError, match="ffmpeg failed"):
            svc._execute(
                {"file_id": "f", "start_time": 0.0, "end_time": 1.0, "stream_copy": True},
                lambda p, m: None,
            )
