"""Tests for AGENT_SYSTEM_PROMPT content requirements."""
from __future__ import annotations


def test_no_panel_schema_phantom_in_prompt():
    from app.services.agent._system_prompt import AGENT_SYSTEM_PROMPT
    assert "panel_schema" not in AGENT_SYSTEM_PROMPT
    assert "當前狀態" in AGENT_SYSTEM_PROMPT  # SOP points at the real injected block
