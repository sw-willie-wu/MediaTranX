"""Integration tests for FFmpegWrapper — requires ffmpeg binary.

Run: pytest -m ffmpeg
"""
import pytest
import numpy as np
from pathlib import Path

pytestmark = pytest.mark.ffmpeg


@pytest.fixture
def ffmpeg():
    from app.adapters.binary.ffmpeg import FFmpegWrapper
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


def _make_src(tmp_path, w, h):
    """A solid-color PNG of exact (w,h). PNG has no even-dimension
    constraint (unlike libx264/mp4), so odd sizes are representable.
    extract_frame reads it as a single-frame input (ffmpeg autodetects;
    `-ss 0 -i img.png -vframes 1` grabs the image)."""
    from PIL import Image
    src = tmp_path / f"src_{w}x{h}.png"
    Image.new("RGB", (w, h), (200, 30, 30)).save(src)
    return src


class TestExtractFrameDownscaleDims:
    @pytest.mark.parametrize("sw,sh,edge,exp", [
        (1920, 1080, 768, (768, 432)),    # landscape down
        (1080, 1920, 768, (432, 768)),    # portrait down
        (1000, 1000, 768, (768, 768)),    # square down
        (640, 480, 768, (640, 480)),      # sub-N even → unchanged
    ])
    async def test_dims(self, ffmpeg, tmp_path, sw, sh, edge, exp):
        from PIL import Image
        src = _make_src(tmp_path, sw, sh)
        out = tmp_path / "o.jpg"
        await ffmpeg.extract_frame(src, out, 0.0, max_edge=edge)
        assert Image.open(out).size == exp

    async def test_proportional_other_axis_rounded_even(self, ffmpeg, tmp_path):
        # 1000x563 → longest edge 768: w=768, h=563*768/1000≈432.4 → -2
        # forces the computed axis to the nearest even value.
        from PIL import Image
        src = _make_src(tmp_path, 1000, 563)
        out = tmp_path / "o.jpg"
        await ffmpeg.extract_frame(src, out, 0.0, max_edge=768)
        w, h = Image.open(out).size
        assert w == 768
        assert h % 2 == 0 and abs(h - 432) <= 2  # -2 even-rounding, ~proportional

    async def test_sub_n_odd_dim_not_upscaled_odd_axis_even(self, ffmpeg, tmp_path):
        # 321x241 ≤ 768: never upscaled; the -2 axis is even; both axes
        # within ≤1px of source (exact JPEG odd-axis handling is encoder-
        # dependent, so assert the AC2 contract, not exact pixels).
        from PIL import Image
        src = _make_src(tmp_path, 321, 241)
        out = tmp_path / "o.jpg"
        await ffmpeg.extract_frame(src, out, 0.0, max_edge=768)
        w, h = Image.open(out).size
        assert abs(w - 321) <= 1 and abs(h - 241) <= 1  # not upscaled, ≤1px
        assert h % 2 == 0                                # -2 axis even
        assert max(w, h) <= 768                          # never upscaled

    async def test_none_is_native(self, ffmpeg, tmp_path):
        from PIL import Image
        src = _make_src(tmp_path, 1280, 720)
        out = tmp_path / "o.jpg"
        await ffmpeg.extract_frame(src, out, 0.0)
        assert Image.open(out).size == (1280, 720)
