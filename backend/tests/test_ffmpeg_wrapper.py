"""Tests for FFmpegWrapper — adapters/binary/ffmpeg.py."""
import pytest
import subprocess
import sys
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


# ── _parse_scene_times helper ───────────────────────────────────────────────

from app.adapters.binary.ffmpeg import _parse_scene_times


class TestParseSceneTimes:
    SAMPLE = (
        "frame:293  pts:156272  pts_time:9.767\n"
        "lavfi.scd.time=9.767\n"
        "frame:1595 pts:850672  pts_time:53.167\n"
        "lavfi.scd.time=53.167\n"
    )

    def test_extracts_scene_times(self):
        assert _parse_scene_times(self.SAMPLE) == [9.767, 53.167]

    def test_empty_input_returns_empty(self):
        assert _parse_scene_times("") == []

    def test_keys_off_scd_time_not_pts_time(self):
        # A frame header line carries pts_time: but no lavfi.scd.time= ->
        # parser must NOT pick it up.
        assert _parse_scene_times("frame:1  pts:1  pts_time:1.5\n") == []


# ── detect_scenes ───────────────────────────────────────────────────────────

import os
from app.adapters.binary.ffmpeg import MediaInfo


def _make_wrapper():
    """Construct FFmpegWrapper without touching the real filesystem for binaries."""
    with patch.object(FFmpegWrapper, "_find_ffmpeg", return_value="ffmpeg"), \
         patch.object(FFmpegWrapper, "_find_ffprobe", return_value="ffprobe"):
        return FFmpegWrapper()


def _fake_proc(progress_lines, stderr_bytes=b"", returncode=0):
    """Build an AsyncMock subprocess: stdout yields progress_lines then EOF."""
    proc = AsyncMock()
    proc.stdout.readline = AsyncMock(side_effect=[*progress_lines, b""])
    proc.stderr.read = AsyncMock(side_effect=[stderr_bytes, b""] if stderr_bytes else [b"", b""])
    proc.wait = AsyncMock(return_value=returncode)
    proc.returncode = returncode
    proc.kill = MagicMock()
    return proc


class TestDetectScenes:
    SCENE_META = (
        "frame:293  pts:156272  pts_time:9.767\n"
        "lavfi.scd.time=9.767\n"
        "frame:1595 pts:850672  pts_time:53.167\n"
        "lavfi.scd.time=53.167\n"
    )

    async def test_returns_scene_times_from_temp_file(self, tmp_path):
        w = _make_wrapper()
        video = tmp_path / "in.mp4"
        video.write_bytes(b"x")
        scene_file = tmp_path / "scdet.txt"
        scene_file.write_text(self.SCENE_META, encoding="utf-8")
        real_fd = os.open(str(scene_file), os.O_RDONLY)
        proc = _fake_proc([b"out_time_ms=5000000\n", b"progress=end\n"])

        with patch.object(w, "get_media_info",
                           new=AsyncMock(return_value=MagicMock(duration=100.0))), \
             patch("app.adapters.binary.ffmpeg.tempfile.mkstemp",
                   return_value=(real_fd, str(scene_file))), \
             patch("app.adapters.binary.ffmpeg.asyncio.create_subprocess_exec",
                   new=AsyncMock(return_value=proc)):
            result = await w.detect_scenes(video, scene_threshold=10.0, analyze_w=640)

        assert result == [9.767, 53.167]
        assert not scene_file.exists()  # temp file cleaned up

    async def test_builds_expected_ffmpeg_args(self, tmp_path):
        w = _make_wrapper()
        video = tmp_path / "in.mp4"
        video.write_bytes(b"x")
        scene_file = tmp_path / "scdet.txt"
        scene_file.write_text("", encoding="utf-8")
        real_fd = os.open(str(scene_file), os.O_RDONLY)
        proc = _fake_proc([b"progress=end\n"])
        spy = AsyncMock(return_value=proc)

        with patch.object(w, "get_media_info",
                           new=AsyncMock(return_value=MagicMock(duration=100.0))), \
             patch("app.adapters.binary.ffmpeg.tempfile.mkstemp",
                   return_value=(real_fd, str(scene_file))), \
             patch("app.adapters.binary.ffmpeg.asyncio.create_subprocess_exec", new=spy):
            await w.detect_scenes(video, scene_threshold=10.0, analyze_w=640)

        args = list(spy.call_args[0])
        vf = args[args.index("-vf") + 1]
        assert "scdet=threshold=10.0" in vf
        assert "scale='min(640,iw)':-2" in vf
        assert "metadata=mode=print" in vf and "key=lavfi.scd.time" in vf
        # bare filename only (no path) — escaping-free; ffmpeg cwd is the temp dir
        assert "file=scdet.txt" in vf
        assert spy.call_args.kwargs["cwd"] == str(tmp_path)
        assert "-progress" in args and "pipe:1" in args
        assert "-nostats" in args
        assert "-an" in args and "-sn" in args  # audio/subtitle skipped
        assert args[-3:] == ["-f", "null", "-"]
        assert "-hwaccel" not in args  # pure software decode

    async def test_reports_progress_fraction(self, tmp_path):
        w = _make_wrapper()
        video = tmp_path / "in.mp4"
        video.write_bytes(b"x")
        scene_file = tmp_path / "scdet.txt"
        scene_file.write_text("", encoding="utf-8")
        real_fd = os.open(str(scene_file), os.O_RDONLY)
        # duration 100s; out_time_ms 50_000_000 us = 50s -> fraction 0.5
        proc = _fake_proc([b"out_time_ms=50000000\n", b"progress=end\n"])
        seen = []

        with patch.object(w, "get_media_info",
                           new=AsyncMock(return_value=MagicMock(duration=100.0))), \
             patch("app.adapters.binary.ffmpeg.tempfile.mkstemp",
                   return_value=(real_fd, str(scene_file))), \
             patch("app.adapters.binary.ffmpeg.asyncio.create_subprocess_exec",
                   new=AsyncMock(return_value=proc)):
            await w.detect_scenes(video, scene_threshold=10.0, analyze_w=640,
                                  on_progress=seen.append)

        assert seen == [0.5]

    async def test_progress_accepts_us_key_and_dedupes(self, tmp_path):
        # A -progress block carries both out_time_us and out_time_ms (same
        # microsecond value). on_progress must fire once per distinct fraction.
        w = _make_wrapper()
        video = tmp_path / "in.mp4"
        video.write_bytes(b"x")
        scene_file = tmp_path / "scdet.txt"
        scene_file.write_text("", encoding="utf-8")
        real_fd = os.open(str(scene_file), os.O_RDONLY)
        proc = _fake_proc([b"out_time_us=50000000\n", b"out_time_ms=50000000\n",
                           b"progress=end\n"])
        seen = []

        with patch.object(w, "get_media_info",
                           new=AsyncMock(return_value=MagicMock(duration=100.0))), \
             patch("app.adapters.binary.ffmpeg.tempfile.mkstemp",
                   return_value=(real_fd, str(scene_file))), \
             patch("app.adapters.binary.ffmpeg.asyncio.create_subprocess_exec",
                   new=AsyncMock(return_value=proc)):
            await w.detect_scenes(video, scene_threshold=10.0, analyze_w=640,
                                  on_progress=seen.append)

        assert seen == [0.5]  # not [0.5, 0.5] — both keys, deduped

    async def test_non_zero_exit_raises(self, tmp_path):
        w = _make_wrapper()
        video = tmp_path / "in.mp4"
        video.write_bytes(b"x")
        scene_file = tmp_path / "scdet.txt"
        scene_file.write_text("", encoding="utf-8")
        real_fd = os.open(str(scene_file), os.O_RDONLY)
        proc = _fake_proc([b"progress=end\n"], stderr_bytes=b"boom", returncode=1)

        with patch.object(w, "get_media_info",
                           new=AsyncMock(return_value=MagicMock(duration=100.0))), \
             patch("app.adapters.binary.ffmpeg.tempfile.mkstemp",
                   return_value=(real_fd, str(scene_file))), \
             patch("app.adapters.binary.ffmpeg.asyncio.create_subprocess_exec",
                   new=AsyncMock(return_value=proc)):
            with pytest.raises(FFmpegError):
                await w.detect_scenes(video, scene_threshold=10.0, analyze_w=640)
        assert not scene_file.exists()  # temp file cleaned up even on failure

    async def test_cancellation_kills_subprocess_and_cleans_up(self, tmp_path):
        w = _make_wrapper()
        video = tmp_path / "in.mp4"
        video.write_bytes(b"x")
        scene_file = tmp_path / "scdet.txt"
        scene_file.write_text("", encoding="utf-8")
        real_fd = os.open(str(scene_file), os.O_RDONLY)
        proc = _fake_proc([b"out_time_ms=5000000\n", b"progress=end\n"])

        def boom(_frac):
            raise RuntimeError("cancelled")

        with patch.object(w, "get_media_info",
                           new=AsyncMock(return_value=MagicMock(duration=100.0))), \
             patch("app.adapters.binary.ffmpeg.tempfile.mkstemp",
                   return_value=(real_fd, str(scene_file))), \
             patch("app.adapters.binary.ffmpeg.asyncio.create_subprocess_exec",
                   new=AsyncMock(return_value=proc)):
            with pytest.raises(RuntimeError, match="cancelled"):
                await w.detect_scenes(video, scene_threshold=10.0, analyze_w=640,
                                      on_progress=boom)

        proc.kill.assert_called_once()      # subprocess killed, no orphan
        assert not scene_file.exists()      # temp file cleaned up

    def test_detect_scenes_sync_delegates(self, tmp_path):
        w = _make_wrapper()
        video = tmp_path / "in.mp4"
        video.write_bytes(b"x")
        scene_file = tmp_path / "scdet.txt"
        scene_file.write_text("lavfi.scd.time=3.0\n", encoding="utf-8")
        real_fd = os.open(str(scene_file), os.O_RDONLY)
        proc = _fake_proc([b"progress=end\n"])

        with patch.object(w, "get_media_info",
                           new=AsyncMock(return_value=MagicMock(duration=100.0))), \
             patch("app.adapters.binary.ffmpeg.tempfile.mkstemp",
                   return_value=(real_fd, str(scene_file))), \
             patch("app.adapters.binary.ffmpeg.asyncio.create_subprocess_exec",
                   new=AsyncMock(return_value=proc)):
            result = w.detect_scenes_sync(video, scene_threshold=10.0, analyze_w=640)

        assert result == [3.0]


class TestDetectScenesThreads:
    """`threads=None` (sentinel) auto-picks by media_info.duration:
    >=1200s -> unbounded (0), <1200s -> cap=4. Windows BELOW_NORMAL
    priority applies to both. See spec 2026-05-25-detect-priority-class.md §11."""

    async def test_auto_pick_unbounded_for_long_video(self, tmp_path):
        """threads=None default + duration >= 1200s -> -threads 0.

        Long videos benefit from saturating dav1d (detect_all is the long pole)
        so detect finishes during Whisper+LLM phase. See spec §11.3."""
        w = _make_wrapper()
        video = tmp_path / "in.mp4"
        video.write_bytes(b"x")
        scene_file = tmp_path / "scdet.txt"
        scene_file.write_text("", encoding="utf-8")
        real_fd = os.open(str(scene_file), os.O_RDONLY)
        try:
            spy = AsyncMock(return_value=_fake_proc([b""]))
            with patch.object(FFmpegWrapper, "get_media_info",
                              new=AsyncMock(return_value=MagicMock(duration=1500.0))), \
                 patch("app.adapters.binary.ffmpeg.tempfile.mkstemp",
                       return_value=(real_fd, str(scene_file))), \
                 patch("app.adapters.binary.ffmpeg.asyncio.create_subprocess_exec", new=spy):
                await w.detect_scenes(video, scene_threshold=10.0, analyze_w=640)
            args = list(spy.call_args[0])
            assert "-threads" in args, args
            assert args.index("-threads") < args.index("-i"), args
            assert args[args.index("-threads") + 1] == "0", args
        finally:
            try:
                os.close(real_fd)
            except OSError:
                pass

    async def test_auto_pick_capped_for_short_video(self, tmp_path):
        """threads=None default + duration < 1200s -> -threads 4.

        Short videos: dav1d work is small enough that 4T finishes quickly;
        unbounded 12T saturates RAM bandwidth and slows concurrent llama-server
        CPU bursts. See spec §11.2."""
        w = _make_wrapper()
        video = tmp_path / "in.mp4"
        video.write_bytes(b"x")
        scene_file = tmp_path / "scdet.txt"
        scene_file.write_text("", encoding="utf-8")
        real_fd = os.open(str(scene_file), os.O_RDONLY)
        try:
            spy = AsyncMock(return_value=_fake_proc([b""]))
            with patch.object(FFmpegWrapper, "get_media_info",
                              new=AsyncMock(return_value=MagicMock(duration=600.0))), \
                 patch("app.adapters.binary.ffmpeg.tempfile.mkstemp",
                       return_value=(real_fd, str(scene_file))), \
                 patch("app.adapters.binary.ffmpeg.asyncio.create_subprocess_exec", new=spy):
                await w.detect_scenes(video, scene_threshold=10.0, analyze_w=640)
            args = list(spy.call_args[0])
            assert "-threads" in args, args
            assert args.index("-threads") < args.index("-i"), args
            assert args[args.index("-threads") + 1] == "4", args
        finally:
            try:
                os.close(real_fd)
            except OSError:
                pass

    async def test_custom_threads_value(self, tmp_path):
        w = _make_wrapper()
        video = tmp_path / "in.mp4"
        video.write_bytes(b"x")
        scene_file = tmp_path / "scdet.txt"
        scene_file.write_text("", encoding="utf-8")
        real_fd = os.open(str(scene_file), os.O_RDONLY)
        try:
            spy = AsyncMock(return_value=_fake_proc([b""]))
            with patch.object(FFmpegWrapper, "get_media_info",
                              new=AsyncMock(return_value=MagicMock(duration=100.0))), \
                 patch("app.adapters.binary.ffmpeg.tempfile.mkstemp",
                       return_value=(real_fd, str(scene_file))), \
                 patch("app.adapters.binary.ffmpeg.asyncio.create_subprocess_exec", new=spy):
                await w.detect_scenes(video, scene_threshold=10.0, analyze_w=640, threads=2)
            args = list(spy.call_args[0])
            assert args[args.index("-threads") + 1] == "2", args
        finally:
            try:
                os.close(real_fd)
            except OSError:
                pass

    @pytest.mark.skipif(sys.platform != "win32", reason="creationflags is Windows-only")
    async def test_below_normal_priority_on_windows(self, tmp_path):
        """detect_scenes launches its FFmpeg subprocess with
        BELOW_NORMAL_PRIORITY_CLASS so the OS scheduler yields CPU to
        NORMAL-priority Whisper / llama-server. Spec §AC#1."""
        w = _make_wrapper()
        video = tmp_path / "in.mp4"
        video.write_bytes(b"x")
        scene_file = tmp_path / "scdet.txt"
        scene_file.write_text("", encoding="utf-8")
        real_fd = os.open(str(scene_file), os.O_RDONLY)
        try:
            spy = AsyncMock(return_value=_fake_proc([b""]))
            with patch.object(FFmpegWrapper, "get_media_info",
                              new=AsyncMock(return_value=MagicMock(duration=100.0))), \
                 patch("app.adapters.binary.ffmpeg.tempfile.mkstemp",
                       return_value=(real_fd, str(scene_file))), \
                 patch("app.adapters.binary.ffmpeg.asyncio.create_subprocess_exec", new=spy):
                await w.detect_scenes(video, scene_threshold=10.0, analyze_w=640)
            kwargs = spy.call_args.kwargs
            assert "creationflags" in kwargs, kwargs
            # Exact equality — flag is set as the ONLY creationflag (no OR with others).
            assert kwargs["creationflags"] == subprocess.BELOW_NORMAL_PRIORITY_CLASS, \
                hex(kwargs["creationflags"])
        finally:
            try:
                os.close(real_fd)
            except OSError:
                pass

    @pytest.mark.skipif(sys.platform == "win32", reason="non-Windows path")
    async def test_no_creationflags_on_posix(self, tmp_path):
        """On POSIX the spec deliberately does NOT pass creationflags so we
        stay portable and avoid relying on Python's silent no-op. Spec §AC#7."""
        w = _make_wrapper()
        video = tmp_path / "in.mp4"
        video.write_bytes(b"x")
        scene_file = tmp_path / "scdet.txt"
        scene_file.write_text("", encoding="utf-8")
        real_fd = os.open(str(scene_file), os.O_RDONLY)
        try:
            spy = AsyncMock(return_value=_fake_proc([b""]))
            with patch.object(FFmpegWrapper, "get_media_info",
                              new=AsyncMock(return_value=MagicMock(duration=100.0))), \
                 patch("app.adapters.binary.ffmpeg.tempfile.mkstemp",
                       return_value=(real_fd, str(scene_file))), \
                 patch("app.adapters.binary.ffmpeg.asyncio.create_subprocess_exec", new=spy):
                await w.detect_scenes(video, scene_threshold=10.0, analyze_w=640)
            assert "creationflags" not in spy.call_args.kwargs, spy.call_args.kwargs
        finally:
            try:
                os.close(real_fd)
            except OSError:
                pass
