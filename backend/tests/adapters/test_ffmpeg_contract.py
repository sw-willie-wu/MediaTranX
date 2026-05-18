"""Contract tests for app.adapters.binary.ffmpeg.FFmpegWrapper.

Drift guard: if FFmpegWrapper's method signatures change (rename, kwarg drop,
return-type change), service tests that mock these methods will silently pass
while production breaks. These tests verify the contract surface 4 Wave C
services depend on.

No real ffmpeg invocation — only inspect the method signature.
"""
from __future__ import annotations

import inspect

import pytest

from app.adapters.binary.ffmpeg import FFmpegWrapper


def _get_kwargs(method) -> set[str]:
    """Return the set of parameter names accepted by a method (excluding self)."""
    sig = inspect.signature(method)
    return {name for name, param in sig.parameters.items() if name != "self"}


def test_cut_sync_signature():
    """AudioCutService passes input_path/output_path/start_time/end_time/stream_copy."""
    params = _get_kwargs(FFmpegWrapper.cut_sync)
    required = {"input_path", "output_path", "start_time", "end_time", "stream_copy"}
    assert required.issubset(params), f"missing: {required - params}"


def test_audio_convert_sync_signature():
    """AudioTranscodeService passes input_path/output_path/audio_codec/audio_bitrate/sample_rate/channels/extra_args."""
    params = _get_kwargs(FFmpegWrapper.audio_convert_sync)
    required = {"input_path", "output_path", "audio_codec",
                "audio_bitrate", "sample_rate", "channels", "extra_args"}
    assert required.issubset(params), f"missing: {required - params}"


def test_adjust_volume_sync_signature():
    """AudioVolumeService passes input_path/output_path/af_filter."""
    params = _get_kwargs(FFmpegWrapper.adjust_volume_sync)
    required = {"input_path", "output_path", "af_filter"}
    assert required.issubset(params), f"missing: {required - params}"


def test_get_media_info_is_async():
    """AudioTranscodeService awaits this."""
    assert inspect.iscoroutinefunction(FFmpegWrapper.get_media_info)


def test_audio_convert_is_async():
    """AudioMidiService.convert_wav awaits this."""
    assert inspect.iscoroutinefunction(FFmpegWrapper.audio_convert)


def test_audio_convert_sync_signature_covers_separate_mp3_branch():
    """After 2986c37, separate_service's inline mp3 branch instantiates
    FFmpegWrapper() and calls audio_convert_sync(input_path=, output_path=,
    audio_codec='libmp3lame', audio_bitrate='192k'). audio_convert_sync was
    already covered above; this is a regression guard for the original bug
    where production reached for a non-existent .convert(...) method."""
    assert hasattr(FFmpegWrapper, "audio_convert_sync")
    assert not hasattr(FFmpegWrapper, "convert"), (
        "If FFmpegWrapper.convert is added later, audit separate_service "
        "mp3 branch to ensure it still uses audio_convert_sync (correct API)."
    )
