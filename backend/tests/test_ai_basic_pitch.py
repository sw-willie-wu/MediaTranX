"""Integration tests for Basic Pitch audio-to-MIDI.

Requires: basic-pitch package (CPU-only, no GPU needed).
Run: pytest -m ai
"""
import pytest

pytestmark = pytest.mark.ai


@pytest.fixture
def basic_pitch():
    """Register the wrapper with a ModelManager so `BaseWrapper.acquire()` works.

    Post-`084e05e` (Wrapper Acquire Bridge) every wrapper that calls
    `self.acquire(...)` needs `wrapper._model_manager` attached; otherwise
    `BaseWrapper.acquire` raises RuntimeError.
    """
    from app.adapters.ai.wrapper.basic_pitch import BasicPitchWrapper
    from app.adapters.ai.model_manager import ModelManager
    mm = ModelManager()
    wrapper = BasicPitchWrapper()
    mm.register_runtime(wrapper)
    return wrapper


class TestBasicPitch:
    def test_get_instance(self, basic_pitch):
        assert basic_pitch is not None

    def test_model_status(self, basic_pitch):
        status = basic_pitch.get_model_status()
        assert "available" in status

    def test_audio_to_midi_silent(self, basic_pitch, tmp_path):
        status = basic_pitch.get_model_status()
        if not status.get("available"):
            pytest.skip("Basic Pitch not available")

        import numpy as np
        import soundfile as sf

        audio = np.zeros(22050 * 2, dtype=np.float32)  # 2 sec mono
        audio_path = tmp_path / "silence.wav"
        sf.write(str(audio_path), audio, 22050)

        result = basic_pitch.audio_to_midi(
            audio_path=str(audio_path),
            on_progress=lambda p, m: None,
        )
        assert isinstance(result, dict)
        assert "notes" in result
