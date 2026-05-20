"""Tests for WhisperWrapper internals — pure functions + Chinese branches + bug regressions."""
from __future__ import annotations
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from app.adapters.ai.wrapper.whisper import (
    WhisperWrapper,
    TranscribeSegment,
    TranscribeWord,
    _split_by_words,
    _recursive_split,
    _zombie_models,
)


@pytest.fixture(autouse=True)
def _reset_zombies():
    """Prevent _zombie_models from growing across tests in this file.

    Production grows this list intentionally (Windows crash protection); tests
    that touch transcribe()/_cleanup_model() each add an entry. Without reset,
    the list grows unboundedly across the whole pytest run.
    """
    before = len(_zombie_models)
    yield
    del _zombie_models[before:]


class TestSplitByWords:
    def test_empty_words_returns_empty(self):
        assert _split_by_words([]) == []

    def test_short_sentence_returns_single_segment(self):
        words = [
            TranscribeWord("Hello", 0.0, 0.5, 0.99),
            TranscribeWord(" world.", 0.5, 1.0, 0.99),
        ]
        result = _split_by_words(words)
        assert len(result) == 1
        assert result[0].text == "Hello world."
        assert result[0].start == 0.0
        assert result[0].end == 1.0

    def test_long_sentence_with_pause_splits(self):
        # Long enough to exceed _MAX_CHARS_PER_LINE (42) with a 0.6s pause
        left = TranscribeWord("This is a fairly long opening clause", 0.0, 2.0, 0.99)
        right = TranscribeWord(" and here is the second clause too", 2.6, 4.5, 0.99)
        result = _split_by_words([left, right])
        assert len(result) >= 2

    def test_no_pause_long_sentence_returns_single(self):
        """Without pause points, long text stays as single segment."""
        words = [TranscribeWord("a" * 100, 0.0, 5.0, 0.99)]
        result = _split_by_words(words)
        assert len(result) == 1


class TestGetModelStatus:
    def test_returns_dict_with_required_keys(self, tmp_path, monkeypatch):
        from app.init.configs import SETTINGS
        monkeypatch.setattr(SETTINGS.path, "models", tmp_path)
        w = WhisperWrapper()
        status = w.get_model_status("medium")
        assert isinstance(status, dict)
        assert "available" in status
        assert "model_downloaded" in status


class TestChineseBranches:
    """Chinese variants get specific Whisper language code + initial_prompt + opencc conversion."""

    def _make_transcribe_mocks(self, segment_text: str):
        fake_model = MagicMock()
        fake_info = MagicMock()
        fake_info.language = "zh"
        fake_info.language_probability = 0.99
        fake_info.duration = 1.0
        fake_segment = MagicMock(start=0.0, end=1.0, text=segment_text, words=None)
        fake_model.transcribe.return_value = ([fake_segment], fake_info)
        return fake_model

    def test_zh_tw_uses_traditional_prompt(self):
        """language='zh-TW' → whisper_lang='zh' + s2t conversion."""
        w = WhisperWrapper()
        fake_model = self._make_transcribe_mocks("简体文本")

        @contextmanager
        def _acquire(model_id=None, variant=None, on_progress=None):
            w._model = fake_model
            w._device = "cpu"
            yield w

        with patch.object(w, "acquire", _acquire), \
             patch("opencc.OpenCC") as MockOpenCC:
            converter = MagicMock()
            converter.convert.return_value = "繁體文本"
            MockOpenCC.return_value = converter
            result = w.transcribe("/fake/audio.wav", language="zh-TW")

        call = fake_model.transcribe.call_args
        assert call.kwargs["language"] == "zh"
        assert "繁體" in call.kwargs["initial_prompt"]
        MockOpenCC.assert_called_with("s2t")
        assert result.segments[0].text == "繁體文本"

    def test_zh_cn_uses_simplified_conversion(self):
        """language='zh-CN' → whisper_lang='zh' + t2s conversion."""
        w = WhisperWrapper()
        fake_model = self._make_transcribe_mocks("繁體文本")

        @contextmanager
        def _acquire(model_id=None, variant=None, on_progress=None):
            w._model = fake_model
            w._device = "cpu"
            yield w

        with patch.object(w, "acquire", _acquire), \
             patch("opencc.OpenCC") as MockOpenCC:
            converter = MagicMock()
            converter.convert.return_value = "简体文本"
            MockOpenCC.return_value = converter
            w.transcribe("/fake/audio.wav", language="zh-CN")

        call = fake_model.transcribe.call_args
        assert call.kwargs["language"] == "zh"
        assert "简体" in call.kwargs["initial_prompt"]
        MockOpenCC.assert_called_with("t2s")


class TestFinallyCallsUnload:
    """Bug-#2 regression: finally block must call self.unload(), not the
    non-existent self._unload_model()."""

    def test_transcribe_finally_calls_unload(self):
        w = WhisperWrapper()
        fake_model = MagicMock()
        fake_info = MagicMock()
        fake_info.language = "en"
        fake_info.language_probability = 0.99
        fake_info.duration = 0.0
        fake_model.transcribe.return_value = (iter([]), fake_info)

        @contextmanager
        def _acquire(model_id=None, variant=None, on_progress=None):
            w._model = fake_model
            w._device = "cpu"
            yield w

        with patch.object(w, "acquire", _acquire), \
             patch.object(w, "unload") as mock_unload:
            w.transcribe("/fake/audio.wav")
        mock_unload.assert_called_once()

    def test_transcribe_finally_calls_unload_on_exception(self):
        w = WhisperWrapper()
        fake_model = MagicMock()
        fake_model.transcribe.side_effect = RuntimeError("model failure")

        @contextmanager
        def _acquire(model_id=None, variant=None, on_progress=None):
            w._model = fake_model
            w._device = "cpu"
            yield w

        with patch.object(w, "acquire", _acquire), \
             patch.object(w, "unload") as mock_unload:
            with pytest.raises(RuntimeError, match="model failure"):
                w.transcribe("/fake/audio.wav")
        mock_unload.assert_called_once()


class TestCleanupModelZombieList:
    def test_cleanup_model_appends_zombie(self):
        w = WhisperWrapper()
        fake_model = MagicMock()
        fake_model.model = MagicMock()
        fake_model.model.unload_model = MagicMock()
        w._model = fake_model

        initial_zombies = len(_zombie_models)
        w._cleanup_model()
        assert len(_zombie_models) == initial_zombies + 1
        assert _zombie_models[-1] is fake_model

    def test_cleanup_model_noop_when_model_none(self):
        w = WhisperWrapper()
        w._model = None
        initial_zombies = len(_zombie_models)
        w._cleanup_model()
        assert len(_zombie_models) == initial_zombies
