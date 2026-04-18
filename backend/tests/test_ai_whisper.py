"""Integration tests for Whisper speech recognition engine.

Requires: GPU + downloaded Whisper model.
Run: pytest -m ai
"""
import pytest
from pathlib import Path

pytestmark = pytest.mark.ai


@pytest.fixture
def whisper():
    from app.adapters.ai.wrapper.whisper import get_whisper
    return get_whisper()


@pytest.fixture
def test_audio(tmp_path):
    """Generate a short silent WAV for testing."""
    import numpy as np
    import soundfile as sf
    audio = np.zeros(16000, dtype=np.float32)  # 1 second silence
    path = tmp_path / "silence.wav"
    sf.write(str(path), audio, 16000)
    return path


class TestWhisperAvailability:
    def test_get_whisper_returns_instance(self, whisper):
        assert whisper is not None

    def test_model_status_structure(self, whisper):
        status = whisper.get_model_status("medium")
        assert "available" in status
        assert "model_downloaded" in status
        assert "model_size" in status


class TestWhisperTranscribe:
    def test_transcribe_silent_audio(self, whisper, test_audio):
        status = whisper.get_model_status("medium")
        if not status["model_downloaded"]:
            pytest.skip("Whisper medium model not downloaded")

        progress_calls = []
        result = whisper.transcribe(
            audio_path=str(test_audio),
            language=None,
            model_size="medium",
            on_progress=lambda p, m: progress_calls.append((p, m)),
        )
        assert hasattr(result, "segments")
        assert hasattr(result, "language")
        assert hasattr(result, "duration")

    def test_transcribe_returns_segments(self, whisper, test_audio):
        status = whisper.get_model_status("tiny")
        if not status["model_downloaded"]:
            pytest.skip("Whisper tiny model not downloaded")

        result = whisper.transcribe(
            audio_path=str(test_audio),
            language="en",
            model_size="tiny",
            on_progress=lambda p, m: None,
        )
        assert isinstance(result.segments, list)
