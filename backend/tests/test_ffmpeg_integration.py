"""Integration tests for FFmpegWrapper — requires ffmpeg binary.

Run: pytest -m ffmpeg
"""
import pytest
import numpy as np
from pathlib import Path

pytestmark = pytest.mark.ffmpeg


@pytest.fixture
def ffmpeg():
    from app.engine.ffmpeg import FFmpegWrapper
    wrapper = FFmpegWrapper()
    if not wrapper.is_installed():
        pytest.skip("ffmpeg not installed")
    return wrapper


@pytest.fixture
def test_wav(tmp_path):
    """Generate a 2-second silent WAV file."""
    import soundfile as sf
    audio = np.zeros(44100 * 2, dtype=np.float32)
    path = tmp_path / "test.wav"
    sf.write(str(path), audio, 44100)
    return path


class TestFFmpegMediaInfo:
    async def test_get_media_info(self, ffmpeg, test_wav):
        info = await ffmpeg.get_media_info(test_wav)
        assert info.duration > 0
        assert info.fps >= 0
        assert isinstance(info.fps_fraction, __import__("fractions").Fraction)

    async def test_media_info_audio_codec(self, ffmpeg, test_wav):
        info = await ffmpeg.get_media_info(test_wav)
        assert info.audio_codec != ""


class TestFFmpegCut:
    async def test_cut_with_float_times(self, ffmpeg, test_wav, tmp_path):
        output = tmp_path / "cut.wav"
        result = await ffmpeg.cut(test_wav, output, start_time=0.0, end_time=1.0)
        assert result.exists()
        assert result.stat().st_size > 0

    async def test_cut_with_string_times(self, ffmpeg, test_wav, tmp_path):
        output = tmp_path / "cut.wav"
        result = await ffmpeg.cut(test_wav, output, start_time="00:00:00", end_time="00:00:01")
        assert result.exists()
        assert result.stat().st_size > 0


class TestFFmpegExtractAudio:
    async def test_extract_audio_wav_16k_mono(self, ffmpeg, test_wav, tmp_path):
        output = tmp_path / "out.wav"
        result = await ffmpeg.extract_audio(
            test_wav, output,
            audio_format="wav",
            sample_rate=16000,
            channels=1,
        )
        assert result.exists()
        import soundfile as sf
        data, sr = sf.read(str(result))
        assert sr == 16000
        assert data.ndim == 1  # mono


class TestFFmpegAdjustVolume:
    async def test_adjust_volume(self, ffmpeg, test_wav, tmp_path):
        output = tmp_path / "loud.wav"
        result = await ffmpeg.adjust_volume(test_wav, output, af_filter="volume=3dB")
        assert result.exists()
        assert result.stat().st_size > 0

    async def test_normalize(self, ffmpeg, test_wav, tmp_path):
        output = tmp_path / "normalized.wav"
        result = await ffmpeg.adjust_volume(test_wav, output, af_filter="loudnorm")
        assert result.exists()


class TestFFmpegAudioConvert:
    async def test_convert_to_mp3(self, ffmpeg, test_wav, tmp_path):
        output = tmp_path / "out.mp3"
        result = await ffmpeg.audio_convert(
            test_wav, output,
            audio_codec="libmp3lame",
            audio_bitrate="128k",
        )
        assert result.exists()
        assert result.stat().st_size > 0

    async def test_convert_to_flac(self, ffmpeg, test_wav, tmp_path):
        output = tmp_path / "out.flac"
        result = await ffmpeg.audio_convert(
            test_wav, output,
            audio_codec="flac",
            extra_args=["-sample_fmt", "s32"],
        )
        assert result.exists()

    async def test_convert_with_sample_rate(self, ffmpeg, test_wav, tmp_path):
        output = tmp_path / "out.wav"
        result = await ffmpeg.audio_convert(
            test_wav, output,
            audio_codec="pcm_s16le",
            sample_rate=22050,
            channels=1,
        )
        assert result.exists()
        import soundfile as sf
        _, sr = sf.read(str(result))
        assert sr == 22050
