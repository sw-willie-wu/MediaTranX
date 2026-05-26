"""Regression tests for OllamaProvider.chat_with_images post-refactor.

Verifies base default + IMAGE_PREP_MODE='raw' produces:
1. Raw bytes-identical b64 (no PIL roundtrip).
2. Same JSON wire shape as the pre-refactor inline implementation.
3. Survives invalid-PNG fixtures (proof PIL is not in the stack).

Spec §6.2.
"""
import base64
import json
from unittest.mock import MagicMock, patch


def _ndjson_done() -> bytes:
    return (json.dumps({"done": True}) + "\n").encode("utf-8")


def _make_fake_urlopen(body_bytes: bytes):
    lines = [l for l in body_bytes.split(b"\n") if l]
    resp = MagicMock(name="HTTPResponse")
    resp.__iter__ = lambda self: iter([l + b"\n" for l in lines])
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    resp.close = MagicMock()
    return resp


def test_ollama_chat_with_images_uses_raw_bytes(tmp_path):
    """The b64 sent on the wire must equal base64(file.read_bytes())."""
    from app.adapters.ai.remote.ollama import OllamaProvider

    raw = bytes(range(64))                 # 64 arbitrary non-image bytes
    p = tmp_path / "frame.png"
    p.write_bytes(raw)

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["data"] = json.loads(req.data.decode("utf-8"))
        return _make_fake_urlopen(_ndjson_done())

    prov = OllamaProvider("http://localhost:11434", None)
    with patch(
        "app.adapters.ai.remote.ollama.urllib.request.urlopen",
        side_effect=fake_urlopen,
    ):
        prov.chat_with_images(
            model="qwen3vl",
            prompt="x",
            images=[str(p)],
            max_tokens=16,
            temperature=0.0,
            abort_hook=lambda r: None,
        )

    img_b64 = captured["data"]["messages"][0]["images"][0]
    assert base64.b64decode(img_b64) == raw


def test_ollama_chat_with_images_wire_shape_matches_legacy(tmp_path):
    """Two-image payload must produce exact legacy JSON shape:
    {model, stream:True, messages:[{role,content,images:[]}], options:{}}
    """
    from app.adapters.ai.remote.ollama import OllamaProvider

    p1 = tmp_path / "a.png"; p1.write_bytes(b"AAAA")
    p2 = tmp_path / "b.png"; p2.write_bytes(b"BBBB")

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["data"] = json.loads(req.data.decode("utf-8"))
        return _make_fake_urlopen(_ndjson_done())

    prov = OllamaProvider("http://localhost:11434", None)
    with patch(
        "app.adapters.ai.remote.ollama.urllib.request.urlopen",
        side_effect=fake_urlopen,
    ):
        prov.chat_with_images(
            model="qwen3vl",
            prompt="describe",
            images=[str(p1), str(p2)],
            max_tokens=42,
            temperature=0.3,
            abort_hook=lambda r: None,
        )

    expected_b64_a = base64.b64encode(b"AAAA").decode("ascii")
    expected_b64_b = base64.b64encode(b"BBBB").decode("ascii")
    # num_ctx is auto-computed from messages+max_tokens; spot-check the rest
    # of the wire shape and that num_ctx is present + at least the floor.
    body = captured["data"]
    assert body["model"] == "qwen3vl"
    assert body["stream"] is True
    assert body["messages"] == [{
        "role": "user",
        "content": "describe",
        "images": [expected_b64_a, expected_b64_b],
    }]
    assert body["options"]["num_predict"] == 42
    assert body["options"]["temperature"] == 0.3
    assert body["options"]["num_ctx"] >= 4096


def test_ollama_chat_with_images_does_not_invoke_pil(tmp_path):
    """Invalid PNG bytes (truncated) must not raise — proves PIL is bypassed.

    The old inline impl took the same raw-bytes path; the new base default
    via IMAGE_PREP_MODE='raw' must preserve that property.
    """
    from app.adapters.ai.remote.ollama import OllamaProvider

    p = tmp_path / "garbage.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)  # invalid IHDR

    def fake_urlopen(req, timeout=None):
        return _make_fake_urlopen(_ndjson_done())

    prov = OllamaProvider("http://localhost:11434", None)
    with patch(
        "app.adapters.ai.remote.ollama.urllib.request.urlopen",
        side_effect=fake_urlopen,
    ):
        # If PIL is anywhere in the stack, this raises UnidentifiedImageError.
        result = prov.chat_with_images(
            model="qwen3vl",
            prompt="x",
            images=[str(p)],
            max_tokens=16,
            temperature=0.0,
            abort_hook=lambda r: None,
        )
    assert isinstance(result, str)
