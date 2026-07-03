"""Tests for AGENT_SYSTEM_PROMPT content requirements."""
from __future__ import annotations


def test_no_panel_schema_phantom_in_prompt():
    from app.services.agent._system_prompt import AGENT_SYSTEM_PROMPT
    assert "panel_schema" not in AGENT_SYSTEM_PROMPT
    assert "當前狀態" in AGENT_SYSTEM_PROMPT  # SOP points at the real injected block


def test_prompt_requires_toolcall_in_same_message():
    """語氣段須要求：敘述動作時同一則訊息發 tool call；移除誘導拆輪的舊措辭。"""
    from app.services.agent._system_prompt import AGENT_SYSTEM_PROMPT
    # 新契約措辭在
    assert "同一則" in AGENT_SYSTEM_PROMPT
    assert "不要只用文字" in AGENT_SYSTEM_PROMPT
    # 舊的「先敘述後動作」誘導措辭移除
    assert "每個 step 之前一句話" not in AGENT_SYSTEM_PROMPT
