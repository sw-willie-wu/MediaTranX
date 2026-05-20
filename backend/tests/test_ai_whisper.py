"""Integration tests for Whisper speech recognition engine.

Requires: GPU + downloaded Whisper model (large-v3 used by default).
Run: pytest -m ai
"""
import pytest
from pathlib import Path

pytestmark = pytest.mark.ai

# Variants in priority order — first one that's downloaded gets used.
_PREFERRED_SIZES = ["large-v3", "medium", "small", "base", "tiny"]


def _pick_available_size(whisper):
    for size in _PREFERRED_SIZES:
        if whisper.get_model_status(size).get("model_downloaded"):
            return size
    return None


@pytest.fixture
def whisper():
    """Whisper wrapper wired through DI container so _model_manager is set."""
    from app.init.container import init_container
    c = init_container()
    w = c.whisper_wrapper()
    w._model_manager = c.model_manager()
    return w


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
    def test_whisper_wrapper_instantiable(self, whisper):
        assert whisper is not None

    def test_model_status_structure(self, whisper):
        status = whisper.get_model_status("large-v3")
        assert "available" in status
        assert "model_downloaded" in status
        assert "model_size" in status


class TestWhisperTranscribe:
    def test_transcribe_silent_audio(self, whisper, test_audio):
        size = _pick_available_size(whisper)
        if size is None:
            pytest.skip(f"No Whisper model downloaded (tried {_PREFERRED_SIZES})")

        progress_calls = []
        result = whisper.transcribe(
            audio_path=str(test_audio),
            language=None,
            model_size=size,
            on_progress=lambda p, m: progress_calls.append((p, m)),
        )
        assert hasattr(result, "segments")
        assert hasattr(result, "language")
        assert hasattr(result, "duration")

    def test_transcribe_returns_segments(self, whisper, test_audio):
        size = _pick_available_size(whisper)
        if size is None:
            pytest.skip(f"No Whisper model downloaded (tried {_PREFERRED_SIZES})")

        result = whisper.transcribe(
            audio_path=str(test_audio),
            language="en",
            model_size=size,
            on_progress=lambda p, m: None,
        )
        assert isinstance(result.segments, list)
