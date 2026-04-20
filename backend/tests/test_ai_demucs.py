"""Integration tests for Demucs audio source separation.

Requires: GPU + Demucs model.
Run: pytest -m ai
"""
import pytest

pytestmark = pytest.mark.ai


@pytest.fixture
def demucs():
    from app.adapters.ai.wrapper.demucs import DemucsWrapper
    return DemucsWrapper()


class TestDemucsAvailability:
    def test_demucs_wrapper_instantiable(self, demucs):
        assert demucs is not None

    def test_model_status_structure(self, demucs):
        status = demucs.get_model_status("htdemucs_6s")
        assert "available" in status
        assert "model_downloaded" in status


class TestDemucsSeparation:
    def test_separate_silent_audio(self, demucs, tmp_path):
        status = demucs.get_model_status("htdemucs_6s")
        if not status["model_downloaded"]:
            pytest.skip("Demucs model not downloaded")

        import numpy as np
        import soundfile as sf

        audio = np.zeros((44100 * 2, 2), dtype=np.float32)  # 2 sec stereo
        audio_path = tmp_path / "silence.wav"
        sf.write(str(audio_path), audio, 44100)

        stems, sr = demucs.separate(
            audio_path=str(audio_path),
            variant="htdemucs_6s",
            stems=None,
            on_progress=lambda p, m: None,
        )
        assert isinstance(stems, dict)
        assert sr > 0
        assert "vocals" in stems
