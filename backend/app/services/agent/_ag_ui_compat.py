"""Centralized ag-ui-protocol imports + helpers.

All ag_ui.* imports live here so future SDK changes only touch this module.

WIRE FORMAT NOTE: ag-ui-protocol's EventEncoder serializes with Pydantic
by_alias=True, producing camelCase JSON keys (e.g., 'runId', 'messageId').
Python constructor kwargs remain snake_case (e.g., run_id=..., thread_id=...).
"""
from __future__ import annotations

from ag_ui.core import (
    RunAgentInput,
    RunStartedEvent,
    RunFinishedEvent,
    RunErrorEvent,
    TextMessageChunkEvent,
    ToolCallChunkEvent,
)
from ag_ui.encoder import EventEncoder


def make_encoder(accept: str | None = None) -> EventEncoder:
    """Return an EventEncoder.

    `accept` mirrors the HTTP Accept header (typically 'text/event-stream').
    None defaults to text/event-stream per SDK behavior.
    """
    return EventEncoder(accept=accept)


def emit_run_finished_with_usage(
    encoder: EventEncoder,
    run_id: str,
    thread_id: str,
    usage: dict | None = None,
) -> str:
    """Encode a RunFinishedEvent, optionally attaching usage as a Pydantic
    extras field (the SDK uses model_config.extra = 'allow', so extra
    fields round-trip through encode() naturally — no manual SSE framing).

    Args:
        encoder: EventEncoder instance (re-use across one round).
        run_id: matches the RunStartedEvent.
        thread_id: matches the RunStartedEvent (REQUIRED, per SDK).
        usage: optional dict {'prompt_tokens': int, 'completion_tokens': int}
               -> wire becomes {'promptTokens': ..., 'completionTokens': ...}
               via by_alias=True. None / missing keys -> no usage in wire.
    """
    kwargs: dict = {"run_id": run_id, "thread_id": thread_id}
    if usage:
        # Map python snake_case -> camelCase via direct construction.
        # Pydantic by_alias=True handles all alias resolution at serialize time.
        kwargs["usage"] = {
            "promptTokens": usage.get("prompt_tokens", 0),
            "completionTokens": usage.get("completion_tokens", 0),
        }
    event = RunFinishedEvent(**kwargs)
    return encoder.encode(event)


__all__ = [
    "RunAgentInput",
    "RunStartedEvent",
    "RunFinishedEvent",
    "RunErrorEvent",
    "TextMessageChunkEvent",
    "ToolCallChunkEvent",
    "EventEncoder",
    "make_encoder",
    "emit_run_finished_with_usage",
]
