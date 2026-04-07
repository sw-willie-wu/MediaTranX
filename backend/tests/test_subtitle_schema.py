"""Tests for SubtitleGenerateRequest schema — video/subtitle.py."""
import pytest

from app.api.routes.video.subtitle import SubtitleGenerateRequest


class TestSubtitleGenerateRequest:
    def test_align_field_exists(self):
        req = SubtitleGenerateRequest(file_id="test")
        assert hasattr(req, "align")

    def test_align_default_false(self):
        req = SubtitleGenerateRequest(file_id="test")
        assert req.align is False

    def test_align_accepts_true(self):
        req = SubtitleGenerateRequest(file_id="test", align=True)
        assert req.align is True

    def test_defaults_match_frontend(self):
        """Frontend WhisperAdvancedSettings defaults must match schema defaults."""
        req = SubtitleGenerateRequest(file_id="test")
        assert req.min_silence_duration_ms == 500
        assert req.vad_threshold == 0.5
        assert req.word_timestamps is False
        assert req.condition_on_previous_text is True

    def test_all_translate_fields(self):
        req = SubtitleGenerateRequest(
            file_id="test",
            target_language="zh-TW",
            translate_model_type="qwen3",
            translate_model_size="8b",
            translate_quantization="Q4_K_M",
            keep_names=True,
            translate_style="formal",
        )
        assert req.target_language == "zh-TW"
        assert req.translate_model_type == "qwen3"
