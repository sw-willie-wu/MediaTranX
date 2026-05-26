"""Integration tests for RemoteChatSession with non-Ollama providers.

Verifies:
- chat() works with abort_hook stash for OpenAI + Gemini.
- chat_with_images() flows through base default (per-provider IMAGE_PREP_MODE).
- kill_process closes the stashed response across threads.

Spec §F2 + §3.1.
"""
import base64
import json
import threading
from unittest.mock import MagicMock, patch

import pytest


def _make_sse_response(*lines: bytes):
    resp = MagicMock(name="HTTPResponse")
    resp.__iter__ = lambda self: iter([l for l in lines])
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    resp.close = MagicMock()
    return resp


# --- chat() through RemoteChatSession ---

def test_remote_chat_session_with_openai_chat_completions():
    from app.adapters.ai.remote.openai import OpenAIProvider
    from app.services.llm.remote_chat import RemoteChatSession

    lines = [
        b'data: {"choices":[{"delta":{"content":"OK"}}]}\n',
        b'data: [DONE]\n',
    ]
    prov = OpenAIProvider("https://api.openai.com", "sk-test")
    sess = RemoteChatSession(prov, "gpt-4o-mini")

    with patch(
        "app.adapters.ai.remote.openai.urllib.request.urlopen",
        return_value=_make_sse_response(*lines),
    ):
        result = sess.chat(
            messages=[{"role": "user", "content": "x"}],
            max_tokens=10, temperature=0.0,
        )
    assert result == "OK"


def test_remote_chat_session_with_gemini():
    from app.adapters.ai.remote.gemini import GeminiProvider
    from app.services.llm.remote_chat import RemoteChatSession

    lines = [
        b'data: {"candidates":[{"content":{"parts":[{"text":"OK"}]}}]}\n',
    ]
    prov = GeminiProvider(
        "https://generativelanguage.googleapis.com", "AIza-test",
    )
    sess = RemoteChatSession(prov, "gemini-2.5-flash")

    with patch(
        "app.adapters.ai.remote.gemini.urllib.request.urlopen",
        return_value=_make_sse_response(*lines),
    ):
        result = sess.chat(
            messages=[{"role": "user", "content": "x"}],
            max_tokens=10, temperature=0.0,
        )
    assert result == "OK"


# --- chat_with_images() through base default ---

def test_chat_with_images_openai_uses_image_url_data_uri(tmp_path):
    """OpenAI IMAGE_PREP_MODE='recompress' → PIL roundtrip → JPEG quality 85."""
    from app.adapters.ai.remote.openai import OpenAIProvider
    from app.services.llm.remote_chat import RemoteChatSession
    from PIL import Image

    # Create a real 16x16 PNG
    img = Image.new("RGB", (16, 16), color="red")
    p = tmp_path / "test.png"
    img.save(str(p))

    lines = [
        b'data: {"choices":[{"delta":{"content":"red"}}]}\n',
        b'data: [DONE]\n',
    ]
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["data"] = json.loads(req.data.decode("utf-8"))
        return _make_sse_response(*lines)

    prov = OpenAIProvider("https://api.openai.com", "sk-test")
    sess = RemoteChatSession(prov, "gpt-4o-mini")

    with patch(
        "app.adapters.ai.remote.openai.urllib.request.urlopen",
        side_effect=fake_urlopen,
    ):
        result = sess.chat_with_images(
            prompt="describe color",
            images=[str(p)],
            max_tokens=10, temperature=0.0,
        )
    assert result == "red"
    # Verify shape: messages[0].content is a list with text + image_url parts
    content = captured["data"]["messages"][0]["content"]
    assert content[0]["type"] == "text"
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"].startswith("data:image/jpeg;base64,")


def test_chat_with_images_gemini_uses_inline_data(tmp_path):
    from app.adapters.ai.remote.gemini import GeminiProvider
    from app.services.llm.remote_chat import RemoteChatSession
    from PIL import Image

    img = Image.new("RGB", (16, 16), color="blue")
    p = tmp_path / "test.png"
    img.save(str(p))

    lines = [
        b'data: {"candidates":[{"content":{"parts":[{"text":"blue"}]}}]}\n',
    ]
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["data"] = json.loads(req.data.decode("utf-8"))
        return _make_sse_response(*lines)

    prov = GeminiProvider(
        "https://generativelanguage.googleapis.com", "AIza-test",
    )
    sess = RemoteChatSession(prov, "gemini-2.5-flash")

    with patch(
        "app.adapters.ai.remote.gemini.urllib.request.urlopen",
        side_effect=fake_urlopen,
    ):
        result = sess.chat_with_images(
            prompt="describe",
            images=[str(p)],
            max_tokens=10, temperature=0.0,
        )
    assert result == "blue"
    # Verify Gemini wire shape: parts[].inline_data
    parts = captured["data"]["contents"][0]["parts"]
    assert any("text" in p for p in parts)
    assert any("inline_data" in p and p["inline_data"]["mime_type"] == "image/jpeg"
               for p in parts)


def test_chat_with_images_ollama_uses_raw_b64(tmp_path):
    """Ollama IMAGE_PREP_MODE='raw' → no PIL → source bytes preserved."""
    from app.adapters.ai.remote.ollama import OllamaProvider
    from app.services.llm.remote_chat import RemoteChatSession

    raw = b"BINARY_BYTES_NOT_A_VALID_IMAGE_AT_ALL"
    p = tmp_path / "frame.png"
    p.write_bytes(raw)

    lines = [(json.dumps({"done": True}) + "\n").encode("utf-8")]
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["data"] = json.loads(req.data.decode("utf-8"))
        return _make_sse_response(*lines)

    prov = OllamaProvider("http://localhost:11434", None)
    sess = RemoteChatSession(prov, "qwen3vl")

    with patch(
        "app.adapters.ai.remote.ollama.urllib.request.urlopen",
        side_effect=fake_urlopen,
    ):
        sess.chat_with_images(
            prompt="x", images=[str(p)],
            max_tokens=10, temperature=0.0,
        )

    sent_b64 = captured["data"]["messages"][0]["images"][0]
    assert base64.b64decode(sent_b64) == raw


# --- kill_process closes stashed response (cross-thread) ---

def test_kill_process_closes_openai_response():
    from app.adapters.ai.remote.openai import OpenAIProvider
    from app.services.llm.remote_chat import RemoteChatSession

    resp = MagicMock(name="HTTPResponse")
    iter_started = threading.Event()
    iter_block = threading.Event()

    def slow_iter():
        iter_started.set()
        iter_block.wait(timeout=5.0)
        yield b'data: [DONE]\n'

    resp.__iter__ = lambda self: slow_iter()
    resp.__enter__ = MagicMock(return_value=resp)
    resp.__exit__ = MagicMock(return_value=False)
    resp.close = MagicMock(side_effect=lambda: iter_block.set())

    prov = OpenAIProvider("https://api.openai.com", "sk-test")
    sess = RemoteChatSession(prov, "gpt-4o-mini")

    def call_chat():
        with patch(
            "app.adapters.ai.remote.openai.urllib.request.urlopen",
            return_value=resp,
        ):
            try:
                sess.chat(
                    messages=[{"role": "user", "content": "x"}],
                    max_tokens=10, temperature=0.0,
                )
            except Exception:
                pass

    t = threading.Thread(target=call_chat)
    t.start()
    iter_started.wait(timeout=2.0)
    sess.kill_process()
    t.join(timeout=3.0)
    assert not t.is_alive()
    resp.close.assert_called()


# --- task kwarg forwarding ---

def test_task_kwarg_forwards_to_provider_chat():
    """RemoteChatSession.chat(task='frame_select') must propagate task to provider."""
    from unittest.mock import MagicMock as _MagicMock
    from app.services.llm.remote_chat import RemoteChatSession

    prov = _MagicMock()
    prov.chat.return_value = "2"
    sess = RemoteChatSession(prov, "test-model")

    sess.chat(
        messages=[{"role": "user", "content": "pick"}],
        max_tokens=16, temperature=0.0,
        task="frame_select",
    )
    call_kwargs = prov.chat.call_args
    assert call_kwargs.kwargs.get("task") == "frame_select", (
        f"task kwarg not forwarded to provider.chat(); got: {call_kwargs.kwargs}"
    )


def test_task_kwarg_forwards_to_provider_chat_with_images(tmp_path):
    """RemoteChatSession.chat_with_images(task='frame_select') must propagate task to provider."""
    from unittest.mock import MagicMock as _MagicMock
    from app.services.llm.remote_chat import RemoteChatSession

    prov = _MagicMock()
    prov.chat_with_images.return_value = "1"
    prov.IMAGE_PREP_MODE = "raw"
    prov.PROVIDER_NAME = "ollama"
    sess = RemoteChatSession(prov, "test-model")

    p = tmp_path / "frame.png"
    p.write_bytes(b"\x89PNG")

    sess.chat_with_images(
        prompt="pick frame",
        images=[str(p)],
        max_tokens=16, temperature=0.0,
        task="frame_select",
    )
    call_kwargs = prov.chat_with_images.call_args
    assert call_kwargs.kwargs.get("task") == "frame_select", (
        f"task kwarg not forwarded to provider.chat_with_images(); got: {call_kwargs.kwargs}"
    )


def test_task_kwarg_defaults_to_none_when_not_passed():
    """When task is omitted, provider receives task=None (default)."""
    from unittest.mock import MagicMock as _MagicMock
    from app.services.llm.remote_chat import RemoteChatSession

    prov = _MagicMock()
    prov.chat.return_value = "OK"
    sess = RemoteChatSession(prov, "test-model")

    sess.chat(
        messages=[{"role": "user", "content": "summarize"}],
        max_tokens=4096, temperature=0.3,
        # no task kwarg
    )
    call_kwargs = prov.chat.call_args
    assert call_kwargs.kwargs.get("task") is None, (
        f"task should be None when not passed; got: {call_kwargs.kwargs.get('task')}"
    )
