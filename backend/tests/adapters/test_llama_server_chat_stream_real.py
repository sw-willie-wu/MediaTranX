"""Real-AI integration test for LlamaServer.chat_stream().

Starts a real llama-server subprocess with qwen3:8b and verifies that:
  1. tool_calls deltas appear in the stream
  2. usage is present in one of the chunks
  3. Accumulated tool arguments parse as valid JSON

Skipped by default unless:
  - ``pytest -m ai`` is passed, AND
  - the qwen3 8B Q4_K_M GGUF file is present on disk, AND
  - llama-server binary exists

Run:
    uv run --extra dev python -m pytest tests/adapters/test_llama_server_chat_stream_real.py -v -m ai
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.ai

# ---------------------------------------------------------------------------
# Model / binary availability guards
# ---------------------------------------------------------------------------

_LLAMA_BINARY_CANDIDATES = [
    Path(__file__).parent.parent.parent / "bin" / "llama" / "llama-server.exe",
    Path(__file__).parent.parent.parent / "bin" / "llama" / "llama-server",
]
_MODEL_CANDIDATES = [
    Path(__file__).parent.parent.parent / "models" / "qwen3" / "Qwen3-8B-Q4_K_M.gguf",
]


def _llama_binary_exists() -> bool:
    return any(p.exists() for p in _LLAMA_BINARY_CANDIDATES)


def _model_exists() -> bool:
    return any(p.exists() for p in _MODEL_CANDIDATES)


def _get_model_path() -> Path:
    for p in _MODEL_CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError("qwen3 8B Q4_K_M model not found")


# ---------------------------------------------------------------------------
# Tool definition (same as SPIKE-B)
# ---------------------------------------------------------------------------

_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "set_field",
            "description": "Set a field on the active panel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "value": {},
                },
                "required": ["field", "value"],
            },
        },
    }
]

_MESSAGES = [
    {"role": "system", "content": "你是 MediaTranX 工具呼叫測試 agent。"},
    {
        "role": "user",
        "content": "請呼叫 set_field 把 model 設為 realesrgan-x4plus",
    },
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestChatStreamRealAI:
    @pytest.fixture(autouse=True)
    def _skip_if_unavailable(self):
        if not _llama_binary_exists():
            pytest.skip("llama-server binary not found")
        if not _model_exists():
            pytest.skip("qwen3 8B Q4_K_M model not found")

    def test_chat_stream_tool_calls_and_usage(self):
        """Real qwen3:8b streaming tool call: verify tool_calls deltas + usage chunk."""
        from app.adapters.binary.llama_server import LlamaServer

        server = LlamaServer()
        model_path = _get_model_path()

        server.start(
            model_path=model_path,
            n_ctx=4096,
            n_gpu_layers=99,
        )
        try:
            chunks = list(server.chat_stream(
                messages=_MESSAGES,
                tools=_TOOLS,
                max_tokens=512,
                temperature=0.1,
            ))
        finally:
            server.stop()

        assert len(chunks) > 0, "No SSE chunks received"

        # AC1: At least one chunk has tool_calls in delta
        tool_call_chunks = [
            c for c in chunks
            if c.get("choices") and
               c["choices"][0].get("delta", {}).get("tool_calls")
        ]
        assert len(tool_call_chunks) >= 1, (
            "Expected at least 1 tool_call delta chunk; "
            f"got {len(tool_call_chunks)}. All chunks: {chunks}"
        )

        # AC2: usage present in the stream (any chunk)
        usage_chunks = [c for c in chunks if c.get("usage")]
        assert len(usage_chunks) >= 1, "No usage chunk in stream"
        usage = usage_chunks[-1]["usage"]
        assert usage.get("prompt_tokens", 0) > 0
        assert usage.get("completion_tokens", 0) > 0

        # AC3: Accumulated tool_call arguments are valid JSON with expected content
        args_buf: dict[int, str] = {}
        name_buf: dict[int, str] = {}
        for chunk in chunks:
            for choice in chunk.get("choices", []):
                for tc in choice.get("delta", {}).get("tool_calls", []):
                    idx = tc.get("index", 0)
                    fn = tc.get("function", {})
                    if fn.get("name"):
                        name_buf[idx] = fn["name"]
                    if fn.get("arguments"):
                        args_buf[idx] = args_buf.get(idx, "") + fn["arguments"]

        assert name_buf.get(0) == "set_field", (
            f"Expected function name 'set_field'; got {name_buf}"
        )

        raw_args = args_buf.get(0, "")
        try:
            parsed = json.loads(raw_args)
        except json.JSONDecodeError as e:
            pytest.fail(f"Tool call arguments are not valid JSON: {e!r}; raw={raw_args!r}")

        assert isinstance(parsed.get("field"), str) and parsed["field"], (
            f"'field' must be a non-empty string; got {parsed!r}"
        )
        assert "x4plus" in str(parsed.get("value", "")).lower(), (
            f"'value' should contain 'x4plus'; got {parsed!r}"
        )
