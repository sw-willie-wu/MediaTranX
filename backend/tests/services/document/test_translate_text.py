"""Unit tests for app.services.document.translate_service.text."""
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from app.services.document.translate_service import text as txt_mod


_FAKE_CONFIG = {
    "n_ctx": 4096,
    "temperature": 0.1,
    "top_k": 40,
    "top_p": 0.9,
    "prompt_builder": "default",
    "thinking": False,
    "max_tokens_strategy": "fixed",
    "max_tokens": 2048,
}

_FAKE_REMOTE_CONFIG = {"temperature": 0.2, "max_tokens": 4096}


@contextmanager
def _noop_fake_progress(*args, **kwargs):
    yield


# --- _get_cloud_text_chunk_size ---

def test_get_cloud_text_chunk_size_has_minimum_floor():
    """Returned chunk size must be at least 1000 chars even with tiny n_ctx."""
    class OpenAIProvider:
        pass
    prov = OpenAIProvider()
    with patch("app.pipeline.translate.get_cloud_ctx", return_value=100):
        result = txt_mod._get_cloud_text_chunk_size(prov, "m")
    assert result >= 1000


def test_get_cloud_text_chunk_size_scales_with_ctx():
    class OpenAIProvider:
        pass
    prov = OpenAIProvider()
    with patch("app.pipeline.translate.get_cloud_ctx", return_value=128000):
        result = txt_mod._get_cloud_text_chunk_size(prov, "m")
    # (128000 // 4) * 2 = 64000
    assert result == 64000


# --- translate_text_cloud ---

def test_translate_text_cloud_single_chunk_emits_translating_key():
    class OpenAIProvider:
        pass
    prov = OpenAIProvider()
    prov.chat = MagicMock(return_value="翻譯結果")
    events = []
    def on_progress(p, m): events.append((p, m))

    with patch("app.adapters.ai.inference_config.get_remote_inference_config", return_value=_FAKE_REMOTE_CONFIG), \
         patch("app.utils.prompts.build_translate_prompt", return_value="prompt"), \
         patch("app.utils.text_chunking.split_text", return_value=["short text"]):
        result = txt_mod.translate_text_cloud(
            "short text", "en", "zh-TW", prov, "gpt-4o",
            on_progress=on_progress, max_chars=5000,
        )
    assert result == "翻譯結果"
    prov.chat.assert_called_once()
    msgs = [m for _, m in events]
    assert any(m == "task.progress.translating" for m in msgs)


def test_translate_text_cloud_multi_chunk_concatenates_with_blank_line():
    class OpenAIProvider:
        pass
    prov = OpenAIProvider()
    prov.chat = MagicMock(side_effect=["A", "B", "C"])
    with patch("app.adapters.ai.inference_config.get_remote_inference_config", return_value=_FAKE_REMOTE_CONFIG), \
         patch("app.utils.prompts.build_translate_prompt", return_value="p"), \
         patch("app.utils.text_chunking.split_text", return_value=["c1", "c2", "c3"]):
        result = txt_mod.translate_text_cloud(
            "long text", "en", "zh-TW", prov, "gpt-4o", max_chars=5000,
        )
    assert result == "A\n\nB\n\nC"
    assert prov.chat.call_count == 3


# --- translate_text_local ---

def test_translate_text_local_chat_mode_calls_session_chat():
    session = MagicMock()
    session.chat = MagicMock(return_value="zh-out")
    session.complete = MagicMock()
    fake_builder = lambda *a, **k: {"mode": "chat", "messages": [{"role": "user", "content": "x"}]}

    with patch("app.adapters.ai.inference_config.get_inference_config", return_value=_FAKE_CONFIG), \
         patch("app.utils.prompts.get_prompt_builder", return_value=fake_builder), \
         patch("app.utils.text_chunking.split_text", return_value=["chunk-1"]), \
         patch("app.utils.inference.fake_progress", _noop_fake_progress), \
         patch("app.utils.inference.calc_max_tokens", return_value=512), \
         patch("app.utils.inference.estimate_tokens", return_value=100):
        result = txt_mod.translate_text_local(
            "in", "en", "zh-TW", session, max_chars=5000,
        )
    assert result == "zh-out"
    session.chat.assert_called_once()
    session.complete.assert_not_called()


def test_translate_text_local_complete_mode_calls_session_complete():
    session = MagicMock()
    session.chat = MagicMock()
    session.complete = MagicMock(return_value="zh-out")
    fake_builder = lambda *a, **k: {"mode": "complete", "prompt": "translate"}

    with patch("app.adapters.ai.inference_config.get_inference_config", return_value=_FAKE_CONFIG), \
         patch("app.utils.prompts.get_prompt_builder", return_value=fake_builder), \
         patch("app.utils.text_chunking.split_text", return_value=["chunk-1"]), \
         patch("app.utils.inference.fake_progress", _noop_fake_progress), \
         patch("app.utils.inference.calc_max_tokens", return_value=512), \
         patch("app.utils.inference.estimate_tokens", return_value=100):
        result = txt_mod.translate_text_local(
            "in", "en", "zh-TW", session, max_chars=5000,
        )
    assert result == "zh-out"
    session.complete.assert_called_once()
    session.chat.assert_not_called()


def test_translate_text_local_emits_translating_segment_progress():
    session = MagicMock()
    session.chat = MagicMock(return_value="out")
    fake_builder = lambda *a, **k: {"mode": "chat", "messages": []}

    events = []
    def on_progress(p, m): events.append((p, m))

    with patch("app.adapters.ai.inference_config.get_inference_config", return_value=_FAKE_CONFIG), \
         patch("app.utils.prompts.get_prompt_builder", return_value=fake_builder), \
         patch("app.utils.text_chunking.split_text", return_value=["c1", "c2"]), \
         patch("app.utils.inference.fake_progress", _noop_fake_progress), \
         patch("app.utils.inference.calc_max_tokens", return_value=512), \
         patch("app.utils.inference.estimate_tokens", return_value=10):
        txt_mod.translate_text_local(
            "in", "en", "zh-TW", session, max_chars=5000,
            on_progress=on_progress,
        )
    msgs = [m for _, m in events]
    assert all(m.startswith("task.progress.translating_segment") for m in msgs)


def test_text_progress_msg_single_chunk_is_generic_not_frozen():
    # single chunk → no running index; generic 'translating', not a frozen 1/1
    assert txt_mod._text_progress_msg(0, 1) == "task.progress.translating"


def test_text_progress_msg_multi_chunk_uses_segment_index():
    assert txt_mod._text_progress_msg(0, 3) == "task.progress.translating_segment|1|3"
    assert txt_mod._text_progress_msg(2, 3) == "task.progress.translating_segment|3|3"


def test_translate_text_local_single_chunk_no_frozen_numerator():
    """Regression: a single-chunk local translation must not emit a frozen
    'translating_segment|1|1' (numerator stuck at 1 while the bar advances)."""
    session = MagicMock()
    session.chat = MagicMock(return_value="out")
    fake_builder = lambda *a, **k: {"mode": "chat", "messages": []}

    events = []
    def on_progress(p, m): events.append((p, m))

    with patch("app.adapters.ai.inference_config.get_inference_config", return_value=_FAKE_CONFIG), \
         patch("app.utils.prompts.get_prompt_builder", return_value=fake_builder), \
         patch("app.utils.text_chunking.split_text", return_value=["only-chunk"]), \
         patch("app.utils.inference.fake_progress", _noop_fake_progress), \
         patch("app.utils.inference.calc_max_tokens", return_value=512), \
         patch("app.utils.inference.estimate_tokens", return_value=10):
        txt_mod.translate_text_local(
            "in", "en", "zh-TW", session, max_chars=5000,
            on_progress=on_progress,
        )
    msgs = [m for _, m in events]
    assert "task.progress.translating_segment|1|1" not in msgs
    assert any(m == "task.progress.translating" for m in msgs)
