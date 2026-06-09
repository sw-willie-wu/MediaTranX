"""Tests for the Ollama VLM probe helper.

The probe is a thin wrapper around OllamaProvider that catches errors
and returns structured ProbeResult dicts. We mock the urlopen layer
because the probe's value-add is the dataclass shape + never-raises
contract, not the HTTP semantics (those are covered by test_ollama*).
"""
import json
from unittest.mock import MagicMock, patch


def _ndjson_response_bytes(*chunks: dict) -> bytes:
    return b"".join((json.dumps(c) + "\n").encode("utf-8") for c in chunks)


def _make_fake_streaming_response(body_bytes: bytes):
    lines = [l for l in body_bytes.split(b"\n") if l]
    resp = MagicMock(name="HTTPResponse")
    resp.__iter__ = lambda self: iter([l + b"\n" for l in lines])
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    resp.close = MagicMock()
    return resp


def test_probe_ollama_vlm_success_returns_success_true_with_detail_snippet():
    from app.adapters.ai.remote.probe import probe_ollama_vlm

    body = _ndjson_response_bytes(
        {"message": {"content": "A colourful gradient."}},
        {"done": True},
    )
    fake_resp = _make_fake_streaming_response(body)

    with patch("app.adapters.ai.remote._http.urlopen", return_value=fake_resp):
        # Pass image_b64 to skip PIL synthetic-image generation
        result = probe_ollama_vlm("http://x:11435", "model-x", image_b64="dGVzdA==")

    assert result.success is True
    assert result.model == "model-x"
    assert result.endpoint == "http://x:11435"
    assert result.code is None
    assert result.detail == "A colourful gradient."
    assert result.elapsed_ms >= 0


def test_probe_ollama_vlm_proxy_error_returns_code_and_full_detail():
    """The whole point of the probe — proxy 500 with detail must be
    captured into the ProbeResult, not swallowed."""
    from app.adapters.ai.remote.probe import probe_ollama_vlm

    body = _ndjson_response_bytes({
        "done": True, "done_reason": "error",
        "error": "backend returned 500",
        "detail": "vLLM upstream unreachable: Connection refused",
    })
    fake_resp = _make_fake_streaming_response(body)

    with patch("app.adapters.ai.remote._http.urlopen", return_value=fake_resp):
        result = probe_ollama_vlm("http://x:11435", "qwen3.5-122b-vllm", image_b64="dGVzdA==")

    assert result.success is False
    assert result.code == "remote_error"
    assert "backend returned 500" in result.detail
    assert "vLLM upstream unreachable" in result.detail
    assert result.model == "qwen3.5-122b-vllm"


def test_probe_ollama_vlm_connection_refused_returns_connection_failed():
    """OSError from urlopen (e.g. proxy down, network unreachable) is
    wrapped as connection_failed by OllamaProvider and surfaces verbatim."""
    from app.adapters.ai.remote.probe import probe_ollama_vlm

    def _raise_oserror(req, timeout=None):
        raise OSError("Connection refused")

    with patch("app.adapters.ai.remote._http.urlopen", side_effect=_raise_oserror):
        result = probe_ollama_vlm("http://nope:11435", "any-model", image_b64="dGVzdA==")

    assert result.success is False
    assert result.code == "connection_failed"
    assert "Connection refused" in result.detail


def test_probe_ollama_vlm_synthetic_image_used_when_no_b64_provided():
    """Default code-path generates a synthetic JPEG. Verify we don't crash
    and that the resulting messages payload carries exactly one image."""
    from app.adapters.ai.remote.probe import probe_ollama_vlm

    body = _ndjson_response_bytes({"message": {"content": "ok"}}, {"done": True})
    fake_resp = _make_fake_streaming_response(body)
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["data"] = json.loads(req.data.decode("utf-8"))
        return fake_resp

    with patch("app.adapters.ai.remote._http.urlopen", side_effect=fake_urlopen):
        result = probe_ollama_vlm("http://x:11435", "model-x")

    assert result.success is True
    images = captured["data"]["messages"][0]["images"]
    assert len(images) == 1
    # base64-of-JPEG starts with "/9j/" (FFD8FF in base64)
    assert images[0].startswith("/9j/")


def test_probe_ollama_vlm_never_raises_on_unexpected_exception():
    """Contract: probe must always return a ProbeResult, never raise."""
    from app.adapters.ai.remote.probe import probe_ollama_vlm

    def _raise_unexpected(req, timeout=None):
        raise RuntimeError("something totally unexpected")

    with patch("app.adapters.ai.remote._http.urlopen", side_effect=_raise_unexpected):
        # If the probe contract holds this returns a ProbeResult; if it
        # leaked the exception this would fail before reaching assertions.
        result = probe_ollama_vlm("http://x:11435", "m", image_b64="dGVzdA==")

    assert result.success is False
    assert result.code == "probe_exception"
    assert "RuntimeError" in result.detail
    assert "something totally unexpected" in result.detail
