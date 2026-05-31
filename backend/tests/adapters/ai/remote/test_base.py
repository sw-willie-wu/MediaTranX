"""Unit tests for app.adapters.ai.remote.base — RemoteModel + abstract base."""
import pytest

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
    PROVIDER_NAME = "stub"
    IMAGE_PREP_MODE = "raw"

    def __init__(self, endpoint: str, api_key=None, connect_result: "bool | Exception" = True):
        super().__init__(endpoint, api_key)
        self._connect_result = connect_result

    def connect(self, timeout: int = 3) -> bool:
        if isinstance(self._connect_result, Exception):
            raise self._connect_result
        return self._connect_result

    def list_models(self, timeout: int = 3):
        return []

    def chat(self, model, messages, *, max_tokens=2048, temperature=0.1, abort_hook=None):
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


# --- ClassVar enforcement via __init_subclass__ ---

def test_subclass_missing_provider_name_raises():
    """Subclass without PROVIDER_NAME ClassVar must fail at class-creation time."""
    with pytest.raises(TypeError, match="PROVIDER_NAME"):
        class _NoName(RemoteProvider):
            IMAGE_PREP_MODE = "raw"
            def connect(self): return True
            def list_models(self): return []
            def chat(self, model, messages, *, max_tokens=2048,
                     temperature=0.1, abort_hook=None): return ""


def test_subclass_missing_image_prep_mode_raises():
    """Subclass without IMAGE_PREP_MODE ClassVar must fail."""
    with pytest.raises(TypeError, match="IMAGE_PREP_MODE"):
        class _NoMode(RemoteProvider):
            PROVIDER_NAME = "x"
            def connect(self): return True
            def list_models(self): return []
            def chat(self, model, messages, *, max_tokens=2048,
                     temperature=0.1, abort_hook=None): return ""


def test_subclass_invalid_image_prep_mode_raises():
    """IMAGE_PREP_MODE not in {'raw','recompress'} must fail."""
    with pytest.raises(TypeError, match="IMAGE_PREP_MODE"):
        class _BadMode(RemoteProvider):
            PROVIDER_NAME = "x"
            IMAGE_PREP_MODE = "invalid"
            def connect(self): return True
            def list_models(self): return []
            def chat(self, model, messages, *, max_tokens=2048,
                     temperature=0.1, abort_hook=None): return ""


def test_subclass_with_both_classvars_passes():
    """Valid declaration of both ClassVars works."""
    class _Good(RemoteProvider):
        PROVIDER_NAME = "good"
        IMAGE_PREP_MODE = "raw"
        def connect(self): return True
        def list_models(self): return []
        def chat(self, model, messages, *, max_tokens=2048,
                 temperature=0.1, abort_hook=None): return ""
    inst = _Good("http://x")
    assert inst.PROVIDER_NAME == "good"
    assert inst.IMAGE_PREP_MODE == "raw"


# --- get_summary_chunking_hints ---

def test_get_summary_chunking_hints_default():
    """Base default returns conservative 32k/6k."""
    p = _StubProvider("http://x")
    hints = p.get_summary_chunking_hints("any-model")
    assert hints == {"n_ctx": 32768, "model_cap": 6000}
