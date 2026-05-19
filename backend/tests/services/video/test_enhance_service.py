"""Tests for VideoEnhanceService — FramePipe streaming + direct-output write."""
from __future__ import annotations
import re
from fractions import Fraction
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
from PIL import Image

from tests.conftest import make_file_service_mock
from app.adapters.binary.ffmpeg import MediaInfo
from app.services.video.enhance_service import (
    EnhanceService,
    TASK_TYPE_VIDEO_ENHANCE,
)

PROGRESS_KEY = re.compile(r"^task\.progress\.[a-z_]+(\|.+)*$")


def _make_media_info(duration=2.0, width=640, height=480, fps=30.0):
    return MediaInfo(
        duration=duration, width=width, height=height,
        fps=fps, fps_fraction=Fraction(int(fps), 1),
        video_codec="h264", audio_codec="aac",
        bitrate=1000, file_size=1024,
    )


class _FakeFramePipe:
    """Stand-in for FramePipe that yields N fake frames."""
    instances = []

    def __init__(self, frame_count=3, **kwargs):
        self.frame_count = frame_count
        self.kwargs = kwargs
        self.opened = False
        self.closed = False
        self.write_frame = MagicMock()
        _FakeFramePipe.instances.append(self)

    def open(self):
        self.opened = True

    def close(self):
        self.closed = True

    def read_frames(self):
        for _ in range(self.frame_count):
            yield np.zeros((480, 640, 3), dtype=np.uint8)


def _make_pipe_factory(frame_count=3):
    """Returns a callable suitable for `patch(...)` whose calls record kwargs."""
    def _factory(*args, **kwargs):
        return _FakeFramePipe(frame_count=frame_count, **kwargs)
    return _factory


FAKE_REGISTRY = {"PTH": {"realesrgan": {"variants": {
    "x4plus": {"scale": 4},
    "x2plus": {"scale": 2},
}}}}


class TestInit:
    def test_registers_handler_with_history_policy(self, tmp_path):
        fs = make_file_service_mock(tmp_path, use_create_output_path=False)
        tm = MagicMock()
        EnhanceService(file_service=fs, task_manager=tm,
                       ffmpeg=MagicMock(), realesrgan=MagicMock())
        args, kwargs = tm.register_handler.call_args
        assert args[0] == TASK_TYPE_VIDEO_ENHANCE
        assert kwargs.get("output_policy") == "history"


class TestSubmit:
    async def test_submit_forwards_params(self, tmp_path):
        fs = make_file_service_mock(tmp_path, use_create_output_path=False)
        tm = MagicMock()

        async def _async_submit(*a, **k):
            return "tid"
        tm.submit.side_effect = lambda *a, **k: _async_submit(*a, **k)

        svc = EnhanceService(file_service=fs, task_manager=tm,
                             ffmpeg=MagicMock(), realesrgan=MagicMock())
        tid = await svc.submit(file_id="fid", model="realesrgan", variant="x2plus",
                               output_format="mp4", video_codec="h264")
        assert tid == "tid"
        args, _ = tm.submit.call_args
        assert args[0] == TASK_TYPE_VIDEO_ENHANCE
        assert args[1]["variant"] == "x2plus"


class TestExecute:
    def _build(self, tmp_path, frame_count=3):
        _FakeFramePipe.instances.clear()
        fs = make_file_service_mock(tmp_path, use_create_output_path=False)
        ffmpeg = MagicMock()
        ffmpeg.ffmpeg_path = "/fake/ffmpeg"
        ffmpeg.get_media_info_sync = MagicMock(return_value=_make_media_info())
        realesrgan = MagicMock()
        realesrgan.enhance.return_value = Image.new("RGB", (1280, 960))
        svc = EnhanceService(file_service=fs, task_manager=MagicMock(),
                             ffmpeg=ffmpeg, realesrgan=realesrgan)
        Path(fs.require_file("f").file_path).write_bytes(b"v")
        return svc, ffmpeg, realesrgan, fs

    def test_unknown_variant_raises(self, tmp_path):
        svc, ffmpeg, realesrgan, fs = self._build(tmp_path)
        with patch("app.adapters.ai.registry.MODELS_REGISTRY", FAKE_REGISTRY), \
             patch("app.utils.video_frames.FramePipe", _make_pipe_factory(3)):
            with pytest.raises(ValueError, match="Unknown variant"):
                svc._execute(
                    {"file_id": "f", "model": "realesrgan", "variant": "bogus",
                     "output_format": "mp4", "video_codec": "h264"},
                    lambda p, m: None,
                )

    def test_framepipe_used_and_frames_iterated(self, tmp_path):
        svc, ffmpeg, realesrgan, fs = self._build(tmp_path, frame_count=3)
        with patch("app.adapters.ai.registry.MODELS_REGISTRY", FAKE_REGISTRY), \
             patch("app.utils.video_frames.FramePipe", _make_pipe_factory(3)):
            result = svc._execute(
                {"file_id": "f", "model": "realesrgan", "variant": "x2plus",
                 "output_format": "mp4", "video_codec": "h264"},
                lambda p, m: None,
            )
        assert realesrgan.enhance.call_count == 3
        assert result["frame_count"] == 3
        assert result["scale"] == 2
        # FramePipe was opened and closed
        assert _FakeFramePipe.instances[0].opened
        assert _FakeFramePipe.instances[0].closed

    def test_output_written_to_output_dir_not_create_output_path(self, tmp_path):
        svc, ffmpeg, realesrgan, fs = self._build(tmp_path, frame_count=1)
        with patch("app.adapters.ai.registry.MODELS_REGISTRY", FAKE_REGISTRY), \
             patch("app.utils.video_frames.FramePipe", _make_pipe_factory(1)):
            svc._execute(
                {"file_id": "f", "model": "realesrgan", "variant": "x4plus",
                 "output_format": "mp4", "video_codec": "h264"},
                lambda p, m: None,
            )
        # Confirms create_output_path bypass + direct register_output
        fs.create_output_path.assert_not_called()
        fs.register_output.assert_called_once()

    def test_progress_clamped_to_below_one_during_frame_loop(self, tmp_path):
        svc, ffmpeg, realesrgan, fs = self._build(tmp_path, frame_count=2)
        progress = []
        with patch("app.adapters.ai.registry.MODELS_REGISTRY", FAKE_REGISTRY), \
             patch("app.utils.video_frames.FramePipe", _make_pipe_factory(2)):
            svc._execute(
                {"file_id": "f", "model": "realesrgan", "variant": "x2plus",
                 "output_format": "mp4", "video_codec": "h264"},
                lambda p, m: progress.append((p, m)),
            )
        # During frame loop progress is clamped to 0.95 (line 116 in production);
        # final emission at end is 1.0
        loop_progress = [p for p, _ in progress[:-1]]
        for p in loop_progress:
            assert p <= 0.95 + 1e-9, f"unclamped during loop: {p}"
        assert progress[-1][0] == 1.0

    def test_progress_callback_emits_i18n_keys(self, tmp_path):
        svc, ffmpeg, realesrgan, fs = self._build(tmp_path, frame_count=1)
        progress = []
        with patch("app.adapters.ai.registry.MODELS_REGISTRY", FAKE_REGISTRY), \
             patch("app.utils.video_frames.FramePipe", _make_pipe_factory(1)):
            svc._execute(
                {"file_id": "f", "model": "realesrgan", "variant": "x4plus",
                 "output_format": "mp4", "video_codec": "h264"},
                lambda p, m: progress.append((p, m)),
            )
        for _, msg in progress:
            assert PROGRESS_KEY.match(msg), f"non-i18n message: {msg}"
