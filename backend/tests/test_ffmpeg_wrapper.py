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


# ── extract_frame max_edge ──────────────────────────────────────────────────

class TestExtractFrameMaxEdge:
    """extract_frame ffmpeg args: byte-identical when max_edge=None;
    adds -vf scale when set. No real ffmpeg (subprocess mocked)."""

    def _wrapper(self):
        # FFmpegWrapper.__init__ calls _find_ffmpeg() AND _find_ffprobe()
        # (ffmpeg.py:120-122); patch both so the unit test is fully
        # environment-independent (no real binary discovery).
        from unittest.mock import patch
        from app.adapters.binary.ffmpeg import FFmpegWrapper
        with patch.object(FFmpegWrapper, "_find_ffmpeg", return_value="ffmpeg"), \
             patch.object(FFmpegWrapper, "_find_ffprobe", return_value="ffprobe"):
            return FFmpegWrapper()

    async def _capture_args(self, w, **kw):
        from unittest.mock import patch, AsyncMock
        proc = AsyncMock()
        proc.returncode = 0
        proc.communicate = AsyncMock(return_value=(b"", b""))
        with patch(
            "app.adapters.binary.ffmpeg.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=proc),
        ) as m:
            await w.extract_frame(**kw)
        return list(m.call_args.args)

    # No @pytest.mark.asyncio needed: pyproject.toml sets asyncio_mode="auto",
    # so bare `async def` tests run automatically.
    async def test_no_max_edge_args_unchanged(self, tmp_path):
        w = self._wrapper()
        # extract_frame guards `if not input_path.exists()` (ffmpeg.py:532-533)
        # BEFORE the subprocess call, so the input must really exist even
        # though the subprocess itself is mocked.
        src = tmp_path / "in.mp4"
        src.write_bytes(b"x")
        out = tmp_path / "f.jpg"
        args = await self._capture_args(
            w, input_path=src, output_path=out, timestamp=42.5
        )
        assert args == [
            "ffmpeg", "-y", "-ss", "42.500", "-i", str(src),
            "-vframes", "1", "-q:v", "2", str(out),
        ]
        assert "-vf" not in args

    async def test_max_edge_adds_scale_filter(self, tmp_path):
        w = self._wrapper()
        src = tmp_path / "in.mp4"
        src.write_bytes(b"x")
        out = tmp_path / "f.jpg"
        args = await self._capture_args(
            w, input_path=src, output_path=out, timestamp=1.0,
            max_edge=768,
        )
        assert "-vf" in args
        vf = args[args.index("-vf") + 1]
        assert vf == (
            "scale='if(gt(iw,ih),min(768,iw),-2)':"
            "'if(gt(iw,ih),-2,min(768,ih))'"
        )
        assert args.index("-vf") < args.index(str(out))  # filter before output
