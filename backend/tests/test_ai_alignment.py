"""Integration tests for Wav2Vec2 alignment engine.

Requires: GPU + wav2vec2 language model auto-downloads from HuggingFace.
Run: pytest -m ai
"""
import pytest

pytestmark = pytest.mark.ai


@pytest.fixture
def alignment_engine():
    from app.adapters.ai.wrapper.wav2vec2 import AlignmentEngine
    return AlignmentEngine()


class TestAlignmentEngineAvailability:
    def test_engine_instantiable(self, alignment_engine):
        assert alignment_engine is not None

    def test_english_supported(self, alignment_engine):
        assert alignment_engine.is_language_supported("en")

    def test_chinese_supported(self, alignment_engine):
        assert alignment_engine.is_language_supported("zh")

    def test_korean_supported(self, alignment_engine):
        assert alignment_engine.is_language_supported("ko")

    def test_unsupported_language(self, alignment_engine):
        assert not alignment_engine.is_language_supported("xyz")


class TestAlignmentAlign:
    def test_align_empty_segments(self, alignment_engine, tmp_path):
        """Align with empty segments should return empty list."""
        import numpy as np
        import soundfile as sf

        audio = np.zeros(16000, dtype=np.float32)
        audio_path = tmp_path / "silence.wav"
        sf.write(str(audio_path), audio, 16000)

        result = alignment_engine.align(
            audio_path=str(audio_path),
            segments=[],
            language="en",
            ffmpeg_path="ffmpeg",  # not invoked (empty segments)
        )
        assert result == []
