"""Tests for MediaInfo fps_fraction field."""
from fractions import Fraction
from dataclasses import fields

from app.engine.ffmpeg import MediaInfo


class TestMediaInfoFpsFraction:
    def test_has_fps_fraction_field(self):
        field_names = [f.name for f in fields(MediaInfo)]
        assert "fps_fraction" in field_names

    def test_fraction_type(self):
        info = MediaInfo(
            duration=10.0, width=1920, height=1080,
            fps=29.97, fps_fraction=Fraction(30000, 1001),
            video_codec="h264", audio_codec="aac",
            bitrate=5000, file_size=1000000,
        )
        assert isinstance(info.fps_fraction, Fraction)
        assert info.fps_fraction == Fraction(30000, 1001)

    def test_fraction_precision(self):
        """Fraction multiplication preserves precision unlike float."""
        frac = Fraction(30000, 1001)
        doubled = frac * 2
        assert doubled == Fraction(60000, 1001)
        # float would give 59.94005994005994, Fraction stays exact
        assert doubled.numerator == 60000
        assert doubled.denominator == 1001

    def test_common_fps_values(self):
        """Common video frame rates as Fractions."""
        cases = [
            (Fraction(24000, 1001), 23.976),
            (Fraction(30000, 1001), 29.97),
            (Fraction(60000, 1001), 59.94),
            (Fraction(25, 1), 25.0),
            (Fraction(30, 1), 30.0),
            (Fraction(60, 1), 60.0),
        ]
        for frac, expected_float in cases:
            assert abs(float(frac) - expected_float) < 0.01


class TestKoreanWav2Vec2:
    def test_korean_repo_exists(self):
        from app.engine.ai.audio.wav2vec2 import LANG_MODELS
        assert "ko" in LANG_MODELS
        assert LANG_MODELS["ko"] == "kresnik/wav2vec2-large-xlsr-korean"

    def test_all_languages_defined(self):
        from app.engine.ai.audio.wav2vec2 import LANG_MODELS
        expected = {"en", "zh", "ja", "ko", "fr", "de", "es", "pt", "it", "nl", "pl", "ru", "ar", "fi", "hu", "el"}
        assert set(LANG_MODELS.keys()) == expected
