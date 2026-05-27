"""Tests for ag_ui compat layer and system prompt.

Verifies:
- All 5 ag-ui event types import correctly
- EventEncoder produces camelCase wire keys (by_alias=True)
- emit_run_finished_with_usage attaches usage extras
- AGENT_SYSTEM_PROMPT is present and well-formed
"""
from __future__ import annotations

import json

from app.services.agent._ag_ui_compat import (
    RunErrorEvent,
    RunFinishedEvent,
    RunStartedEvent,
    TextMessageChunkEvent,
    ToolCallChunkEvent,
    emit_run_finished_with_usage,
    make_encoder,
)


class TestImports:
    """Smoke test that all 5 events + encoder import correctly."""

    def test_all_events_importable(self):
        # If import statement above succeeded, this passes
        assert RunStartedEvent and TextMessageChunkEvent and ToolCallChunkEvent
        assert RunFinishedEvent and RunErrorEvent
        assert make_encoder is not None


class TestCamelCaseWire:
    """All 5 events MUST serialize with camelCase JSON keys (Pydantic
    by_alias=True). Frontend SSE parser depends on this."""

    def setup_method(self):
        self.enc = make_encoder(accept=None)

    def test_run_started_camel_case(self):
        out = self.enc.encode(RunStartedEvent(run_id="r1", thread_id="t1"))
        assert "runId" in out
        assert "threadId" in out
        assert "run_id" not in out  # negative — no snake_case leak

    def test_text_message_chunk_camel_case(self):
        out = self.enc.encode(TextMessageChunkEvent(
            message_id="m1", role="assistant", delta="hi"))
        assert "messageId" in out
        assert "message_id" not in out

    def test_tool_call_chunk_camel_case(self):
        out = self.enc.encode(ToolCallChunkEvent(
            tool_call_id="tc1", tool_call_name="navigate_to",
            parent_message_id="m1", delta='{"x":1}'))
        assert "toolCallId" in out
        assert "toolCallName" in out
        assert "parentMessageId" in out

    def test_run_finished_camel_case(self):
        # RunFinishedEvent requires both run_id AND thread_id (per SPIKE-A
        # findings — spec §5.1 originally said only run_id, was wrong).
        out = self.enc.encode(RunFinishedEvent(run_id="r1", thread_id="t1"))
        assert "runId" in out and "threadId" in out

    def test_run_error_basic(self):
        out = self.enc.encode(RunErrorEvent(code="agent.error.no_model", message="x"))
        assert "code" in out and "message" in out


class TestEmitWithUsage:
    """emit_run_finished_with_usage attaches usage extras via Pydantic
    extra='allow' — wire payload contains promptTokens/completionTokens."""

    def test_with_usage(self):
        enc = make_encoder()
        out = emit_run_finished_with_usage(
            enc, run_id="r1", thread_id="t1",
            usage={"prompt_tokens": 100, "completion_tokens": 50},
        )
        # Extract the JSON data line and parse
        data_line = next(
            line[len("data: "):] for line in out.split("\n") if line.startswith("data: ")
        )
        payload = json.loads(data_line)
        assert payload["runId"] == "r1"
        assert payload["threadId"] == "t1"
        assert payload["usage"] == {"promptTokens": 100, "completionTokens": 50}

    def test_without_usage(self):
        enc = make_encoder()
        out = emit_run_finished_with_usage(enc, run_id="r1", thread_id="t1")
        data_line = next(
            line[len("data: "):] for line in out.split("\n") if line.startswith("data: ")
        )
        payload = json.loads(data_line)
        assert "usage" not in payload  # absent when not supplied

    def test_partial_usage_defaults_zero(self):
        enc = make_encoder()
        out = emit_run_finished_with_usage(
            enc, run_id="r1", thread_id="t1",
            usage={"prompt_tokens": 100},  # missing completion
        )
        data_line = next(
            line[len("data: "):] for line in out.split("\n") if line.startswith("data: ")
        )
        payload = json.loads(data_line)
        assert payload["usage"] == {"promptTokens": 100, "completionTokens": 0}


class TestSystemPrompt:
    """_system_prompt.py exposes AGENT_SYSTEM_PROMPT."""

    def test_import(self):
        from app.services.agent._system_prompt import AGENT_SYSTEM_PROMPT
        assert isinstance(AGENT_SYSTEM_PROMPT, str)
        assert len(AGENT_SYSTEM_PROMPT) > 200  # ~350 char target
        assert "navigate_to" in AGENT_SYSTEM_PROMPT  # mentions tool names
        assert "set_field" in AGENT_SYSTEM_PROMPT
        assert "click_execute" in AGENT_SYSTEM_PROMPT
