"""GeminiProvider streaming (SSE via streamGenerateContent?alt=sse) tests.

Spec §4.3.1.
"""
import json
from unittest.mock import MagicMock, patch

import pytest


def _make_sse_response(*lines: bytes):
    resp = MagicMock(name="HTTPResponse")
    resp.__iter__ = lambda self: iter([l for l in lines])
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    resp.close = MagicMock()
    return resp


def test_streaming_parses_sse_data_lines():
    from app.adapters.ai.remote.gemini import GeminiProvider

    lines = [
        b'data: {"candidates":[{"content":{"parts":[{"text":"Hello"}]}}]}\n',
        b'data: {"candidates":[{"content":{"parts":[{"text":" world"}]}}]}\n',
    ]
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["data"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _make_sse_response(*lines)

    with patch(
        "app.adapters.ai.remote.gemini.urllib.request.urlopen",
        side_effect=fake_urlopen,
    ):
        prov = GeminiProvider(
            "https://generativelanguage.googleapis.com", "AIza-test",
        )
        result = prov.chat(
            model="gemini-2.5-flash",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=100, temperature=0.0,
            abort_hook=lambda r: None,
        )
    assert result == "Hello world"
    assert captured["timeout"] == 180
    assert "alt=sse" in captured["url"]
    assert "streamGenerateContent" in captured["url"]
    assert ":streamGenerateContent" in captured["url"]


def test_streaming_url_strips_models_prefix():
    """list_models returns 'gemini-2.5-flash' already-stripped; caller passes that."""
    from app.adapters.ai.remote.gemini import GeminiProvider

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        return _make_sse_response()

    with patch(
        "app.adapters.ai.remote.gemini.urllib.request.urlopen",
        side_effect=fake_urlopen,
    ):
        prov = GeminiProvider(
            "https://generativelanguage.googleapis.com", "AIza-test",
        )
        prov.chat(
            model="gemini-2.5-flash",
            messages=[{"role": "user", "content": "x"}],
            max_tokens=10, temperature=0.0,
            abort_hook=lambda r: None,
        )
    assert "/v1beta/models/gemini-2.5-flash:streamGenerateContent" in captured["url"]


def test_streaming_handles_multi_part_per_candidate():
    """One candidate can have multiple parts in one chunk."""
    from app.adapters.ai.remote.gemini import GeminiProvider

    lines = [
        b'data: {"candidates":[{"content":{"parts":[{"text":"A"},{"text":"B"}]}}]}\n',
    ]
    with patch(
        "app.adapters.ai.remote.gemini.urllib.request.urlopen",
        return_value=_make_sse_response(*lines),
    ):
        prov = GeminiProvider(
            "https://generativelanguage.googleapis.com", "AIza-test",
        )
        result = prov.chat(
            model="gemini-2.5-flash",
            messages=[{"role": "user", "content": "x"}],
            max_tokens=10, temperature=0.0,
            abort_hook=lambda r: None,
        )
    assert result == "AB"


def test_streaming_raises_on_safety_finish_reason():
    from app.adapters.ai.remote.gemini import GeminiProvider
    from app.handler.exceptions import RemoteApiError

    lines = [
        b'data: {"candidates":[{"content":{"parts":[{"text":"start"}]},"finishReason":"SAFETY"}]}\n',
    ]
    with patch(
        "app.adapters.ai.remote.gemini.urllib.request.urlopen",
        return_value=_make_sse_response(*lines),
    ):
        prov = GeminiProvider(
            "https://generativelanguage.googleapis.com", "AIza-test",
        )
        with pytest.raises(RemoteApiError) as exc_info:
            prov.chat(
                model="gemini-2.5-flash",
                messages=[{"role": "user", "content": "x"}],
                max_tokens=10, temperature=0.0,
                abort_hook=lambda r: None,
            )
    assert exc_info.value.code == "safety_blocked"


@pytest.mark.parametrize("reason", ["RECITATION", "BLOCKLIST", "PROHIBITED_CONTENT",
                                     "SPII", "IMAGE_SAFETY", "OTHER"])
def test_streaming_raises_on_other_safety_reasons(reason):
    from app.adapters.ai.remote.gemini import GeminiProvider
    from app.handler.exceptions import RemoteApiError

    lines = [
        f'data: {{"candidates":[{{"finishReason":"{reason}"}}]}}\n'.encode(),
    ]
    with patch(
        "app.adapters.ai.remote.gemini.urllib.request.urlopen",
        return_value=_make_sse_response(*lines),
    ):
        prov = GeminiProvider(
            "https://generativelanguage.googleapis.com", "AIza-test",
        )
        with pytest.raises(RemoteApiError):
            prov.chat(
                model="gemini-2.5-flash",
                messages=[{"role": "user", "content": "x"}],
                max_tokens=10, temperature=0.0,
                abort_hook=lambda r: None,
            )


def test_streaming_handles_eof_without_done_marker():
    """Gemini has no [DONE] sentinel — stream ends with EOF."""
    from app.adapters.ai.remote.gemini import GeminiProvider

    lines = [
        b'data: {"candidates":[{"content":{"parts":[{"text":"Hi"}]}}]}\n',
        # No terminal marker; stream just ends
    ]
    with patch(
        "app.adapters.ai.remote.gemini.urllib.request.urlopen",
        return_value=_make_sse_response(*lines),
    ):
        prov = GeminiProvider(
            "https://generativelanguage.googleapis.com", "AIza-test",
        )
        result = prov.chat(
            model="gemini-2.5-flash",
            messages=[{"role": "user", "content": "x"}],
            max_tokens=10, temperature=0.0,
            abort_hook=lambda r: None,
        )
    assert result == "Hi"


# --- Blocking-path regression ---

def test_blocking_no_regression():
    """abort_hook=None hits non-streaming generateContent."""
    from app.adapters.ai.remote.gemini import GeminiProvider

    body = json.dumps({
        "candidates": [{"content": {"parts": [{"text": "OK"}]}}]
    }).encode("utf-8")
    resp = MagicMock(name="HTTPResponse")
    resp.read = MagicMock(return_value=body)
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["timeout"] = timeout
        return resp

    with patch(
        "app.adapters.ai.remote.gemini.urllib.request.urlopen",
        side_effect=fake_urlopen,
    ):
        prov = GeminiProvider(
            "https://generativelanguage.googleapis.com", "AIza-test",
        )
        result = prov.chat(
            model="gemini-2.5-flash",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=100, temperature=0.0,
        )
    assert result == "OK"
    assert ":generateContent" in captured["url"]
    assert "streamGenerateContent" not in captured["url"]
    assert captured["timeout"] == 300


# --- task hint: thinkingConfig ---

def test_streaming_thinking_budget_zero_when_task_is_frame_select():
    """task='frame_select' must set generationConfig.thinkingConfig.thinkingBudget=0."""
    from app.adapters.ai.remote.gemini import GeminiProvider

    lines = [
        b'data: {"candidates":[{"content":{"parts":[{"text":"2"}]}}]}\n',
    ]
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["data"] = json.loads(req.data.decode("utf-8"))
        return _make_sse_response(*lines)

    with patch(
        "app.adapters.ai.remote.gemini.urllib.request.urlopen",
        side_effect=fake_urlopen,
    ):
        prov = GeminiProvider(
            "https://generativelanguage.googleapis.com", "AIza-test",
        )
        prov.chat(
            model="gemini-2.5-flash",
            messages=[{"role": "user", "content": "pick a frame"}],
            max_tokens=16, temperature=0.0,
            abort_hook=lambda r: None,
            task="frame_select",
        )
    gen_cfg = captured["data"]["generationConfig"]
    assert "thinkingConfig" in gen_cfg, "thinkingConfig missing when task=frame_select"
    assert gen_cfg["thinkingConfig"] == {"thinkingBudget": 0}


def test_streaming_no_thinking_config_without_task_hint():
    """No task hint must NOT add thinkingConfig to generationConfig."""
    from app.adapters.ai.remote.gemini import GeminiProvider

    lines = [
        b'data: {"candidates":[{"content":{"parts":[{"text":"hi"}]}}]}\n',
    ]
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["data"] = json.loads(req.data.decode("utf-8"))
        return _make_sse_response(*lines)

    with patch(
        "app.adapters.ai.remote.gemini.urllib.request.urlopen",
        side_effect=fake_urlopen,
    ):
        prov = GeminiProvider(
            "https://generativelanguage.googleapis.com", "AIza-test",
        )
        prov.chat(
            model="gemini-2.5-flash",
            messages=[{"role": "user", "content": "summarize"}],
            max_tokens=4096, temperature=0.3,
            abort_hook=lambda r: None,
            # task=None (default)
        )
    gen_cfg = captured["data"]["generationConfig"]
    assert "thinkingConfig" not in gen_cfg, "thinkingConfig must not appear when task=None"


def test_blocking_thinking_budget_zero_when_task_is_frame_select():
    """Blocking path also sends thinkingConfig.thinkingBudget=0 for frame_select."""
    from app.adapters.ai.remote.gemini import GeminiProvider

    body = json.dumps({
        "candidates": [{"content": {"parts": [{"text": "1"}]}}]
    }).encode("utf-8")
    resp = MagicMock(name="HTTPResponse")
    resp.read = MagicMock(return_value=body)
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["data"] = json.loads(req.data.decode("utf-8"))
        return resp

    with patch(
        "app.adapters.ai.remote.gemini.urllib.request.urlopen",
        side_effect=fake_urlopen,
    ):
        prov = GeminiProvider(
            "https://generativelanguage.googleapis.com", "AIza-test",
        )
        prov.chat(
            model="gemini-2.5-flash",
            messages=[{"role": "user", "content": "pick"}],
            max_tokens=16, temperature=0.0,
            task="frame_select",  # no abort_hook → blocking path
        )
    gen_cfg = captured["data"]["generationConfig"]
    assert gen_cfg["thinkingConfig"] == {"thinkingBudget": 0}
