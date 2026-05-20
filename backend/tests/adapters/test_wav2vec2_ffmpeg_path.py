"""Regression: wav2vec2.align() requires ffmpeg_path (no legacy fallback)."""
import pytest
from app.adapters.ai.wrapper.wav2vec2 import AlignmentEngine


def test_align_requires_ffmpeg_path():
    engine = AlignmentEngine()
    with pytest.raises(TypeError):
        engine.align(
            audio_path="/does/not/matter",
            segments=[],
            language="en",
            # ffmpeg_path omitted — must raise TypeError
        )
