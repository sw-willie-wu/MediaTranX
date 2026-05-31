"""SPIKE-A: ag-ui-protocol 0.1.18 sanity check.

Run: uv run python scripts/_spike_agent_a_ag_ui.py
(from core/backend directory)

Verified API surface (0.1.18):
- All event classes: direct kwargs (snake_case) work fine (populate_by_name=True)
- model_config: extra='allow', alias_generator=to_camel, populate_by_name=True
- EventEncoder(accept=None) — accept=None means accept anything
- EventEncoder.encode(event) -> str (SSE data line)
"""
from ag_ui.core import (
    RunStartedEvent,
    TextMessageChunkEvent,
    ToolCallChunkEvent,
    RunFinishedEvent,
    RunErrorEvent,
)
from ag_ui.encoder import EventEncoder
import json

enc = EventEncoder(accept=None)

events = [
    RunStartedEvent(run_id="r1", thread_id="t1"),
    TextMessageChunkEvent(message_id="m1", role="assistant", delta="hi"),
    ToolCallChunkEvent(
        tool_call_id="tc1",
        tool_call_name="navigate_to",
        parent_message_id="m1",
        delta='{"route":"/video"}',
    ),
    RunFinishedEvent(run_id="r1", thread_id="t1"),
    RunErrorEvent(code="agent.error.no_model", message="missing"),
]

print("=== Event serialization test ===")
for e in events:
    out = enc.encode(e)
    print(out)
    assert "data:" in out, f"No 'data:' in output: {out!r}"
    # Wire MUST be camelCase per PyPI README
    if isinstance(e, RunStartedEvent):
        assert "runId" in out and "threadId" in out, f"snake_case detected: {out!r}"
        assert "run_id" not in out, f"snake_case run_id in wire: {out!r}"
    if isinstance(e, TextMessageChunkEvent):
        assert "messageId" in out, f"Missing messageId (snake_case?): {out!r}"
        assert "message_id" not in out, f"snake_case message_id in wire: {out!r}"
    if isinstance(e, ToolCallChunkEvent):
        assert "toolCallId" in out, f"Missing toolCallId: {out!r}"
        assert "toolCallName" in out, f"Missing toolCallName: {out!r}"
        assert "parentMessageId" in out, f"Missing parentMessageId: {out!r}"

# Usage extras test: extra='allow' means RunFinishedEvent accepts extra fields
print("=== Usage extras test ===")
finished_with_usage = RunFinishedEvent(run_id="r2", thread_id="t2", usage={"promptTokens": 100, "completionTokens": 50})
print(f"extra field stored: {finished_with_usage.usage}")  # type: ignore[attr-defined]

# model_dump with by_alias includes camelCase keys + extras
finished_dict = finished_with_usage.model_dump(by_alias=True, exclude_none=True)
print(f"model_dump result: {finished_dict}")
assert "usage" in finished_dict, "usage extra field not in model_dump"

# Encode via EventEncoder — extras should be present in wire JSON
encoded_finished = enc.encode(finished_with_usage)
print(f"Encoded with usage extra: {encoded_finished}")

# Also confirm manual SSE frame construction works as fallback
manual_sse = f"event: RUN_FINISHED\ndata: {json.dumps(finished_dict)}\n\n"
print(f"Manual SSE frame: {manual_sse}")
manual_data = json.loads(manual_sse.split("data: ", 1)[1].strip())
assert "usage" in manual_data, "usage not in manual SSE data"
assert "runId" in manual_data, "runId not in manual SSE camelCase"

print("SPIKE-A PASS")
