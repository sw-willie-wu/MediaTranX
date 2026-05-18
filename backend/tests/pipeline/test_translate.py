"""Unit tests for app.pipeline.translate — SRT batch translation orchestration."""
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import pytest

from app.pipeline import translate as tr


_FAKE_CONFIG = {
    "n_ctx": 4096,
    "temperature": 0.1,
    "top_k": 40,
    "top_p": 0.9,
    "prompt_builder": "default",
    "thinking": False,
    "max_tokens_strategy": "fixed",
    "max_tokens": 2048,
    "max_srt_batch": 0,
}

_FAKE_REMOTE_CONFIG = {
    "temperature": 0.2,
    "max_tokens": 4096,
}


@contextmanager
def _noop_fake_progress(*args, **kwargs):
    yield


def _segs(n: int) -> list[dict]:
    return [{"start": float(i), "end": float(i + 1), "text": f"line {i}"} for i in range(n)]


# --- _calc_srt_batch_size ---

def test_calc_srt_batch_size_empty_returns_one():
    assert tr._calc_srt_batch_size(4096, []) == 1


def test_calc_srt_batch_size_caps_at_segment_count():
    """Very large n_ctx must not return batch_size > len(seg_dicts)."""
    result = tr._calc_srt_batch_size(1_000_000, _segs(3))
    assert result == 3


def test_calc_srt_batch_size_respects_max_batch_limit():
    """max_batch=5 must clamp batch size regardless of n_ctx."""
    result = tr._calc_srt_batch_size(1_000_000, _segs(50), max_batch=5)
    assert result == 5


# --- get_cloud_ctx ---

def test_get_cloud_ctx_ollama_queries_provider():
    """Ollama path must call prov.get_model_ctx(model)."""
    class OllamaProvider:
        pass
    prov = OllamaProvider()
    prov.get_model_ctx = MagicMock(return_value=32768)
    assert tr.get_cloud_ctx(prov, "qwen2") == 32768
    prov.get_model_ctx.assert_called_once_with("qwen2")


def test_get_cloud_ctx_ollama_falls_back_on_query_failure():
    class OllamaProvider:
        pass
    prov = OllamaProvider()
    prov.get_model_ctx = MagicMock(side_effect=RuntimeError("api down"))
    assert tr.get_cloud_ctx(prov, "qwen2") == 8192


def test_get_cloud_ctx_unknown_provider_uses_default():
    class OpenAIProvider:
        pass
    assert tr.get_cloud_ctx(OpenAIProvider()) == 128000


# --- translate_srt_cloud ---

def test_translate_srt_cloud_batches_and_calls_provider():
    """All segments must flow through prov.chat."""
    class OpenAIProvider:
        pass
    prov = OpenAIProvider()
    prov.chat = MagicMock(return_value="dummy-srt")
    segs = _segs(2)

    with patch("app.adapters.ai.inference_config.get_remote_inference_config", return_value=_FAKE_REMOTE_CONFIG), \
         patch("app.utils.prompts.build_srt_translate_prompt", return_value="prompt-x"), \
         patch("app.utils.subtitles.segments_to_srt", return_value="srt-x"), \
         patch("app.utils.subtitles.parse_srt_response", return_value=[{"start": 0, "end": 1, "text": "翻譯"}]):
        result = tr.translate_srt_cloud(
            segs, source_lang="en", target_lang="zh-TW",
            prov=prov, model="gpt-4o", batch_size=2,
        )
    assert len(result) == 1
    prov.chat.assert_called_once()
    assert prov.chat.call_args.kwargs["model"] == "gpt-4o"
    assert prov.chat.call_args.kwargs["temperature"] == 0.2


def test_translate_srt_cloud_emits_progress():
    class OpenAIProvider:
        pass
    prov = OpenAIProvider()
    prov.chat = MagicMock(return_value="dummy")
    events = []
    def on_progress(p, m): events.append((p, m))

    with patch("app.adapters.ai.inference_config.get_remote_inference_config", return_value=_FAKE_REMOTE_CONFIG), \
         patch("app.utils.prompts.build_srt_translate_prompt", return_value="x"), \
         patch("app.utils.subtitles.segments_to_srt", return_value="x"), \
         patch("app.utils.subtitles.parse_srt_response", return_value=[]):
        tr.translate_srt_cloud(
            _segs(4), source_lang="en", target_lang="zh-TW",
            prov=prov, model="m", batch_size=2,
            on_progress=on_progress,
        )
    msgs = [m for _, m in events]
    assert any(m.startswith("task.progress.translating_segment") for m in msgs)
    assert any(m.startswith("task.progress.translated_segment") for m in msgs)


# --- translate_srt_local ---

def test_translate_srt_local_uses_session_chat_when_mode_is_chat():
    session = MagicMock()
    session.chat = MagicMock(return_value="srt-out")
    session.complete = MagicMock()

    fake_builder = lambda *a, **k: {"mode": "chat", "messages": [{"role": "user", "content": "x"}]}

    with patch("app.adapters.ai.inference_config.get_inference_config", return_value=_FAKE_CONFIG), \
         patch("app.utils.prompts.get_prompt_builder", return_value=fake_builder), \
         patch("app.utils.subtitles.segments_to_srt", return_value="srt-in"), \
         patch("app.utils.subtitles.parse_srt_response", return_value=[]), \
         patch("app.utils.inference.fake_progress", _noop_fake_progress), \
         patch("app.utils.inference.calc_max_tokens", return_value=512), \
         patch("app.utils.inference.estimate_tokens", return_value=100):
        tr.translate_srt_local(
            _segs(2), "en", "zh-TW", session, batch_size=2,
        )
    session.chat.assert_called_once()
    session.complete.assert_not_called()


def test_translate_srt_local_uses_session_complete_when_mode_is_complete():
    session = MagicMock()
    session.chat = MagicMock()
    session.complete = MagicMock(return_value="srt-out")

    fake_builder = lambda *a, **k: {"mode": "complete", "prompt": "translate this"}

    with patch("app.adapters.ai.inference_config.get_inference_config", return_value=_FAKE_CONFIG), \
         patch("app.utils.prompts.get_prompt_builder", return_value=fake_builder), \
         patch("app.utils.subtitles.segments_to_srt", return_value="srt-in"), \
         patch("app.utils.subtitles.parse_srt_response", return_value=[]), \
         patch("app.utils.inference.fake_progress", _noop_fake_progress), \
         patch("app.utils.inference.calc_max_tokens", return_value=512), \
         patch("app.utils.inference.estimate_tokens", return_value=100):
        tr.translate_srt_local(
            _segs(1), "en", "zh-TW", session, batch_size=1,
        )
    session.complete.assert_called_once()
    session.chat.assert_not_called()


# --- translate_srt_auto ---

def test_translate_srt_auto_dispatches_to_cloud_when_prov_set():
    class OpenAIProvider:
        pass
    prov = OpenAIProvider()
    prov.chat = MagicMock(return_value="x")
    with patch("app.adapters.ai.inference_config.get_remote_inference_config", return_value=_FAKE_REMOTE_CONFIG), \
         patch("app.utils.prompts.build_srt_translate_prompt", return_value="p"), \
         patch("app.utils.subtitles.segments_to_srt", return_value="srt"), \
         patch("app.utils.subtitles.parse_srt_response", return_value=[]):
        tr.translate_srt_auto(
            _segs(1), "en", "zh-TW", prov=prov, remote_model="gpt-4o",
        )
    prov.chat.assert_called_once()


def test_translate_srt_auto_dispatches_to_local_when_session_set():
    session = MagicMock()
    session.chat = MagicMock(return_value="x")
    with patch("app.adapters.ai.inference_config.get_inference_config", return_value=_FAKE_CONFIG), \
         patch("app.utils.prompts.get_prompt_builder", return_value=lambda *a, **k: {"mode": "chat", "messages": []}), \
         patch("app.utils.subtitles.segments_to_srt", return_value="srt"), \
         patch("app.utils.subtitles.parse_srt_response", return_value=[]), \
         patch("app.utils.inference.fake_progress", _noop_fake_progress), \
         patch("app.utils.inference.calc_max_tokens", return_value=128), \
         patch("app.utils.inference.estimate_tokens", return_value=10):
        tr.translate_srt_auto(
            _segs(1), "en", "zh-TW", session=session,
        )
    session.chat.assert_called_once()


def test_translate_srt_auto_raises_when_neither_provided():
    with pytest.raises(ValueError, match="prov.*session"):
        tr.translate_srt_auto(_segs(1), "en", "zh-TW")
