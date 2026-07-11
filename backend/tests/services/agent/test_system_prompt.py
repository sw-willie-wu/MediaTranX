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


def test_prompt_settings_no_apply_step():
    """設定頁規則：set_field 即生效、不問套用、不 click_execute。"""
    from app.services.agent._system_prompt import AGENT_SYSTEM_PROMPT
    assert "settings." in AGENT_SYSTEM_PROMPT
    assert "已設定完成" in AGENT_SYSTEM_PROMPT
    assert "設定頁沒有" in AGENT_SYSTEM_PROMPT


def test_no_pipeline_variant_strips_pipeline_content():
    from app.services.agent._system_prompt import AGENT_SYSTEM_PROMPT_NO_PIPELINE
    assert "create_pipeline" not in AGENT_SYSTEM_PROMPT_NO_PIPELINE
    assert "run_pipeline" not in AGENT_SYSTEM_PROMPT_NO_PIPELINE
    assert "多步驟串接" not in AGENT_SYSTEM_PROMPT_NO_PIPELINE
    # 通用指引段（原 :43）必須保留
    assert "當前狀態" in AGENT_SYSTEM_PROMPT_NO_PIPELINE
    assert "select_subfunction` 切過去" in AGENT_SYSTEM_PROMPT_NO_PIPELINE


def test_full_variant_keeps_pipeline_content():
    from app.services.agent._system_prompt import AGENT_SYSTEM_PROMPT
    assert "create_pipeline" in AGENT_SYSTEM_PROMPT
    assert "多步驟串接" in AGENT_SYSTEM_PROMPT


def test_count_wording_removed_in_both():
    from app.services.agent._system_prompt import (
        AGENT_SYSTEM_PROMPT,
        AGENT_SYSTEM_PROMPT_NO_PIPELINE,
    )
    assert "11 個 tool" not in AGENT_SYSTEM_PROMPT
    assert "11 個 tool" not in AGENT_SYSTEM_PROMPT_NO_PIPELINE


def test_pick_system_prompt():
    from app.services.agent._system_prompt import (
        AGENT_SYSTEM_PROMPT,
        AGENT_SYSTEM_PROMPT_NO_PIPELINE,
        pick_system_prompt,
    )
    assert pick_system_prompt({"create_pipeline", "navigate_to"}) == AGENT_SYSTEM_PROMPT
    assert pick_system_prompt({"navigate_to"}) == AGENT_SYSTEM_PROMPT_NO_PIPELINE
    assert pick_system_prompt(set()) == AGENT_SYSTEM_PROMPT_NO_PIPELINE
