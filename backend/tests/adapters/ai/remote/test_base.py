"""Unit tests for app.adapters.ai.remote.base — RemoteModel + abstract base."""
from app.adapters.ai.remote.base import RemoteModel, RemoteProvider


# --- RemoteModel ---

def test_remote_model_defaults_capabilities_to_text():
    m = RemoteModel(id="x", name="x")
    assert m.capabilities == ["text"]


def test_remote_model_explicit_capabilities_preserved():
    m = RemoteModel(id="x", name="x", capabilities=["text", "vision"])
    assert m.capabilities == ["text", "vision"]


def test_remote_model_optional_fields_default_none():
    m = RemoteModel(id="x", name="x")
    assert m.size is None
    assert m.family is None
    assert m.parameter_size is None
    assert m.quantization is None


# --- RemoteProvider abstract base ---

class _StubProvider(RemoteProvider):
    """Concrete subclass for testing base behavior."""
    def __init__(self, endpoint: str, api_key=None, connect_result: bool | Exception = True):
        super().__init__(endpoint, api_key)
        self._connect_result = connect_result

    def connect(self) -> bool:
        if isinstance(self._connect_result, Exception):
            raise self._connect_result
        return self._connect_result

    def list_models(self):
        return []

    def chat(self, model, messages, max_tokens=2048, temperature=0.1):
        return ""


def test_endpoint_trailing_slash_stripped():
    p = _StubProvider("https://api.example.com/")
    assert p.endpoint == "https://api.example.com"


def test_endpoint_no_trailing_slash_unchanged():
    p = _StubProvider("https://api.example.com")
    assert p.endpoint == "https://api.example.com"


def test_is_available_returns_true_when_connect_succeeds():
    p = _StubProvider("https://x", connect_result=True)
    assert p.is_available() is True


def test_is_available_returns_false_when_connect_returns_false():
    p = _StubProvider("https://x", connect_result=False)
    assert p.is_available() is False


def test_is_available_returns_false_when_connect_raises():
    p = _StubProvider("https://x", connect_result=RuntimeError("boom"))
    assert p.is_available() is False
