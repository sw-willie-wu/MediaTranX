"""Unit tests for app.adapters.ai.remote.openai."""
import json
from unittest.mock import patch

import pytest

from app.adapters.ai.remote import openai as openai_mod
from app.adapters.ai.remote.openai import OpenAIProvider, get_openai_provider
from app.handler.exceptions import RemoteApiError

from .conftest import make_response, make_http_error, make_url_error


PATCH_TARGET = "app.adapters.ai.remote.openai.urllib.request.urlopen"


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Singleton _openai leaks between tests if we don't reset it."""
    openai_mod._openai = None
    yield
    openai_mod._openai = None


# ─── connect ───

def test_connect_returns_true_on_success():
    prov = OpenAIProvider(api_key="sk-test")
    with patch(PATCH_TARGET, return_value=make_response({"data": [{"id": "gpt-4o"}]})):
        assert prov.connect() is True


def test_connect_returns_false_on_auth_failure():
    prov = OpenAIProvider(api_key="bad")
    with patch(PATCH_TARGET, side_effect=make_http_error(401, "Unauthorized")):
        assert prov.connect() is False


def test_connect_returns_false_on_network_error():
    prov = OpenAIProvider(api_key="sk-test")
    with patch(PATCH_TARGET, side_effect=make_url_error("DNS failure")):
        assert prov.connect() is False


def test_connect_sets_authorization_header():
    """Captured request must include Bearer token when api_key is set."""
    prov = OpenAIProvider(api_key="sk-token-123")
    captured = []
    def _side_effect(req, timeout=None):
        captured.append(req)
        return make_response({"data": []})
    with patch(PATCH_TARGET, side_effect=_side_effect):
        prov.connect()
    assert captured[0].get_header("Authorization") == "Bearer sk-token-123"


# ─── list_models ───

def test_list_models_dedup_by_family_key():
    """Multiple gpt-4o variants must collapse to a single base entry."""
    prov = OpenAIProvider(api_key="sk-test")
    payload = {"data": [
        {"id": "gpt-4o-2024-11-20", "owned_by": "openai"},
        {"id": "gpt-4o-2024-05-13", "owned_by": "openai"},
        {"id": "gpt-4o", "owned_by": "openai"},
        {"id": "gpt-3.5-turbo-0125", "owned_by": "openai"},
    ]}
    with patch(PATCH_TARGET, return_value=make_response(payload)):
        models = prov.list_models()
    ids = [m.id for m in models]
    assert "gpt-4o" in ids  # base preferred
    assert "gpt-4o-2024-11-20" not in ids  # dated dropped
    assert any(m.id.startswith("gpt-3.5-turbo") for m in models)


def test_list_models_filters_hidden_models():
    """tts-1, whisper-1, dall-e-* must be filtered out."""
    prov = OpenAIProvider(api_key="sk-test")
    payload = {"data": [
        {"id": "tts-1", "owned_by": "openai"},
        {"id": "whisper-1", "owned_by": "openai"},
        {"id": "dall-e-3", "owned_by": "openai"},
        {"id": "gpt-4o", "owned_by": "openai"},
    ]}
    with patch(PATCH_TARGET, return_value=make_response(payload)):
        models = prov.list_models()
    ids = [m.id for m in models]
    assert "tts-1" not in ids
    assert "whisper-1" not in ids
    assert "dall-e-3" not in ids
    assert "gpt-4o" in ids


def test_list_models_filters_preview_keyword():
    """Any *-preview, *-transcribe, *-tts variants must be filtered."""
    prov = OpenAIProvider(api_key="sk-test")
    payload = {"data": [
        {"id": "gpt-4-vision-preview", "owned_by": "openai"},
        {"id": "gpt-4o-transcribe", "owned_by": "openai"},
        {"id": "gpt-4o", "owned_by": "openai"},
    ]}
    with patch(PATCH_TARGET, return_value=make_response(payload)):
        models = prov.list_models()
    ids = [m.id for m in models]
    assert "gpt-4-vision-preview" not in ids
    assert "gpt-4o-transcribe" not in ids
    assert "gpt-4o" in ids


def test_list_models_returns_empty_on_http_error():
    prov = OpenAIProvider(api_key="sk-test")
    with patch(PATCH_TARGET, side_effect=make_http_error(500, "Server Error")):
        assert prov.list_models() == []


def test_list_models_returns_empty_on_json_decode_error():
    prov = OpenAIProvider(api_key="sk-test")
    with patch(PATCH_TARGET, return_value=make_response(b"not-json")):
        assert prov.list_models() == []


def test_list_models_detects_capabilities():
    """gpt-4o → vision; gpt-3.5-turbo → text only."""
    prov = OpenAIProvider(api_key="sk-test")
    payload = {"data": [
        {"id": "gpt-4o", "owned_by": "openai"},
        {"id": "gpt-3.5-turbo", "owned_by": "openai"},
    ]}
    with patch(PATCH_TARGET, return_value=make_response(payload)):
        models = {m.id: m for m in prov.list_models()}
    assert "vision" in models["gpt-4o"].capabilities
    assert "vision" not in models["gpt-3.5-turbo"].capabilities


# ─── chat (completions path) ───

def test_chat_completions_returns_response_text():
    prov = OpenAIProvider(api_key="sk-test")
    payload = {"choices": [{"message": {"content": "  hello world  "}}]}
    with patch(PATCH_TARGET, return_value=make_response(payload)):
        result = prov.chat(model="gpt-4o", messages=[{"role": "user", "content": "hi"}])
    assert result == "hello world"


def test_chat_completions_uses_max_tokens_for_older_models():
    """Older models (gpt-4o, gpt-3.5) use 'max_tokens' key."""
    prov = OpenAIProvider(api_key="sk-test")
    captured = []
    def _side_effect(req, timeout=None):
        captured.append(json.loads(req.data.decode("utf-8")))
        return make_response({"choices": [{"message": {"content": "x"}}]})
    with patch(PATCH_TARGET, side_effect=_side_effect):
        prov.chat(model="gpt-4o", messages=[{"role": "user", "content": "x"}], max_tokens=500)
    assert "max_tokens" in captured[0]
    assert captured[0]["max_tokens"] == 500


def test_chat_completions_uses_max_completion_tokens_for_gpt5():
    """GPT-5+ models use 'max_completion_tokens' key."""
    prov = OpenAIProvider(api_key="sk-test")
    captured = []
    def _side_effect(req, timeout=None):
        captured.append(json.loads(req.data.decode("utf-8")))
        return make_response({"choices": [{"message": {"content": "x"}}]})
    with patch(PATCH_TARGET, side_effect=_side_effect):
        prov.chat(model="gpt-5", messages=[{"role": "user", "content": "x"}], max_tokens=500)
    assert "max_completion_tokens" in captured[0]
    assert "max_tokens" not in captured[0]


# ─── chat (responses path) ───

def test_chat_dispatches_to_responses_api_for_o1_model():
    """o1 / o3 / o4 / *-pro must use /v1/responses endpoint."""
    prov = OpenAIProvider(api_key="sk-test")
    captured = []
    def _side_effect(req, timeout=None):
        captured.append(req)
        return make_response({"output_text": "from-responses"})
    with patch(PATCH_TARGET, side_effect=_side_effect):
        result = prov.chat(model="o1", messages=[{"role": "user", "content": "hi"}])
    assert result == "from-responses"
    assert captured[0].full_url.endswith("/v1/responses")


def test_chat_responses_extracts_text_from_output_message_format():
    """Responses API returns nested output[].message.content[].output_text."""
    prov = OpenAIProvider(api_key="sk-test")
    payload = {"output": [
        {"type": "message", "content": [
            {"type": "output_text", "text": "  nested  "},
        ]},
    ]}
    with patch(PATCH_TARGET, return_value=make_response(payload)):
        result = prov.chat(model="o3", messages=[{"role": "user", "content": "x"}])
    assert result == "nested"


def test_chat_responses_converts_text_content_to_input_text():
    """String content must be wrapped as [{'type': 'input_text', 'text': ...}]."""
    prov = OpenAIProvider(api_key="sk-test")
    captured = []
    def _side_effect(req, timeout=None):
        captured.append(json.loads(req.data.decode("utf-8")))
        return make_response({"output_text": "x"})
    with patch(PATCH_TARGET, side_effect=_side_effect):
        prov.chat(model="o1", messages=[{"role": "user", "content": "plain text"}])
    msg = captured[0]["input"][0]
    assert msg["role"] == "user"
    assert msg["content"][0]["type"] == "input_text"
    assert msg["content"][0]["text"] == "plain text"


def test_chat_responses_converts_image_url_to_input_image():
    """List content with image_url part must become input_image."""
    prov = OpenAIProvider(api_key="sk-test")
    captured = []
    def _side_effect(req, timeout=None):
        captured.append(json.loads(req.data.decode("utf-8")))
        return make_response({"output_text": "x"})
    with patch(PATCH_TARGET, side_effect=_side_effect):
        prov.chat(
            model="o1",
            messages=[{"role": "user", "content": [
                {"type": "text", "text": "look"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,XYZ"}},
            ]}],
        )
    parts = captured[0]["input"][0]["content"]
    types = {p["type"] for p in parts}
    assert "input_text" in types
    assert "input_image" in types


# ─── error mapping ───

@pytest.mark.parametrize("status,body,expected_code", [
    (429, "quota exceeded", "quota_exceeded"),
    (401, "invalid key", "auth_failed"),
    (403, "forbidden", "auth_failed"),
    (404, "model gpt-x not found", "model_not_found"),
    (404, "not a chat model", "model_not_supported"),
    (400, "invalid max_tokens value", "invalid_params"),
    (400, "malformed request", "invalid_request"),
    (500, "internal error", "remote_error"),
])
def test_chat_completions_error_maps_to_remote_api_error(status, body, expected_code):
    prov = OpenAIProvider(api_key="sk-test")
    with patch(PATCH_TARGET, side_effect=make_http_error(status, body)):
        with pytest.raises(RemoteApiError) as exc_info:
            prov.chat(model="gpt-4o", messages=[{"role": "user", "content": "x"}])
    assert exc_info.value.code == expected_code


def test_chat_completions_body_keyword_precedes_non_429_status():
    """`_parse_error` checks body for 'quota'/'rate' keywords BEFORE status — a
    500 with 'quota' in body still maps to quota_exceeded. This is a real
    short-circuit branch worth pinning.
    """
    prov = OpenAIProvider(api_key="sk-test")
    with patch(PATCH_TARGET, side_effect=make_http_error(500, "Internal error: quota related")):
        with pytest.raises(RemoteApiError) as exc:
            prov.chat(model="gpt-4o", messages=[{"role": "user", "content": "x"}])
    assert exc.value.code == "quota_exceeded"


def test_chat_completions_network_error_maps_to_connection_failed():
    prov = OpenAIProvider(api_key="sk-test")
    with patch(PATCH_TARGET, side_effect=make_url_error("DNS down")):
        with pytest.raises(RemoteApiError) as exc_info:
            prov.chat(model="gpt-4o", messages=[{"role": "user", "content": "x"}])
    assert exc_info.value.code == "connection_failed"


# ─── helpers ───

@pytest.mark.parametrize("model,expected", [
    ("gpt-4o", False),
    ("gpt-5", False),
    ("o1", True),
    ("o1-mini", True),
    ("o3", True),
    ("o4-mini", True),
    ("gpt-5-pro", True),
    ("gpt-3.5-turbo", False),
])
def test_needs_responses_api(model, expected):
    assert OpenAIProvider._needs_responses_api(model) is expected


@pytest.mark.parametrize("model,expected", [
    ("gpt-4o", False),
    ("gpt-3.5-turbo", False),
    ("gpt-5", True),
    ("gpt-5-pro", True),
    ("o1", True),
    ("o3-mini", True),
    ("o4", True),
])
def test_is_new_model(model, expected):
    assert OpenAIProvider._is_new_model(model) is expected


@pytest.mark.parametrize("model_id,expected_caps_subset", [
    ("gpt-4o", {"text", "vision"}),
    ("gpt-4o-2024-11-20", {"text", "vision"}),  # prefix match
    ("text-embedding-3-small", {"embedding"}),
    ("unknown-model-xyz", {"text"}),  # default
    ("custom-embedding-1", {"embedding"}),  # keyword fallback
])
def test_detect_capabilities(model_id, expected_caps_subset):
    caps = set(OpenAIProvider._detect_capabilities(model_id))
    assert expected_caps_subset.issubset(caps)


@pytest.mark.parametrize("model_id,expected_family", [
    ("gpt-4o-2024-11-20", "gpt-4o"),
    ("gpt-3.5-turbo-0125", "gpt-3.5-turbo"),
    ("gpt-3.5-turbo-16k", "gpt-3.5-turbo"),
    ("o4-mini-2025-04-16", "o4-mini"),
    ("text-embedding-3-small", "text-embedding-3-small"),
])
def test_model_family_key(model_id, expected_family):
    assert OpenAIProvider._model_family_key(model_id) == expected_family


# ─── singleton factory ───

def test_get_openai_provider_returns_same_instance_for_same_args():
    p1 = get_openai_provider(api_key="sk-A")
    p2 = get_openai_provider(api_key="sk-A")
    assert p1 is p2


def test_get_openai_provider_returns_new_instance_when_key_changes():
    p1 = get_openai_provider(api_key="sk-A")
    p2 = get_openai_provider(api_key="sk-B")
    assert p1 is not p2


# ─── get_summary_chunking_hints ───

def test_get_summary_chunking_hints_returns_128k_24k():
    """OpenAI returns 128k/24k regardless of model name."""
    p = OpenAIProvider("https://api.openai.com", "sk-test")
    hints = p.get_summary_chunking_hints("gpt-4o-mini")
    assert hints == {"n_ctx": 128000, "model_cap": 24000}


def test_get_summary_chunking_hints_consistent_across_models():
    """Same hints returned for o4-mini and gpt-5 (all >= 128k)."""
    p = OpenAIProvider("https://api.openai.com", "sk-test")
    assert p.get_summary_chunking_hints("o4-mini") == {"n_ctx": 128000, "model_cap": 24000}
    assert p.get_summary_chunking_hints("gpt-5") == {"n_ctx": 128000, "model_cap": 24000}
