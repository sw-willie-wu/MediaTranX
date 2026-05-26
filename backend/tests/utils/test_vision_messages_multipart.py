"""Tests for build_vision_chat_messages multi-image signature + read_image_raw_b64."""
from pathlib import Path

import pytest


def test_read_image_raw_b64_returns_source_bytes_for_png(tmp_path):
    """Raw helper returns file bytes verbatim — does NOT touch PIL."""
    import base64
    from app.utils.vision_messages import read_image_raw_b64

    # Real 1x1 PNG (8 bytes header + IHDR + IDAT + IEND)
    raw = (
        b"\x89PNG\r\n\x1a\n"
        b"\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
        b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\rIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01"
        b"\x0d\n-\xb4"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    p = tmp_path / "tiny.png"
    p.write_bytes(raw)

    b64, mime = read_image_raw_b64(str(p))
    assert base64.b64decode(b64) == raw
    assert mime == "image/png"


def test_read_image_raw_b64_unknown_extension_defaults_png(tmp_path):
    """No-extension or unknown-extension file falls back to image/png MIME."""
    from app.utils.vision_messages import read_image_raw_b64

    p = tmp_path / "noext"
    p.write_bytes(b"abc")
    _, mime = read_image_raw_b64(str(p))
    assert mime == "image/png"


def test_read_image_raw_b64_skips_pil_for_invalid_image(tmp_path):
    """Even garbage 'PNG-looking' bytes succeed — raw path never invokes PIL."""
    from app.utils.vision_messages import read_image_raw_b64

    p = tmp_path / "garbage.png"
    p.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)  # invalid PNG IHDR
    b64, mime = read_image_raw_b64(str(p))
    assert mime == "image/png"
    assert b64  # non-empty; no PIL.UnidentifiedImageError raised


# --- build_vision_chat_messages multi-image dispatch ---

PARTS_2 = [("BBBB1", "image/png"), ("BBBB2", "image/jpeg")]


def test_build_vision_chat_messages_ollama_multi_image():
    from app.utils.vision_messages import build_vision_chat_messages
    msgs = build_vision_chat_messages("ollama", "describe", PARTS_2)
    assert msgs == [{
        "role": "user", "content": "describe",
        "images": ["BBBB1", "BBBB2"],
    }]


def test_build_vision_chat_messages_openai_multi_image():
    from app.utils.vision_messages import build_vision_chat_messages
    msgs = build_vision_chat_messages("openai", "describe", PARTS_2)
    assert msgs == [{
        "role": "user",
        "content": [
            {"type": "text", "text": "describe"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,BBBB1"}},
            {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,BBBB2"}},
        ],
    }]


def test_build_vision_chat_messages_gemini_multi_image():
    from app.utils.vision_messages import build_vision_chat_messages
    msgs = build_vision_chat_messages("gemini", "describe", PARTS_2)
    assert msgs == [{
        "role": "user",
        "content": [
            {"type": "text", "text": "describe"},
            {"type": "image", "mime_type": "image/png", "data": "BBBB1"},
            {"type": "image", "mime_type": "image/jpeg", "data": "BBBB2"},
        ],
    }]


def test_build_vision_chat_messages_single_image_list_wrap():
    """Single-image use case via list-wrap still produces same result as before."""
    from app.utils.vision_messages import build_vision_chat_messages
    msgs = build_vision_chat_messages("openai", "x", [("AAAA", "image/png")])
    assert len(msgs[0]["content"]) == 2  # text + 1 image
    assert msgs[0]["content"][1]["image_url"]["url"] == "data:image/png;base64,AAAA"


def test_build_vision_chat_messages_unknown_provider_defaults_to_openai():
    """Unknown provider falls to openai-compatible shape (current behaviour)."""
    from app.utils.vision_messages import build_vision_chat_messages
    msgs = build_vision_chat_messages("unknown-prov", "x", [("AAAA", "image/png")])
    # Should match openai shape
    assert msgs[0]["content"][1]["type"] == "image_url"
