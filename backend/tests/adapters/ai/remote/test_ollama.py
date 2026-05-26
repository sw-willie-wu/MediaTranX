"""Unit tests for app.adapters.ai.remote.ollama."""
import json
from unittest.mock import patch

import pytest

from app.adapters.ai.remote import ollama as ollama_mod
from app.adapters.ai.remote.ollama import OllamaProvider, get_ollama_provider
from app.handler.exceptions import RemoteApiError

from .conftest import make_response, make_http_error, make_url_error


PATCH_TARGET = "app.adapters.ai.remote.ollama.urllib.request.urlopen"


@pytest.fixture(autouse=True)
def _reset_singleton():
    ollama_mod._ollama = None
    yield
    ollama_mod._ollama = None


# ─── connect ───

def test_connect_returns_true_on_version_response():
    prov = OllamaProvider()
    with patch(PATCH_TARGET, return_value=make_response({"version": "0.4.0"})):
        assert prov.connect() is True


def test_connect_returns_false_on_network_failure():
    prov = OllamaProvider()
    with patch(PATCH_TARGET, side_effect=make_url_error("Connection refused")):
        assert prov.connect() is False


def test_connect_returns_false_on_invalid_json():
    prov = OllamaProvider()
    with patch(PATCH_TARGET, return_value=make_response(b"not-json")):
        assert prov.connect() is False


def test_connect_hits_api_version_endpoint():
    prov = OllamaProvider(endpoint="http://host:11434")
    captured = []
    def _side_effect(req, timeout=None):
        captured.append(req)
        return make_response({"version": "0.4.0"})
    with patch(PATCH_TARGET, side_effect=_side_effect):
        prov.connect()
    assert captured[0].full_url == "http://host:11434/api/version"


# ─── list_models ───

def test_list_models_parses_tags_response():
    prov = OllamaProvider()
    page = {"models": [
        {"name": "llama3.2:3b", "size": 2000000000, "details": {
            "family": "llama", "families": ["llama"],
            "parameter_size": "3B", "quantization_level": "Q4_0",
        }},
    ]}
    show_resp = {"capabilities": ["completion"]}
    responses = iter([make_response(page), make_response(show_resp)])
    def _side_effect(req, timeout=None):
        return next(responses)
    with patch(PATCH_TARGET, side_effect=_side_effect):
        models = prov.list_models()
    assert len(models) == 1
    m = models[0]
    assert m.id == "llama3.2:3b"
    assert m.size == 2000000000
    assert m.family == "llama"
    assert m.parameter_size == "3B"
    assert m.quantization == "Q4_0"


def test_list_models_returns_empty_on_failure():
    prov = OllamaProvider()
    with patch(PATCH_TARGET, side_effect=make_url_error("down")):
        assert prov.list_models() == []


def test_list_models_caches_capabilities_per_model():
    """Second list_models call must NOT re-query /api/show for the same model."""
    prov = OllamaProvider()
    page = {"models": [
        {"name": "m1", "size": 1, "details": {"family": "f"}},
    ]}
    show = {"capabilities": ["completion", "vision"]}
    call_count = {"n": 0}
    def _side_effect(req, timeout=None):
        call_count["n"] += 1
        url = req.full_url
        if "/api/tags" in url:
            return make_response(page)
        return make_response(show)

    with patch(PATCH_TARGET, side_effect=_side_effect):
        prov.list_models()
        prov.list_models()

    # 2 × /api/tags + 1 × /api/show (cached on 2nd call)
    assert call_count["n"] == 3


def test_list_models_show_request_carries_correct_body():
    """/api/show POST body must be JSON `{"name": <model_name>}`."""
    prov = OllamaProvider()
    page = {"models": [
        {"name": "mistral:7b", "size": 1, "details": {"family": "mistral"}},
    ]}
    show = {"capabilities": ["completion"]}
    show_bodies = []
    def _side_effect(req, timeout=None):
        if "/api/show" in req.full_url:
            show_bodies.append(json.loads(req.data.decode("utf-8")))
            return make_response(show)
        return make_response(page)
    with patch(PATCH_TARGET, side_effect=_side_effect):
        prov.list_models()
    assert show_bodies == [{"name": "mistral:7b"}]


def test_list_models_capability_detection_vision_keyword_fallback():
    """When /api/show fails, fall back to name keyword detection."""
    prov = OllamaProvider()
    page = {"models": [
        {"name": "llava:7b", "size": 1, "details": {"family": "llama"}},
    ]}
    def _side_effect(req, timeout=None):
        if "/api/tags" in req.full_url:
            return make_response(page)
        raise Exception("show failed")  # forces fallback
    with patch(PATCH_TARGET, side_effect=_side_effect):
        models = prov.list_models()
    assert "vision" in models[0].capabilities


# ─── get_model_ctx ───

def test_get_model_ctx_parses_num_ctx_from_parameters():
    prov = OllamaProvider()
    info = {"parameters": "stop \"<|im_end|>\"\nnum_ctx 32768\n", "modelfile": ""}
    with patch(PATCH_TARGET, return_value=make_response(info)):
        assert prov.get_model_ctx("qwen2") == 32768


def test_get_model_ctx_falls_back_on_failure():
    prov = OllamaProvider()
    with patch(PATCH_TARGET, side_effect=make_url_error("down")):
        assert prov.get_model_ctx("qwen2") == 8192


def test_get_model_ctx_returns_default_when_num_ctx_absent():
    prov = OllamaProvider()
    info = {"parameters": "stop \"<|im_end|>\"\n", "modelfile": ""}
    with patch(PATCH_TARGET, return_value=make_response(info)):
        assert prov.get_model_ctx("qwen2") == 8192


def test_get_model_ctx_parses_from_modelfile_when_parameters_missing():
    prov = OllamaProvider()
    info = {"parameters": "", "modelfile": "FROM qwen2\nPARAMETER num_ctx 16384\n"}
    with patch(PATCH_TARGET, return_value=make_response(info)):
        assert prov.get_model_ctx("qwen2") == 16384


# ─── chat ───

def test_chat_returns_message_content():
    prov = OllamaProvider()
    with patch(PATCH_TARGET, return_value=make_response({
        "message": {"role": "assistant", "content": "  hi  "},
    })):
        result = prov.chat(model="llama3.2:3b", messages=[{"role": "user", "content": "x"}])
    assert result == "hi"


def test_chat_payload_includes_options():
    prov = OllamaProvider()
    captured = []
    def _side_effect(req, timeout=None):
        captured.append(json.loads(req.data.decode("utf-8")))
        return make_response({"message": {"content": "x"}})
    with patch(PATCH_TARGET, side_effect=_side_effect):
        prov.chat(model="m", messages=[{"role": "user", "content": "x"}],
                  max_tokens=500, temperature=0.7)
    payload = captured[0]
    assert payload["model"] == "m"
    assert payload["stream"] is False
    assert payload["options"]["num_predict"] == 500
    assert payload["options"]["temperature"] == 0.7


def test_chat_url_targets_api_chat():
    prov = OllamaProvider(endpoint="http://host:11434")
    captured = []
    def _side_effect(req, timeout=None):
        captured.append(req)
        return make_response({"message": {"content": "x"}})
    with patch(PATCH_TARGET, side_effect=_side_effect):
        prov.chat(model="m", messages=[])
    assert captured[0].full_url == "http://host:11434/api/chat"


# ─── error mapping ───

@pytest.mark.parametrize("status,body,expected_code", [
    (500, "model load EOF", "gpu_oom"),
    (404, "model not found", "model_not_found"),
    (401, "unauthorized", "auth_failed"),
    (403, "forbidden", "auth_failed"),
    (502, "bad gateway", "remote_error"),
])
def test_chat_error_maps_to_remote_api_error(status, body, expected_code):
    prov = OllamaProvider()
    with patch(PATCH_TARGET, side_effect=make_http_error(status, body)):
        with pytest.raises(RemoteApiError) as exc:
            prov.chat(model="m", messages=[{"role": "user", "content": "x"}])
    assert exc.value.code == expected_code


def test_chat_network_error_maps_to_connection_failed():
    prov = OllamaProvider()
    with patch(PATCH_TARGET, side_effect=make_url_error("refused")):
        with pytest.raises(RemoteApiError) as exc:
            prov.chat(model="m", messages=[{"role": "user", "content": "x"}])
    assert exc.value.code == "connection_failed"


# ─── singleton ───

def test_get_ollama_provider_singleton():
    p1 = get_ollama_provider("http://a:11434")
    p2 = get_ollama_provider("http://a:11434")
    assert p1 is p2
    p3 = get_ollama_provider("http://b:11434")
    assert p1 is not p3


# ─── get_summary_chunking_hints ───

def test_get_summary_chunking_hints_queries_model_ctx(monkeypatch):
    """Ollama hints derive from /api/show num_ctx via get_model_ctx."""
    p = OllamaProvider("http://localhost:11434", None)
    monkeypatch.setattr(p, "get_model_ctx", lambda model: 65536)
    hints = p.get_summary_chunking_hints("qwen3.5:9b")
    # 65536 * 0.75 = 49152, capped at 16000
    assert hints == {"n_ctx": 65536, "model_cap": 16000}


def test_get_summary_chunking_hints_falls_back_on_error(monkeypatch):
    """Network failure on get_model_ctx falls back to base 32k/6k default."""
    p = OllamaProvider("http://localhost:11434", None)

    def _raise(model):
        raise RuntimeError("network down")

    monkeypatch.setattr(p, "get_model_ctx", _raise)
    hints = p.get_summary_chunking_hints("qwen3.5:9b")
    assert hints == {"n_ctx": 32768, "model_cap": 6000}


def test_get_summary_chunking_hints_caps_model_cap_at_16k(monkeypatch):
    """Even with huge n_ctx, model_cap stays at the 16k coherence ceiling."""
    p = OllamaProvider("http://localhost:11434", None)
    monkeypatch.setattr(p, "get_model_ctx", lambda model: 200000)
    hints = p.get_summary_chunking_hints("any:huge")
    assert hints == {"n_ctx": 200000, "model_cap": 16000}


def test_get_summary_chunking_hints_floors_model_cap_at_6k(monkeypatch):
    """Small n_ctx still gives at least 6000 model_cap (parity with old hardcoded)."""
    p = OllamaProvider("http://localhost:11434", None)
    monkeypatch.setattr(p, "get_model_ctx", lambda model: 4096)
    hints = p.get_summary_chunking_hints("tiny")
    # min(int(4096*0.75), 16000) = 3072; max(6000, 3072) = 6000
    assert hints == {"n_ctx": 4096, "model_cap": 6000}
