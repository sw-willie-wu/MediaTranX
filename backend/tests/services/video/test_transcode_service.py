"""Tests for VideoTranscodeService."""
from __future__ import annotations
import re
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from tests.conftest import make_file_service_mock
from app.adapters.binary.ffmpeg import VideoCodec, AudioCodec, QualityPreset, MediaInfo
from app.services.video.transcode_service import (
    VideoTranscodeService,
    TASK_TYPE_VIDEO_TRANSCODE,
)

PROGRESS_KEY = re.compile(r"^task\.progress\.[a-z_]+(\|.+)*$")


def _ensure_input(fs):
    Path(fs.require_file("f").file_path).write_bytes(b"v")


BASE_PARAMS = {
    "file_id": "f",
    "output_format": "mp4",
    "video_codec": "h264",
    "audio_codec": "aac",
    "preset": "medium",
    "crf": 23,
    "resolution": "1080p",
    "scale_algorithm": "lanczos",
    "fps": 30,
    "audio_bitrate": "192k",
}


class TestInit:
    def test_registers_handler_with_history_policy(self, tmp_path):
        ffmpeg = MagicMock()
        fs = make_file_service_mock(tmp_path)
        tm = MagicMock()
        VideoTranscodeService(ffmpeg=ffmpeg, file_service=fs, task_manager=tm)
        args, kwargs = tm.register_handler.call_args
        assert args[0] == TASK_TYPE_VIDEO_TRANSCODE
        assert kwargs.get("output_policy") == "history"


class TestSubmit:
    async def test_submit_forwards_all_kwargs(self, tmp_path):
        ffmpeg = MagicMock()
        fs = make_file_service_mock(tmp_path)
        tm = MagicMock()

        async def _async_submit(*a, **k):
            return "tid"
        tm.submit.side_effect = lambda *a, **k: _async_submit(*a, **k)

        svc = VideoTranscodeService(ffmpeg=ffmpeg, file_service=fs, task_manager=tm)
        tid = await svc.submit_transcode(
            file_id="fid", output_format="webm", video_codec="vp9",
            audio_codec="opus", preset="fast", crf=28, resolution="720p",
            fps=60, audio_bitrate="128k",
        )
        assert tid == "tid"
        args, _ = tm.submit.call_args
        assert args[0] == TASK_TYPE_VIDEO_TRANSCODE
        assert args[1]["video_codec"] == "vp9"
        assert args[1]["preset"] == "fast"


class TestExecute:
    def _build(self, tmp_path):
        ffmpeg = MagicMock()
        fs = make_file_service_mock(tmp_path)
        tm = MagicMock()
        svc = VideoTranscodeService(ffmpeg=ffmpeg, file_service=fs, task_manager=tm)
        return svc, ffmpeg, fs

    @pytest.mark.parametrize("codec_str,enum_value", [
        ("h264", VideoCodec.H264),
        ("h265", VideoCodec.H265),
        ("vp9", VideoCodec.VP9),
        ("av1", VideoCodec.AV1),
        ("copy", VideoCodec.COPY),
    ])
    def test_video_codec_enum_mapping(self, tmp_path, codec_str, enum_value):
        svc, ffmpeg, fs = self._build(tmp_path)
        _ensure_input(fs)
        svc._execute({**BASE_PARAMS, "video_codec": codec_str}, lambda p, m: None)
        options = ffmpeg.transcode_sync.call_args.kwargs["options"]
        assert options.video_codec == enum_value

    @pytest.mark.parametrize("codec_str,enum_value", [
        ("aac", AudioCodec.AAC),
        ("mp3", AudioCodec.MP3),
        ("opus", AudioCodec.OPUS),
        ("flac", AudioCodec.FLAC),
        ("copy", AudioCodec.COPY),
    ])
    def test_audio_codec_enum_mapping(self, tmp_path, codec_str, enum_value):
        svc, ffmpeg, fs = self._build(tmp_path)
        _ensure_input(fs)
        svc._execute({**BASE_PARAMS, "audio_codec": codec_str}, lambda p, m: None)
        options = ffmpeg.transcode_sync.call_args.kwargs["options"]
        assert options.audio_codec == enum_value

    @pytest.mark.parametrize("preset_str,enum_value", [
        ("ultrafast", QualityPreset.ULTRAFAST),
        ("fast", QualityPreset.FAST),
        ("medium", QualityPreset.MEDIUM),
        ("slow", QualityPreset.SLOW),
        ("veryslow", QualityPreset.VERYSLOW),
    ])
    def test_preset_enum_mapping(self, tmp_path, preset_str, enum_value):
        svc, ffmpeg, fs = self._build(tmp_path)
        _ensure_input(fs)
        svc._execute({**BASE_PARAMS, "preset": preset_str}, lambda p, m: None)
        options = ffmpeg.transcode_sync.call_args.kwargs["options"]
        assert options.preset == enum_value

    def test_bogus_video_codec_silently_defaults_to_h264(self, tmp_path):
        """Production uses video_codec_map.get(value, VideoCodec.H264) — bogus values
        silently default; no exception. Intentional at transcode_service.py:182."""
        svc, ffmpeg, fs = self._build(tmp_path)
        _ensure_input(fs)
        svc._execute({**BASE_PARAMS, "video_codec": "bogus"}, lambda p, m: None)
        options = ffmpeg.transcode_sync.call_args.kwargs["options"]
        assert options.video_codec == VideoCodec.H264

    def test_progress_callback_emits_i18n_keys(self, tmp_path):
        svc, ffmpeg, fs = self._build(tmp_path)
        _ensure_input(fs)
        progress = []
        svc._execute(BASE_PARAMS, lambda p, m: progress.append((p, m)))
        for _, msg in progress:
            assert PROGRESS_KEY.match(msg), f"non-i18n message: {msg}"
        assert progress[-1][0] == 1.0

    def test_options_includes_resolution_fps_crf_audio_bitrate(self, tmp_path):
        svc, ffmpeg, fs = self._build(tmp_path)
        _ensure_input(fs)
        svc._execute(BASE_PARAMS, lambda p, m: None)
        options = ffmpeg.transcode_sync.call_args.kwargs["options"]
        assert options.crf == 23
        assert options.resolution == "1080p"
        assert options.fps == 30
        assert options.audio_bitrate == "192k"


class TestQueryMethods:
    async def test_get_media_info_returns_dict(self, tmp_path):
        ffmpeg = MagicMock()
        fs = make_file_service_mock(tmp_path)
        from fractions import Fraction
        media = MediaInfo(
            duration=10.0, width=1920, height=1080, fps=30.0,
            fps_fraction=Fraction(30, 1),
            video_codec="h264", audio_codec="aac",
            bitrate=5000, file_size=1024,
        )

        async def _get_info(_):
            return media
        ffmpeg.get_media_info = MagicMock(side_effect=_get_info)

        svc = VideoTranscodeService(ffmpeg=ffmpeg, file_service=fs, task_manager=MagicMock())
        result = await svc.get_media_info("f")
        assert isinstance(result, dict)
        assert result["duration"] == 10.0
        assert result["video_codec"] == "h264"

    def test_get_ffmpeg_status_patches_class_symbol(self, tmp_path):
        """DI violation: get_ffmpeg_status() does FFmpegWrapper() directly + classmethods.
        Patching self._ffmpeg won't intercept; must patch the class symbol in the
        service module namespace. Follow-up: refactor get_ffmpeg_status to use DI."""
        injected_ffmpeg = MagicMock()
        fs = make_file_service_mock(tmp_path)
        svc = VideoTranscodeService(ffmpeg=injected_ffmpeg, file_service=fs, task_manager=MagicMock())

        with patch("app.services.video.transcode_service.FFmpegWrapper") as MockFF:
            MockFF.is_installed.return_value = True
            MockFF.get_bin_dir.return_value = Path("/fake/bin")
            instance = MockFF.return_value
            instance.ffmpeg_path = "/fake/bin/ffmpeg.exe"
            instance.ffprobe_path = "/fake/bin/ffprobe.exe"
            status = svc.get_ffmpeg_status()

        assert status["installed"] is True
        assert status["ffmpeg_path"] == "/fake/bin/ffmpeg.exe"
        assert "bin_dir" in status
        # Confirm injected wrapper was NOT touched (proves the DI violation)
        injected_ffmpeg.is_installed.assert_not_called()

    def test_get_ffmpeg_status_when_not_installed(self, tmp_path):
        fs = make_file_service_mock(tmp_path)
        svc = VideoTranscodeService(ffmpeg=MagicMock(), file_service=fs, task_manager=MagicMock())

        with patch("app.services.video.transcode_service.FFmpegWrapper") as MockFF:
            MockFF.is_installed.return_value = False
            MockFF.get_bin_dir.return_value = Path("/fake/bin")
            status = svc.get_ffmpeg_status()

        assert status["installed"] is False
        assert status["ffmpeg_path"] is None
