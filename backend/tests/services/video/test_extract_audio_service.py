"""Tests for VideoExtractAudioService."""
from __future__ import annotations
import re
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from tests.conftest import make_file_service_mock
from app.adapters.binary.ffmpeg import FFmpegError
from app.services.video.extract_audio_service import (
    VideoExtractAudioService,
    TASK_TYPE_VIDEO_EXTRACT_AUDIO,
)

PROGRESS_KEY = re.compile(r"^task\.progress\.[a-z_]+(\|.+)*$")


def _ensure_input(fs):
    Path(fs.require_file("f").file_path).write_bytes(b"v")


class TestInit:
    def test_registers_handler_with_results_policy(self, tmp_path):
        ffmpeg = MagicMock()
        fs = make_file_service_mock(tmp_path)
        tm = MagicMock()
        VideoExtractAudioService(ffmpeg=ffmpeg, file_service=fs, task_manager=tm)
        args, kwargs = tm.register_handler.call_args
        assert args[0] == TASK_TYPE_VIDEO_EXTRACT_AUDIO
        assert kwargs.get("output_policy") == "results"


class TestSubmit:
    async def test_submit_forwards_format_and_bitrate(self, tmp_path):
        ffmpeg = MagicMock()
        fs = make_file_service_mock(tmp_path)
        tm = MagicMock()

        async def _async_submit(*a, **k):
            return "tid"
        tm.submit.side_effect = lambda *a, **k: _async_submit(*a, **k)

        svc = VideoExtractAudioService(ffmpeg=ffmpeg, file_service=fs, task_manager=tm)
        tid = await svc.submit_extract_audio(file_id="fid", audio_format="wav", audio_bitrate="320k")
        assert tid == "tid"
        args, _ = tm.submit.call_args
        assert args[0] == TASK_TYPE_VIDEO_EXTRACT_AUDIO
        assert args[1]["audio_format"] == "wav"
        assert args[1]["audio_bitrate"] == "320k"


class TestExecute:
    def _build(self, tmp_path):
        ffmpeg = MagicMock()
        fs = make_file_service_mock(tmp_path)
        tm = MagicMock()
        svc = VideoExtractAudioService(ffmpeg=ffmpeg, file_service=fs, task_manager=tm)
        return svc, ffmpeg, fs

    def test_calls_extract_audio_sync_with_correct_args(self, tmp_path):
        svc, ffmpeg, fs = self._build(tmp_path)
        _ensure_input(fs)
        result = svc._execute(
            {"file_id": "f", "audio_format": "mp3", "audio_bitrate": "192k"},
            lambda p, m: None,
        )
        ffmpeg.extract_audio_sync.assert_called_once()
        kwargs = ffmpeg.extract_audio_sync.call_args.kwargs
        assert kwargs["audio_format"] == "mp3"
        assert kwargs["audio_bitrate"] == "192k"
        assert "output_file_id" in result

    def test_progress_callback_emits_i18n_keys(self, tmp_path):
        svc, ffmpeg, fs = self._build(tmp_path)
        _ensure_input(fs)
        progress = []
        svc._execute(
            {"file_id": "f", "audio_format": "mp3"},
            lambda p, m: progress.append((p, m)),
        )
        for _, msg in progress:
            assert PROGRESS_KEY.match(msg), f"non-i18n message: {msg}"
        assert progress[-1][0] == 1.0

    def test_extract_audio_error_propagates(self, tmp_path):
        svc, ffmpeg, fs = self._build(tmp_path)
        ffmpeg.extract_audio_sync.side_effect = FFmpegError("no audio stream")
        _ensure_input(fs)
        with pytest.raises(FFmpegError):
            svc._execute(
                {"file_id": "f", "audio_format": "mp3", "audio_bitrate": "192k"},
                lambda p, m: None,
            )
