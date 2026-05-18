"""Tests for FFmpegWrapper — adapters/binary/ffmpeg.py."""
import pytest
from fractions import Fraction
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.adapters.binary.ffmpeg import FFmpegWrapper, _parse_time, FFmpegError


# ── _parse_time helper ──────────────────────────────────────────────────────

class TestParseTime:
    def test_float_passthrough(self):
        assert _parse_time(3.5) == 3.5

    def test_int_passthrough(self):
        assert _parse_time(0) == 0.0

    def test_hhmmss_string(self):
        assert _parse_time("01:30:00") == 5400.0

    def test_mmss_string(self):
        assert _parse_time("02:30") == 150.0

    def test_seconds_string(self):
        assert _parse_time("45.5") == 45.5

    def test_zero_string(self):
        assert _parse_time("00:00:00") == 0.0

    def test_hhmmss_with_fraction(self):
        assert _parse_time("00:01:30.5") == 90.5


# ── FFmpegWrapper.cut() string time support ──────────────────────────────────

class TestCutStringTime:
    """Verify cut() accepts both float and string times."""

    @pytest.mark.ffmpeg
    async def test_cut_accepts_string_times(self, tmp_path):
        """cut() should not raise with string start/end times."""
        wrapper = FFmpegWrapper()
        if not wrapper.is_installed():
            pytest.skip("ffmpeg not installed")

        # Just verify the method signature accepts strings (will fail on missing input)
        with pytest.raises(FFmpegError, match="not found"):
            await wrapper.cut(
                input_path=tmp_path / "nonexistent.mp4",
                output_path=tmp_path / "out.mp4",
                start_time="00:00:05",
                end_time="00:00:10",
            )

    def test_cut_duration_validation_with_strings(self):
        """_parse_time should correctly compare start/end for validation."""
        start = _parse_time("00:01:00")
        end = _parse_time("00:00:30")
        assert end - start < 0, "end should be before start"

    def test_cut_valid_duration(self):
        start = _parse_time("00:00:05")
        end = _parse_time("00:00:10")
        assert end - start == 5.0


# ── FFmpegWrapper new methods exist ──────────────────────────────────────────

class TestFFmpegWrapperMethods:
    def test_has_extract_audio(self):
        assert hasattr(FFmpegWrapper, "extract_audio")

    def test_has_adjust_volume(self):
        assert hasattr(FFmpegWrapper, "adjust_volume")

    def test_has_audio_convert(self):
        assert hasattr(FFmpegWrapper, "audio_convert")

    def test_has_cut(self):
        assert hasattr(FFmpegWrapper, "cut")

    def test_has_transcode(self):
        assert hasattr(FFmpegWrapper, "transcode")


# ── extract_audio sample_rate / channels params ─────────────────────────────

class TestExtractAudioParams:
    @pytest.mark.ffmpeg
    async def test_extract_audio_with_sample_rate_channels(self, tmp_path):
        """extract_audio() should accept sample_rate and channels params."""
        wrapper = FFmpegWrapper()
        if not wrapper.is_installed():
            pytest.skip("ffmpeg not installed")

        with pytest.raises(FFmpegError, match="not found"):
            await wrapper.extract_audio(
                input_path=tmp_path / "nonexistent.mp4",
                output_path=tmp_path / "out.wav",
                audio_format="wav",
                sample_rate=16000,
                channels=1,
            )
