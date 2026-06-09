import json
import pytest

from app.adapters.ai.remote import _http
from app.adapters.ai.remote.base import PROBE_TIMEOUT, TEST_TIMEOUT
from app.adapters.ai.remote.ollama import OllamaProvider
from app.adapters.ai.remote.openai import OpenAIProvider
from app.adapters.ai.remote.gemini import GeminiProvider


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def read(self):
        return json.dumps(self._payload).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def capture_timeout(monkeypatch):
    """Patch urllib.request.urlopen everywhere and record the timeout kwarg."""
    seen = {"timeout": None}

    def fake_urlopen(req, timeout=None):
        seen["timeout"] = timeout
        return _FakeResp({"data": [], "models": []})

    monkeypatch.setattr(_http, "urlopen", fake_urlopen)
    return seen


@pytest.mark.parametrize("make_provider", [
    lambda: OllamaProvider("http://x"),
    lambda: OpenAIProvider("http://x", "sk-test"),
    lambda: GeminiProvider("http://x", "key"),
])
def test_list_models_defaults_to_probe_timeout(capture_timeout, make_provider):
    make_provider().list_models()
    assert capture_timeout["timeout"] == PROBE_TIMEOUT


@pytest.mark.parametrize("make_provider", [
    lambda: OllamaProvider("http://x"),
    lambda: OpenAIProvider("http://x", "sk-test"),
    lambda: GeminiProvider("http://x", "key"),
])
def test_list_models_honours_explicit_timeout(capture_timeout, make_provider):
    make_provider().list_models(timeout=TEST_TIMEOUT)
    assert capture_timeout["timeout"] == TEST_TIMEOUT


def test_is_available_forwards_timeout(capture_timeout):
    OllamaProvider("http://x").is_available(timeout=TEST_TIMEOUT)
    assert capture_timeout["timeout"] == TEST_TIMEOUT
