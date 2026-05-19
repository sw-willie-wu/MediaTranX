"""Tests for VideoInterpolateService — FPS modes + rife.interpolate_pipe."""
from __future__ import annotations
import re
from fractions import Fraction
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import make_file_service_mock
from app.adapters.binary.ffmpeg import MediaInfo
from app.services.video.interpolate_service import (
    InterpolateService,
    TASK_TYPE_VIDEO_INTERPOLATE,
)

PROGRESS_KEY = re.compile(r"^task\.progress\.[a-z_]+(\|.+)*$")


def _make_media_info(duration=2.0, width=640, height=480, fps=30.0):
    return MediaInfo(
        duration=duration, width=width, height=height,
        fps=fps, fps_fraction=Fraction(int(fps), 1),
        video_codec="h264", audio_codec="aac",
        bitrate=1000, file_size=1024,
    )


def _build(tmp_path):
    fs = make_file_service_mock(tmp_path, use_create_output_path=False)
    ffmpeg = MagicMock()
    ffmpeg.ffmpeg_path = "/fake/ffmpeg"
    ffmpeg.get_media_info_sync = MagicMock(return_value=_make_media_info())
    rife = MagicMock()
    rife.interpolate_pipe = MagicMock(return_value=(60, None))
    svc = InterpolateService(file_service=fs, task_manager=MagicMock(),
                             ffmpeg=ffmpeg, rife=rife)
    Path(fs.require_file("f").file_path).write_bytes(b"v")
    return svc, ffmpeg, rife, fs


class TestInit:
    def test_registers_handler_with_history_policy(self, tmp_path):
        fs = make_file_service_mock(tmp_path, use_create_output_path=False)
        tm = MagicMock()
        InterpolateService(file_service=fs, task_manager=tm,
                           ffmpeg=MagicMock(), rife=MagicMock())
        args, kwargs = tm.register_handler.call_args
        assert args[0] == TASK_TYPE_VIDEO_INTERPOLATE
        assert kwargs.get("output_policy") == "history"


class TestSubmit:
    async def test_submit_forwards_params(self, tmp_path):
        fs = make_file_service_mock(tmp_path, use_create_output_path=False)
        tm = MagicMock()

        async def _async_submit(*a, **k):
            return "tid"
        tm.submit.side_effect = lambda *a, **k: _async_submit(*a, **k)

        svc = InterpolateService(file_service=fs, task_manager=tm,
                                  ffmpeg=MagicMock(), rife=MagicMock())
        tid = await svc.submit(file_id="fid", model="v4.26", mode="4x",
                               target_fps=None, output_format="mp4",
                               video_codec="h264")
        assert tid == "tid"
        args, _ = tm.submit.call_args
        assert args[0] == TASK_TYPE_VIDEO_INTERPOLATE
        assert args[1]["mode"] == "4x"


class TestExecute:
    def test_2x_mode_uses_multiplier_2(self, tmp_path):
        svc, ffmpeg, rife, fs = _build(tmp_path)
        svc._execute(
            {"file_id": "f", "model": "v4.26", "mode": "2x",
             "target_fps": None, "output_format": "mp4", "video_codec": "h264"},
            lambda p, m: None,
        )
        kwargs = rife.interpolate_pipe.call_args.kwargs
        assert kwargs["multiplier"] == 2

    def test_4x_mode_uses_multiplier_4(self, tmp_path):
        svc, ffmpeg, rife, fs = _build(tmp_path)
        svc._execute(
            {"file_id": "f", "model": "v4.26", "mode": "4x",
             "target_fps": None, "output_format": "mp4", "video_codec": "h264"},
            lambda p, m: None,
        )
        kwargs = rife.interpolate_pipe.call_args.kwargs
        assert kwargs["multiplier"] == 4

    def test_custom_mode_invalid_fps_raises(self, tmp_path):
        svc, ffmpeg, rife, fs = _build(tmp_path)
        # source fps is 30; target_fps=24 is invalid
        with pytest.raises(ValueError, match="must be greater than source"):
            svc._execute(
                {"file_id": "f", "model": "v4.26", "mode": "custom",
                 "target_fps": 24.0, "output_format": "mp4", "video_codec": "h264"},
                lambda p, m: None,
            )

    @pytest.mark.parametrize("target_fps,expected_multiplier", [
        (60, 2),    # ratio 2 → 2
        (90, 4),    # ratio 3 → next pow2 is 4
        (120, 4),   # ratio 4 → 4
        (240, 8),   # ratio 8 → 8
    ])
    def test_custom_mode_computes_power_of_two_multiplier(self, tmp_path, target_fps, expected_multiplier):
        svc, ffmpeg, rife, fs = _build(tmp_path)
        svc._execute(
            {"file_id": "f", "model": "v4.26", "mode": "custom",
             "target_fps": float(target_fps), "output_format": "mp4",
             "video_codec": "h264"},
            lambda p, m: None,
        )
        kwargs = rife.interpolate_pipe.call_args.kwargs
        assert kwargs["multiplier"] == expected_multiplier

    def test_returns_frame_count_from_rife(self, tmp_path):
        svc, ffmpeg, rife, fs = _build(tmp_path)
        rife.interpolate_pipe.return_value = (120, None)
        result = svc._execute(
            {"file_id": "f", "model": "v4.26", "mode": "2x",
             "target_fps": None, "output_format": "mp4", "video_codec": "h264"},
            lambda p, m: None,
        )
        assert result["frame_count"] == 120
        assert result["source_fps"] == 30.0

    def test_output_bypasses_create_output_path(self, tmp_path):
        svc, ffmpeg, rife, fs = _build(tmp_path)
        svc._execute(
            {"file_id": "f", "model": "v4.26", "mode": "2x",
             "target_fps": None, "output_format": "mp4", "video_codec": "h264"},
            lambda p, m: None,
        )
        fs.create_output_path.assert_not_called()
        fs.register_output.assert_called_once()

    def test_progress_callback_emits_i18n_keys(self, tmp_path):
        svc, ffmpeg, rife, fs = _build(tmp_path)
        progress = []
        svc._execute(
            {"file_id": "f", "model": "v4.26", "mode": "2x",
             "target_fps": None, "output_format": "mp4", "video_codec": "h264"},
            lambda p, m: progress.append((p, m)),
        )
        for _, msg in progress:
            assert PROGRESS_KEY.match(msg), f"non-i18n message: {msg}"
        assert progress[-1][0] == 1.0


class TestQueryMethods:
    def test_get_rife_status_returns_dict_with_variants(self, tmp_path):
        fs = make_file_service_mock(tmp_path, use_create_output_path=False)
        svc = InterpolateService(file_service=fs, task_manager=MagicMock(),
                                  ffmpeg=MagicMock(), rife=MagicMock())
        # MODELS_REGISTRY + SETTINGS are lazy-imported inside the method.
        # Don't mock — let it run against real registry.
        status = svc.get_rife_status()
        assert isinstance(status, dict)
        assert "variants" in status
        # variant entries shape
        for name, info in status["variants"].items():
            assert "downloaded" in info
            assert isinstance(info["downloaded"], bool)
