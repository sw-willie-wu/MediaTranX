"""OllamaProvider streaming chat tests.

Covers the new abort_hook-aware streaming path. The legacy _chat_blocking
path is covered by the unchanged tests in test_ollama.py.

Spec: §F1.
"""
import json
from unittest.mock import MagicMock, patch

import pytest


def _ndjson_response_bytes(*chunks: dict) -> bytes:
    """Build NDJSON body bytes from sequential Ollama stream chunks."""
    return b"".join((json.dumps(c) + "\n").encode("utf-8") for c in chunks)


def _make_fake_urlopen_response(body_bytes: bytes):
    """Build a MagicMock that behaves like urlopen()'s HTTPResponse:
    - iterable line-by-line (yields bytes per line)
    - .close() supported
    """
    lines = body_bytes.split(b"\n")
    lines = [l for l in lines if l]  # drop trailing empty
    resp = MagicMock(name="HTTPResponse")
    resp.__iter__ = lambda self: iter([l + b"\n" for l in lines])
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    resp.close = MagicMock()
    return resp


def test_chat_streaming_sends_stream_true_and_returns_concatenated_content():
    """abort_hook present → streaming path → sends stream:true, parses NDJSON."""
    from app.adapters.ai.remote.ollama import OllamaProvider

    body = _ndjson_response_bytes(
        {"message": {"content": "Hello "}},
        {"message": {"content": "world"}},
        {"done": True},
    )
    fake_resp = _make_fake_urlopen_response(body)

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["data"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return fake_resp

    prov = OllamaProvider("http://localhost:11434", None)
    with patch("app.adapters.ai.remote.ollama.urllib.request.urlopen", side_effect=fake_urlopen):
        result = prov.chat(
            model="qwen3.5:9b",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=100, temperature=0.2,
            abort_hook=lambda r: None,
        )
    assert result == "Hello world"
    assert captured["data"]["stream"] is True
    assert captured["timeout"] == 600


def test_chat_blocking_legacy_path_unchanged():
    """abort_hook absent → legacy path → sends stream:false, single read."""
    from app.adapters.ai.remote.ollama import OllamaProvider

    fake_body = json.dumps({"message": {"content": "Hi"}}).encode("utf-8")
    fake_resp = MagicMock(name="HTTPResponse")
    fake_resp.read = MagicMock(return_value=fake_body)
    fake_resp.__enter__ = MagicMock(return_value=fake_resp)
    fake_resp.__exit__ = MagicMock(return_value=False)

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["data"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return fake_resp

    prov = OllamaProvider("http://localhost:11434", None)
    with patch("app.adapters.ai.remote.ollama.urllib.request.urlopen", side_effect=fake_urlopen):
        result = prov.chat(
            model="qwen3.5:9b",
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=100, temperature=0.2,
            # no abort_hook → legacy
        )
    assert result == "Hi"
    assert captured["data"]["stream"] is False
    assert captured["timeout"] == 300


def test_chat_streaming_calls_abort_hook_with_response_before_read():
    """abort_hook receives the live response object before iteration starts."""
    from app.adapters.ai.remote.ollama import OllamaProvider

    body = _ndjson_response_bytes(
        {"message": {"content": "ok"}}, {"done": True},
    )
    fake_resp = _make_fake_urlopen_response(body)

    received = []
    prov = OllamaProvider("http://localhost:11434", None)
    with patch("app.adapters.ai.remote.ollama.urllib.request.urlopen", return_value=fake_resp):
        prov.chat(
            model="m", messages=[{"role": "user", "content": "x"}],
            max_tokens=10, temperature=0.0,
            abort_hook=lambda r: received.append(r),
        )
    assert len(received) == 1
    assert received[0] is fake_resp


def test_chat_streaming_socket_close_raises_remote_api_error_connection_failed():
    """Cancel-induced socket close (resp.close from another thread) → OSError
    inside the read loop → wrapped as RemoteApiError(connection_failed)."""
    from app.adapters.ai.remote.ollama import OllamaProvider
    from app.handler.exceptions import RemoteApiError

    fake_resp = MagicMock(name="HTTPResponse")
    fake_resp.__iter__ = MagicMock(side_effect=OSError("socket closed"))
    fake_resp.__enter__ = MagicMock(return_value=fake_resp)
    fake_resp.__exit__ = MagicMock(return_value=False)
    fake_resp.close = MagicMock()

    prov = OllamaProvider("http://localhost:11434", None)
    with patch("app.adapters.ai.remote.ollama.urllib.request.urlopen", return_value=fake_resp):
        with pytest.raises(RemoteApiError) as excinfo:
            prov.chat(
                model="m", messages=[{"role": "user", "content": "x"}],
                max_tokens=10, temperature=0.0,
                abort_hook=lambda r: None,
            )
    assert excinfo.value.code == "connection_failed"


def test_chat_with_images_sends_messages_with_base64_images_array(tmp_path):
    """Ollama multimodal: messages[0].images = [base64...] (no data URI prefix)."""
    from app.adapters.ai.remote.ollama import OllamaProvider

    # Real-looking PNG header so base64 encoding is exercised.
    img = tmp_path / "frame.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)

    body = _ndjson_response_bytes(
        {"message": {"content": "A still image"}}, {"done": True},
    )
    fake_resp = _make_fake_urlopen_response(body)

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["data"] = json.loads(req.data.decode("utf-8"))
        captured["timeout"] = timeout
        return fake_resp

    prov = OllamaProvider("http://localhost:11434", None)
    with patch("app.adapters.ai.remote.ollama.urllib.request.urlopen", side_effect=fake_urlopen):
        result = prov.chat_with_images(
            model="qwen3vl:8b",
            prompt="describe",
            images=[img],
            max_tokens=200, temperature=0.0,
            abort_hook=lambda r: None,
        )
    assert result == "A still image"
    payload = captured["data"]
    assert payload["stream"] is True
    assert payload["model"] == "qwen3vl:8b"
    assert payload["messages"][0]["role"] == "user"
    assert payload["messages"][0]["content"] == "describe"
    assert isinstance(payload["messages"][0]["images"], list)
    assert len(payload["messages"][0]["images"]) == 1
    # Raw base64, no data: prefix
    b64 = payload["messages"][0]["images"][0]
    assert not b64.startswith("data:")
    import base64
    decoded = base64.b64decode(b64)
    assert decoded.startswith(b"\x89PNG")
    assert captured["timeout"] == 600


def test_chat_with_images_calls_abort_hook(tmp_path):
    """chat_with_images also calls abort_hook with the live response."""
    from app.adapters.ai.remote.ollama import OllamaProvider

    img = tmp_path / "x.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 64)
    body = _ndjson_response_bytes(
        {"message": {"content": "ok"}}, {"done": True},
    )
    fake_resp = _make_fake_urlopen_response(body)

    received = []
    prov = OllamaProvider("http://localhost:11434", None)
    with patch("app.adapters.ai.remote.ollama.urllib.request.urlopen", return_value=fake_resp):
        prov.chat_with_images(
            model="m", prompt="p", images=[img],
            max_tokens=10, temperature=0.0,
            abort_hook=lambda r: received.append(r),
        )
    assert received == [fake_resp]


def test_chat_with_images_multiple_images_preserved_order(tmp_path):
    """Multiple images preserve insertion order in the images array."""
    from app.adapters.ai.remote.ollama import OllamaProvider

    imgs = []
    for i in range(3):
        p = tmp_path / f"f{i}.png"
        p.write_bytes(b"\x89PNG\r\n\x1a\n" + bytes([i] * 64))
        imgs.append(p)

    body = _ndjson_response_bytes(
        {"message": {"content": "ok"}}, {"done": True},
    )
    fake_resp = _make_fake_urlopen_response(body)

    captured = {}
    def fake_urlopen(req, timeout=None):
        captured["data"] = json.loads(req.data.decode("utf-8"))
        return fake_resp

    prov = OllamaProvider("http://localhost:11434", None)
    with patch("app.adapters.ai.remote.ollama.urllib.request.urlopen", side_effect=fake_urlopen):
        prov.chat_with_images(
            model="m", prompt="p", images=imgs,
            max_tokens=10, temperature=0.0,
            abort_hook=lambda r: None,
        )
    images_b64 = captured["data"]["messages"][0]["images"]
    assert len(images_b64) == 3
    import base64
    # ordered i=0,1,2 by the 64-byte unique tail
    for i, b64 in enumerate(images_b64):
        decoded = base64.b64decode(b64)
        assert decoded.endswith(bytes([i] * 64))
