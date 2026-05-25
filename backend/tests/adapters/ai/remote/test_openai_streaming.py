"""OpenAIProvider streaming (SSE) tests — Chat Completions + Responses API.

Spec §4.2.2.
"""
import json
from unittest.mock import MagicMock, patch

import pytest


def _make_sse_response(*lines: bytes):
    """Build a MagicMock HTTPResponse from a sequence of SSE byte lines."""
    resp = MagicMock(name="HTTPResponse")
    resp.__iter__ = lambda self: iter([l for l in lines])
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    resp.close = MagicMock()
    return resp


# --- Chat Completions SSE ---

def test_chat_completions_streaming_parses_data_lines():
    from app.adapters.ai.remote.openai import OpenAIProvider

    lines = [
        b'data: {"choices":[{"delta":{"content":"Hello"}}]}\n',
        b'data: {"choices":[{"delta":{"content":" world"}}]}\n',
        b'data: [DONE]\n',
    ]
    resp = _make_sse_response(*lines)

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["data"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return resp

    prov = OpenAIProvider("https://api.openai.com", "sk-test")
    with patch(
        "app.adapters.ai.remote.openai.urllib.request.urlopen",
        side_effect=fake_urlopen,
    ):
        result = prov.chat(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=100, temperature=0.2,
            abort_hook=lambda r: None,
        )
    assert result == "Hello world"
    assert captured["data"]["stream"] is True
    assert captured["data"]["max_tokens"] == 100  # legacy param for gpt-4o-mini
    assert captured["timeout"] == 30


def test_chat_completions_streaming_uses_max_completion_tokens_for_new_models():
    """gpt-5+, o1+, o3+, o4+ use max_completion_tokens kwarg."""
    from app.adapters.ai.remote.openai import OpenAIProvider

    lines = [b'data: [DONE]\n']
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["data"] = json.loads(req.data.decode("utf-8"))
        return _make_sse_response(*lines)

    prov = OpenAIProvider("https://api.openai.com", "sk-test")
    with patch(
        "app.adapters.ai.remote.openai.urllib.request.urlopen",
        side_effect=fake_urlopen,
    ):
        prov.chat(
            model="gpt-5-mini",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=50, temperature=0.1,
            abort_hook=lambda r: None,
        )
    assert captured["data"].get("max_completion_tokens") == 50
    assert "max_tokens" not in captured["data"]


def test_chat_completions_streaming_skips_unknown_lines():
    from app.adapters.ai.remote.openai import OpenAIProvider

    lines = [
        b': keepalive comment\n',
        b'event: ping\n',
        b'\n',
        b'data: {"choices":[{"delta":{"content":"X"}}]}\n',
        b'data: not-json\n',
        b'data: [DONE]\n',
    ]
    with patch(
        "app.adapters.ai.remote.openai.urllib.request.urlopen",
        return_value=_make_sse_response(*lines),
    ):
        prov = OpenAIProvider("https://api.openai.com", "sk-test")
        result = prov.chat(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "x"}],
            max_tokens=10, temperature=0.1,
            abort_hook=lambda r: None,
        )
    assert result == "X"


# --- Responses API SSE ---

def test_responses_streaming_parses_output_text_delta():
    from app.adapters.ai.remote.openai import OpenAIProvider

    lines = [
        b'event: response.created\n',
        b'data: {"response":{"id":"resp_1"}}\n',
        b'\n',
        b'event: response.output_text.delta\n',
        b'data: {"delta":"Hello"}\n',
        b'\n',
        b'event: response.output_text.delta\n',
        b'data: {"delta":" world"}\n',
        b'\n',
        b'event: response.completed\n',
        b'data: {"response":{"id":"resp_1"}}\n',
        b'\n',
    ]
    with patch(
        "app.adapters.ai.remote.openai.urllib.request.urlopen",
        return_value=_make_sse_response(*lines),
    ):
        prov = OpenAIProvider("https://api.openai.com", "sk-test")
        result = prov.chat(
            model="o4-mini",
            messages=[{"role": "user", "content": "x"}],
            max_tokens=100, temperature=0.0,
            abort_hook=lambda r: None,
        )
    assert result == "Hello world"


def test_responses_streaming_raises_on_refusal():
    from app.adapters.ai.remote.openai import OpenAIProvider
    from app.handler.exceptions import RemoteApiError

    lines = [
        b'event: response.refusal.delta\n',
        b'data: {"delta":"Cannot help with that"}\n',
        b'\n',
        b'event: response.completed\n',
        b'data: {}\n',
    ]
    with patch(
        "app.adapters.ai.remote.openai.urllib.request.urlopen",
        return_value=_make_sse_response(*lines),
    ):
        prov = OpenAIProvider("https://api.openai.com", "sk-test")
        with pytest.raises(RemoteApiError) as exc_info:
            prov.chat(
                model="o4-mini",
                messages=[{"role": "user", "content": "harmful"}],
                max_tokens=100, temperature=0.0,
                abort_hook=lambda r: None,
            )
    assert exc_info.value.code == "refused"


def test_responses_streaming_raises_on_response_failed():
    from app.adapters.ai.remote.openai import OpenAIProvider
    from app.handler.exceptions import RemoteApiError

    lines = [
        b'event: response.failed\n',
        b'data: {"response":{"error":{"message":"rate_limit"}}}\n',
    ]
    with patch(
        "app.adapters.ai.remote.openai.urllib.request.urlopen",
        return_value=_make_sse_response(*lines),
    ):
        prov = OpenAIProvider("https://api.openai.com", "sk-test")
        with pytest.raises(RemoteApiError) as exc_info:
            prov.chat(
                model="o4-mini",
                messages=[{"role": "user", "content": "x"}],
                max_tokens=10, temperature=0.0,
                abort_hook=lambda r: None,
            )
    assert "rate_limit" in str(exc_info.value)


def test_responses_streaming_raises_on_error_event_literal():
    """Stream control 'error' event (literal string, NO 'response.' prefix)."""
    from app.adapters.ai.remote.openai import OpenAIProvider
    from app.handler.exceptions import RemoteApiError

    lines = [
        b'event: error\n',
        b'data: {"message":"server_overloaded"}\n',
    ]
    with patch(
        "app.adapters.ai.remote.openai.urllib.request.urlopen",
        return_value=_make_sse_response(*lines),
    ):
        prov = OpenAIProvider("https://api.openai.com", "sk-test")
        with pytest.raises(RemoteApiError) as exc_info:
            prov.chat(
                model="o4-mini",
                messages=[{"role": "user", "content": "x"}],
                max_tokens=10, temperature=0.0,
                abort_hook=lambda r: None,
            )
    assert "server_overloaded" in str(exc_info.value)


def test_responses_streaming_ignores_unknown_events():
    """response.output_item.added, response.reasoning.* etc. — silent skip."""
    from app.adapters.ai.remote.openai import OpenAIProvider

    lines = [
        b'event: response.output_item.added\n',
        b'data: {"index":0}\n',
        b'\n',
        b'event: response.reasoning.summary_text.delta\n',
        b'data: {"delta":"thinking"}\n',
        b'\n',
        b'event: some.future.event\n',
        b'data: {"x":1}\n',
        b'\n',
        b'event: response.output_text.delta\n',
        b'data: {"delta":"Real"}\n',
        b'\n',
        b'event: response.completed\n',
        b'data: {}\n',
    ]
    with patch(
        "app.adapters.ai.remote.openai.urllib.request.urlopen",
        return_value=_make_sse_response(*lines),
    ):
        prov = OpenAIProvider("https://api.openai.com", "sk-test")
        result = prov.chat(
            model="o4-mini",
            messages=[{"role": "user", "content": "x"}],
            max_tokens=10, temperature=0.0,
            abort_hook=lambda r: None,
        )
    assert result == "Real"


# --- Blocking-path regression (abort_hook=None) ---

def test_chat_completions_blocking_no_regression():
    """abort_hook is None must NOT set stream:true."""
    from app.adapters.ai.remote.openai import OpenAIProvider

    body = json.dumps({"choices": [{"message": {"content": "OK"}}]}).encode("utf-8")
    resp = MagicMock(name="HTTPResponse")
    resp.read = MagicMock(return_value=body)
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["data"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return resp

    prov = OpenAIProvider("https://api.openai.com", "sk-test")
    with patch(
        "app.adapters.ai.remote.openai.urllib.request.urlopen",
        side_effect=fake_urlopen,
    ):
        result = prov.chat(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=100, temperature=0.2,
        )
    assert result == "OK"
    assert "stream" not in captured["data"] or captured["data"]["stream"] is False
    assert captured["timeout"] == 300


def test_responses_blocking_no_regression():
    """gpt-5-pro / o4-mini in blocking mode hits Responses API correctly."""
    from app.adapters.ai.remote.openai import OpenAIProvider

    body = json.dumps({
        "output": [
            {"type": "message", "content": [
                {"type": "output_text", "text": "Reasoned answer"}
            ]}
        ]
    }).encode("utf-8")
    resp = MagicMock(name="HTTPResponse")
    resp.read = MagicMock(return_value=body)
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["data"] = json.loads(req.data.decode("utf-8"))
        return resp

    prov = OpenAIProvider("https://api.openai.com", "sk-test")
    with patch(
        "app.adapters.ai.remote.openai.urllib.request.urlopen",
        side_effect=fake_urlopen,
    ):
        result = prov.chat(
            model="o4-mini",
            messages=[{"role": "user", "content": "x"}],
            max_tokens=100, temperature=0.0,
        )
    assert result == "Reasoned answer"
    assert "/v1/responses" in captured["url"]
    assert "max_output_tokens" in captured["data"]
