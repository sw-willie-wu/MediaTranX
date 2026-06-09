"""Unit tests for app.adapters.ai.remote.gemini."""
import json
from unittest.mock import patch

import pytest

from app.adapters.ai.remote import gemini as gemini_mod
from app.adapters.ai.remote.gemini import GeminiProvider, get_gemini_provider
from app.handler.exceptions import RemoteApiError

from .conftest import make_response, make_http_error, make_url_error


PATCH_TARGET = "app.adapters.ai.remote._http.urlopen"


@pytest.fixture(autouse=True)
def _reset_singleton():
    gemini_mod._gemini = None
    yield
    gemini_mod._gemini = None


# ─── connect ───

def test_connect_returns_true_on_success():
    prov = GeminiProvider(api_key="g-key")
    with patch(PATCH_TARGET, return_value=make_response({"models": [{"name": "models/gemini-2.0-flash"}]})):
        assert prov.connect() is True


def test_connect_appends_api_key_as_query_param():
    """Gemini auth uses `?key=` query param, not Authorization header."""
    prov = GeminiProvider(api_key="g-secret-123")
    captured = []
    def _side_effect(req, timeout=None):
        captured.append(req)
        return make_response({"models": []})
    with patch(PATCH_TARGET, side_effect=_side_effect):
        prov.connect()
    assert "key=g-secret-123" in captured[0].full_url


def test_connect_returns_false_on_403():
    prov = GeminiProvider(api_key="bad")
    with patch(PATCH_TARGET, side_effect=make_http_error(403, "Forbidden")):
        assert prov.connect() is False


def test_connect_returns_false_on_network_error():
    prov = GeminiProvider(api_key="g-key")
    with patch(PATCH_TARGET, side_effect=make_url_error("DNS down")):
        assert prov.connect() is False


# ─── list_models (with pagination) ───

def test_list_models_fetches_all_pages():
    """Gemini returns nextPageToken; list_models must follow until exhausted."""
    prov = GeminiProvider(api_key="g-key")
    pages = [
        {"models": [{"name": "models/gemini-2.0-flash", "supportedGenerationMethods": ["generateContent"]}],
         "nextPageToken": "tok-2"},
        {"models": [{"name": "models/gemini-2.5-pro", "supportedGenerationMethods": ["generateContent"]}]},
    ]
    page_iter = iter(pages)
    def _side_effect(req, timeout=None):
        return make_response(next(page_iter))
    with patch(PATCH_TARGET, side_effect=_side_effect):
        models = prov.list_models()
    ids = sorted(m.id for m in models)
    assert ids == ["gemini-2.0-flash", "gemini-2.5-pro"]


def test_list_models_filters_hidden_keywords():
    """imagen / veo / lyria / -tts / embedding etc. must be filtered."""
    prov = GeminiProvider(api_key="g-key")
    page = {"models": [
        {"name": "models/imagen-3", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/veo-2", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]},
        {"name": "models/gemini-2.0-flash-tts", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
    ]}
    with patch(PATCH_TARGET, return_value=make_response(page)):
        ids = [m.id for m in prov.list_models()]
    assert "imagen-3" not in ids
    assert "veo-2" not in ids
    assert "text-embedding-004" not in ids
    assert "gemini-2.0-flash-tts" not in ids
    assert "gemini-2.5-flash" in ids


def test_list_models_dedup_by_family_key():
    prov = GeminiProvider(api_key="g-key")
    page = {"models": [
        {"name": "models/gemini-2.0-flash-001", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-2.0-flash", "supportedGenerationMethods": ["generateContent"]},
    ]}
    with patch(PATCH_TARGET, return_value=make_response(page)):
        models = prov.list_models()
    # Both collapse to family-key "gemini-2.0-flash"; only one kept
    assert len(models) == 1


def test_list_models_raises_on_http_error():
    prov = GeminiProvider(api_key="g-key")
    with patch(PATCH_TARGET, side_effect=make_http_error(500, "x")):
        with pytest.raises(RemoteApiError) as ei:
            prov.list_models()
    assert ei.value.code == "remote_error"


def test_list_models_raises_connection_failed_on_url_error():
    prov = GeminiProvider(api_key="g-key")
    with patch(PATCH_TARGET, side_effect=make_url_error("down")):
        with pytest.raises(RemoteApiError) as ei:
            prov.list_models()
    assert ei.value.code == "connection_failed"


def test_list_models_assigns_vision_capability_to_modern_models():
    prov = GeminiProvider(api_key="g-key")
    page = {"models": [
        {"name": "models/gemini-2.5-flash", "supportedGenerationMethods": ["generateContent"]},
        {"name": "models/gemini-2.5-pro", "supportedGenerationMethods": ["generateContent"]},
    ]}
    with patch(PATCH_TARGET, return_value=make_response(page)):
        models = {m.id: m for m in prov.list_models()}
    assert "vision" in models["gemini-2.5-flash"].capabilities
    assert "vision" in models["gemini-2.5-pro"].capabilities


# ─── chat ───

def test_chat_returns_text_from_candidates():
    prov = GeminiProvider(api_key="g-key")
    payload = {"candidates": [
        {"content": {"parts": [{"text": "  generated  "}]}},
    ]}
    with patch(PATCH_TARGET, return_value=make_response(payload)):
        result = prov.chat(model="gemini-2.5-flash", messages=[{"role": "user", "content": "hi"}])
    assert result == "generated"


def test_chat_returns_empty_when_no_candidates():
    prov = GeminiProvider(api_key="g-key")
    with patch(PATCH_TARGET, return_value=make_response({"candidates": []})):
        result = prov.chat(model="gemini-2.5-flash", messages=[{"role": "user", "content": "hi"}])
    assert result == ""


def test_chat_payload_converts_user_role_correctly():
    prov = GeminiProvider(api_key="g-key")
    captured = []
    def _side_effect(req, timeout=None):
        captured.append(json.loads(req.data.decode("utf-8")))
        return make_response({"candidates": [{"content": {"parts": [{"text": "x"}]}}]})
    with patch(PATCH_TARGET, side_effect=_side_effect):
        prov.chat(model="gemini-2.5-flash", messages=[
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "world"},
        ])
    contents = captured[0]["contents"]
    assert contents[0]["role"] == "user"
    assert contents[1]["role"] == "model"  # assistant → model in Gemini format
    assert contents[0]["parts"][0]["text"] == "hello"


def test_chat_payload_converts_multipart_image_to_inline_data():
    """`{type: image, mime_type, data}` parts must become `inline_data`."""
    prov = GeminiProvider(api_key="g-key")
    captured = []
    def _side_effect(req, timeout=None):
        captured.append(json.loads(req.data.decode("utf-8")))
        return make_response({"candidates": [{"content": {"parts": [{"text": "x"}]}}]})
    with patch(PATCH_TARGET, side_effect=_side_effect):
        prov.chat(model="gemini-2.5-flash", messages=[
            {"role": "user", "content": [
                {"type": "text", "text": "describe"},
                {"type": "image", "mime_type": "image/png", "data": "BASE64DATA"},
            ]},
        ])
    parts = captured[0]["contents"][0]["parts"]
    assert any("text" in p and p["text"] == "describe" for p in parts)
    img_part = next(p for p in parts if "inline_data" in p)
    assert img_part["inline_data"]["mime_type"] == "image/png"
    assert img_part["inline_data"]["data"] == "BASE64DATA"


def test_chat_payload_sets_generation_config():
    prov = GeminiProvider(api_key="g-key")
    captured = []
    def _side_effect(req, timeout=None):
        captured.append(json.loads(req.data.decode("utf-8")))
        return make_response({"candidates": [{"content": {"parts": [{"text": "x"}]}}]})
    with patch(PATCH_TARGET, side_effect=_side_effect):
        prov.chat(
            model="gemini-2.5-flash",
            messages=[{"role": "user", "content": "x"}],
            max_tokens=999, temperature=0.7,
        )
    gen = captured[0]["generationConfig"]
    assert gen["maxOutputTokens"] == 999
    assert gen["temperature"] == 0.7


def test_chat_url_includes_model_and_api_key():
    prov = GeminiProvider(api_key="g-key")
    captured = []
    def _side_effect(req, timeout=None):
        captured.append(req)
        return make_response({"candidates": [{"content": {"parts": [{"text": "x"}]}}]})
    with patch(PATCH_TARGET, side_effect=_side_effect):
        prov.chat(model="gemini-2.5-flash", messages=[{"role": "user", "content": "x"}])
    url = captured[0].full_url
    assert "gemini-2.5-flash:generateContent" in url
    assert "key=g-key" in url


# ─── error mapping ───

@pytest.mark.parametrize("status,body,expected_code", [
    (429, "quota exceeded", "quota_exceeded"),
    (403, "API key invalid", "auth_failed"),
    (401, "unauthorized", "auth_failed"),
    (404, "model not found", "model_not_found"),
    (400, "bad request", "invalid_request"),
    (500, "server error", "remote_error"),
])
def test_chat_error_maps_to_remote_api_error(status, body, expected_code):
    prov = GeminiProvider(api_key="g-key")
    with patch(PATCH_TARGET, side_effect=make_http_error(status, body)):
        with pytest.raises(RemoteApiError) as exc:
            prov.chat(model="gemini-2.5-flash", messages=[{"role": "user", "content": "x"}])
    assert exc.value.code == expected_code


def test_chat_network_error_maps_to_connection_failed():
    prov = GeminiProvider(api_key="g-key")
    with patch(PATCH_TARGET, side_effect=make_url_error("DNS down")):
        with pytest.raises(RemoteApiError) as exc:
            prov.chat(model="gemini-2.5-flash", messages=[{"role": "user", "content": "x"}])
    assert exc.value.code == "connection_failed"


# ─── helpers ───

@pytest.mark.parametrize("model_id,expected", [
    ("gemini-2.0-flash-001", "gemini-2.0-flash"),
    ("gemini-2.0-flash", "gemini-2.0-flash"),
    ("gemini-3.1-pro-preview-05-20", "gemini-3.1-pro-preview"),
])
def test_model_family_key(model_id, expected):
    assert GeminiProvider._model_family_key(model_id) == expected


def test_methods_to_capabilities_text_default_when_no_methods():
    """A model with no generate/embed methods falls back to ['text']."""
    caps = GeminiProvider._methods_to_capabilities("legacy-model", methods=[])
    assert caps == ["text"]


def test_methods_to_capabilities_embedding_only():
    """A model with only embedContent gets ['embedding']."""
    caps = GeminiProvider._methods_to_capabilities("embedding-001", methods=["embedContent"])
    assert caps == ["embedding"]


def test_methods_to_capabilities_modern_text_gets_vision():
    """Modern gemini variants (flash/pro/2.5) get vision added on top of text."""
    caps = GeminiProvider._methods_to_capabilities("gemini-2.5-flash", methods=["generateContent"])
    assert "text" in caps
    assert "vision" in caps


# ─── singleton factory ───

def test_get_gemini_provider_singleton():
    p1 = get_gemini_provider(api_key="A")
    p2 = get_gemini_provider(api_key="A")
    assert p1 is p2
    p3 = get_gemini_provider(api_key="B")
    assert p1 is not p3


# ─── get_summary_chunking_hints ───

def test_get_summary_chunking_hints_returns_128k_24k():
    """Gemini returns 128k/24k regardless of model name."""
    p = GeminiProvider("https://generativelanguage.googleapis.com", "AIza-test")
    hints = p.get_summary_chunking_hints("gemini-2.5-flash")
    assert hints == {"n_ctx": 128000, "model_cap": 24000}


def test_get_summary_chunking_hints_consistent_across_models():
    """Same hints returned for all Gemini model variants."""
    p = GeminiProvider("https://generativelanguage.googleapis.com", "AIza-test")
    assert p.get_summary_chunking_hints("gemini-1.5-pro") == {"n_ctx": 128000, "model_cap": 24000}
    assert p.get_summary_chunking_hints("gemini-2.0-flash") == {"n_ctx": 128000, "model_cap": 24000}
