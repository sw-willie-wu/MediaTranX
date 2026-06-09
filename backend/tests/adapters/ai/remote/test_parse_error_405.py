"""405 must map to the specific endpoint_invalid code, not catch-all remote_error."""
from app.adapters.ai.remote.ollama import OllamaProvider
from app.adapters.ai.remote.openai import OpenAIProvider
from app.adapters.ai.remote.gemini import GeminiProvider


def test_ollama_405_maps_to_endpoint_invalid():
    err = OllamaProvider._parse_error(405, "Method Not Allowed")
    assert err.code == "endpoint_invalid"


def test_openai_405_maps_to_endpoint_invalid():
    err = OpenAIProvider._parse_error(405, "Method Not Allowed")
    assert err.code == "endpoint_invalid"


def test_gemini_405_maps_to_endpoint_invalid():
    err = GeminiProvider._parse_error(405, "Method Not Allowed")
    assert err.code == "endpoint_invalid"
