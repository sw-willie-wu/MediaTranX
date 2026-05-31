"""Unit tests for Gemini tools/messages converter helpers.

Covers:
- _to_gemini_tools: happy path (1 tool), empty input
- _convert_jsonschema_to_gemini: nested object, uppercase types, recursive props
- _convert_jsonschema_to_gemini: drops oneOf / anyOf with a warning
- _to_gemini_messages: assistant with text + tool_calls → mixed model parts
- _to_gemini_messages: tool result → role='function' with name lookup
- _to_gemini_messages: system message → returned as systemInstruction
- _to_gemini_messages: camelCase 'toolCalls' AND snake_case 'tool_calls' accepted
"""
import json
import logging

import pytest


# ── helpers ──────────────────────────────────────────────────────────────────

def _tools():
    from app.adapters.ai.remote.gemini import _to_gemini_tools, _convert_jsonschema_to_gemini
    return _to_gemini_tools, _convert_jsonschema_to_gemini


def _msgs():
    from app.adapters.ai.remote.gemini import _to_gemini_messages
    return _to_gemini_messages


# ── _to_gemini_tools ─────────────────────────────────────────────────────────

class TestToGeminiTools:
    def test_empty_returns_empty(self):
        to_gemini_tools, _ = _tools()
        assert to_gemini_tools([]) == []
        assert to_gemini_tools(None) == []  # type: ignore[arg-type]

    def test_single_tool_produces_function_declarations_block(self):
        to_gemini_tools, _ = _tools()
        tools = [{
            "name": "navigate_to",
            "description": "Navigate to a route",
            "parameters": {
                "type": "object",
                "properties": {
                    "route": {"type": "string", "description": "The target route"},
                },
                "required": ["route"],
            },
        }]
        result = to_gemini_tools(tools)
        assert len(result) == 1
        decls = result[0]["functionDeclarations"]
        assert len(decls) == 1
        d = decls[0]
        assert d["name"] == "navigate_to"
        assert d["description"] == "Navigate to a route"
        assert d["parameters"]["type"] == "OBJECT"
        assert d["parameters"]["properties"]["route"]["type"] == "STRING"
        assert d["parameters"]["required"] == ["route"]

    def test_multiple_tools_in_single_declarations_block(self):
        to_gemini_tools, _ = _tools()
        tools = [
            {"name": "foo", "description": "Foo", "parameters": {}},
            {"name": "bar", "description": "Bar", "parameters": {}},
        ]
        result = to_gemini_tools(tools)
        # All declarations must be in the SAME block
        assert len(result) == 1
        assert len(result[0]["functionDeclarations"]) == 2

    def test_missing_description_defaults_to_empty_string(self):
        to_gemini_tools, _ = _tools()
        tools = [{"name": "noDesc", "parameters": {"type": "object", "properties": {}}}]
        result = to_gemini_tools(tools)
        assert result[0]["functionDeclarations"][0]["description"] == ""


# ── _convert_jsonschema_to_gemini ─────────────────────────────────────────────

class TestConvertJsonSchemaToGemini:
    def test_object_type_uppercased(self):
        _, convert = _tools()
        result = convert({"type": "object", "properties": {}})
        assert result["type"] == "OBJECT"

    def test_all_primitive_types_uppercased(self):
        _, convert = _tools()
        for lower, upper in [
            ("string", "STRING"),
            ("number", "NUMBER"),
            ("integer", "INTEGER"),
            ("boolean", "BOOLEAN"),
            ("array", "ARRAY"),
        ]:
            assert convert({"type": lower})["type"] == upper

    def test_nested_properties_recursed(self):
        _, convert = _tools()
        schema = {
            "type": "object",
            "properties": {
                "inner": {
                    "type": "object",
                    "properties": {
                        "leaf": {"type": "string"},
                    },
                },
            },
        }
        result = convert(schema)
        assert result["properties"]["inner"]["type"] == "OBJECT"
        assert result["properties"]["inner"]["properties"]["leaf"]["type"] == "STRING"

    def test_array_items_recursed(self):
        _, convert = _tools()
        schema = {"type": "array", "items": {"type": "integer"}}
        result = convert(schema)
        assert result["type"] == "ARRAY"
        assert result["items"]["type"] == "INTEGER"

    def test_enum_preserved(self):
        _, convert = _tools()
        result = convert({"type": "string", "enum": ["a", "b"]})
        assert result["enum"] == ["a", "b"]

    def test_required_preserved(self):
        _, convert = _tools()
        result = convert({"type": "object", "required": ["x"], "properties": {}})
        assert result["required"] == ["x"]

    def test_oneof_dropped_with_warning(self, caplog):
        _, convert = _tools()
        with caplog.at_level(logging.WARNING, logger="app.adapters.ai.remote.gemini"):
            result = convert({"oneOf": [{"type": "string"}, {"type": "integer"}]})
        assert "oneOf" not in result
        assert any("oneOf" in r.message for r in caplog.records)

    def test_anyof_dropped_with_warning(self, caplog):
        _, convert = _tools()
        with caplog.at_level(logging.WARNING, logger="app.adapters.ai.remote.gemini"):
            result = convert({"anyOf": [{"type": "string"}]})
        assert "anyOf" not in result
        assert any("anyOf" in r.message for r in caplog.records)

    def test_unknown_type_excluded(self):
        _, convert = _tools()
        # "null" is not in Gemini's supported types
        result = convert({"type": "null"})
        assert "type" not in result

    def test_title_and_extra_keys_dropped(self):
        _, convert = _tools()
        result = convert({"type": "string", "title": "Foo", "examples": ["x"]})
        assert "title" not in result
        assert "examples" not in result
        assert result["type"] == "STRING"


# ── _to_gemini_messages ───────────────────────────────────────────────────────

class TestToGeminiMessages:
    def test_user_message(self):
        msgs = _msgs()
        system, contents = msgs([{"role": "user", "content": "Hello"}])
        assert system is None
        assert len(contents) == 1
        assert contents[0]["role"] == "user"
        assert contents[0]["parts"] == [{"text": "Hello"}]

    def test_system_message_extracted_not_in_contents(self):
        msgs = _msgs()
        system, contents = msgs([
            {"role": "system", "content": "You are helpful."},
            {"role": "user", "content": "hi"},
        ])
        assert system == "You are helpful."
        assert all(c["role"] != "system" for c in contents)
        assert len(contents) == 1

    def test_assistant_text_only(self):
        msgs = _msgs()
        _, contents = msgs([
            {"role": "user", "content": "q"},
            {"role": "assistant", "content": "answer"},
        ])
        model_msg = next(c for c in contents if c["role"] == "model")
        assert model_msg["parts"] == [{"text": "answer"}]

    def test_assistant_with_tool_calls_camel_case(self):
        msgs = _msgs()
        _, contents = msgs([
            {"role": "user", "content": "q"},
            {
                "role": "assistant",
                "content": "Let me call a tool.",
                "toolCalls": [{
                    "id": "tc1",
                    "function": {"name": "my_tool", "arguments": '{"x": 1}'},
                }],
            },
        ])
        model_msg = next(c for c in contents if c["role"] == "model")
        assert len(model_msg["parts"]) == 2
        assert model_msg["parts"][0] == {"text": "Let me call a tool."}
        fc = model_msg["parts"][1]["functionCall"]
        assert fc["name"] == "my_tool"
        assert fc["args"] == {"x": 1}

    def test_assistant_with_tool_calls_snake_case(self):
        msgs = _msgs()
        _, contents = msgs([
            {"role": "user", "content": "q"},
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": "tc2",
                    "function": {"name": "snake_tool", "arguments": '{"y": 2}'},
                }],
            },
        ])
        model_msg = next(c for c in contents if c["role"] == "model")
        # content is None so no text part
        assert len(model_msg["parts"]) == 1
        assert model_msg["parts"][0]["functionCall"]["name"] == "snake_tool"

    def test_tool_result_uses_name_from_prior_assistant(self):
        msgs = _msgs()
        _, contents = msgs([
            {"role": "user", "content": "q"},
            {
                "role": "assistant",
                "content": None,
                "toolCalls": [{
                    "id": "tc3",
                    "function": {"name": "lookup_info", "arguments": "{}"},
                }],
            },
            {
                "role": "tool",
                "toolCallId": "tc3",
                "content": '{"result": "found it"}',
            },
        ])
        fn_msg = next(c for c in contents if c["role"] == "function")
        fr = fn_msg["parts"][0]["functionResponse"]
        assert fr["name"] == "lookup_info"
        assert fr["response"] == {"result": "found it"}

    def test_tool_result_snake_case_tool_call_id(self):
        msgs = _msgs()
        _, contents = msgs([
            {"role": "user", "content": "q"},
            {
                "role": "assistant",
                "content": None,
                "toolCalls": [{"id": "tc4", "function": {"name": "my_fn", "arguments": "{}"}}],
            },
            {"role": "tool", "tool_call_id": "tc4", "content": '{"ok": true}'},
        ])
        fn_msg = next(c for c in contents if c["role"] == "function")
        assert fn_msg["parts"][0]["functionResponse"]["name"] == "my_fn"

    def test_tool_result_unknown_id_falls_back(self):
        msgs = _msgs()
        _, contents = msgs([
            {"role": "user", "content": "q"},
            {"role": "tool", "toolCallId": "nonexistent", "content": '{}'},
        ])
        fn_msg = next(c for c in contents if c["role"] == "function")
        assert fn_msg["parts"][0]["functionResponse"]["name"] == "unknown_tool"

    def test_tool_result_non_json_content_wrapped(self):
        msgs = _msgs()
        _, contents = msgs([
            {"role": "user", "content": "q"},
            {
                "role": "assistant",
                "content": None,
                "toolCalls": [{"id": "tc5", "function": {"name": "t", "arguments": "{}"}}],
            },
            {"role": "tool", "toolCallId": "tc5", "content": "plain string result"},
        ])
        fn_msg = next(c for c in contents if c["role"] == "function")
        assert fn_msg["parts"][0]["functionResponse"]["response"] == {"content": "plain string result"}

    def test_no_system_returns_none(self):
        msgs = _msgs()
        system, _ = msgs([{"role": "user", "content": "x"}])
        assert system is None
