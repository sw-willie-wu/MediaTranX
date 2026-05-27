"""Tests for OpenAI strict-mode tool-call schema adapter.

Spec: core/.claude/specs/2026-05-27-openai-strict-tool-calling-design.md
"""
import json
from unittest.mock import MagicMock, patch

import pytest


class TestStrictifySchemaRoot:
    """Root schema must be a dict declaring type:'object'."""

    def test_raises_on_non_dict_root(self):
        from app.adapters.ai.remote.openai import _strictify_schema

        with pytest.raises(ValueError, match="root must be a dict"):
            _strictify_schema(None)  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="root must be a dict"):
            _strictify_schema("string")  # type: ignore[arg-type]
        with pytest.raises(ValueError, match="root must be a dict"):
            _strictify_schema([])  # type: ignore[arg-type]

    def test_raises_on_root_without_type_object(self):
        from app.adapters.ai.remote.openai import _strictify_schema

        # Empty dict — has no type key
        with pytest.raises(ValueError, match="type:'object'"):
            _strictify_schema({})
        # type:'string' — wrong type
        with pytest.raises(ValueError, match="type:'object'"):
            _strictify_schema({"type": "string"})


class TestStrictifySchemaHappyPath:
    """additionalProperties, required overwrite, primitive + enum preservation."""

    def test_handles_zero_arg_object(self):
        from app.adapters.ai.remote.openai import _strictify_schema

        result = _strictify_schema({"type": "object", "properties": {}})
        assert result == {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        }

    def test_adds_additionalProperties_false(self):
        from app.adapters.ai.remote.openai import _strictify_schema

        result = _strictify_schema({
            "type": "object",
            "properties": {"x": {"type": "string"}},
            "required": ["x"],
        })
        assert result["additionalProperties"] is False

    def test_overwrites_required_to_all_property_keys(self):
        from app.adapters.ai.remote.openai import _strictify_schema

        # Caller forgot to mark `b` as required — adapter normalizes
        result = _strictify_schema({
            "type": "object",
            "properties": {"a": {"type": "string"}, "b": {"type": "number"}},
            "required": ["a"],
        })
        assert set(result["required"]) == {"a", "b"}

    def test_preserves_enum_unchanged(self):
        from app.adapters.ai.remote.openai import _strictify_schema

        schema = {
            "type": "object",
            "properties": {"route": {"type": "string", "enum": ["/a", "/b"]}},
            "required": ["route"],
        }
        result = _strictify_schema(schema)
        assert result["properties"]["route"] == {"type": "string", "enum": ["/a", "/b"]}

    def test_preserves_string_property(self):
        from app.adapters.ai.remote.openai import _strictify_schema

        result = _strictify_schema({
            "type": "object",
            "properties": {"name": {"type": "string"}},
        })
        assert result["properties"]["name"] == {"type": "string"}


class TestStrictifySchemaEmptyValue:
    """The set_field.value fix: untyped {} → primitive anyOf union."""

    def test_replaces_empty_value_with_anyOf_primitive_union(self):
        from app.adapters.ai.remote.openai import _strictify_schema

        schema = {
            "type": "object",
            "properties": {"field": {"type": "string"}, "value": {}},
            "required": ["field", "value"],
        }
        result = _strictify_schema(schema)
        assert result["properties"]["value"] == {
            "anyOf": [
                {"type": "string"},
                {"type": "number"},
                {"type": "boolean"},
                {"type": "null"},
            ]
        }

    def test_anyOf_branches_are_single_type_not_multi_array(self):
        """Sanity: each anyOf branch is a single-type schema (OpenAI strict
        rejects multi-element type arrays like ["string","number"])."""
        from app.adapters.ai.remote.openai import _strictify_schema

        result = _strictify_schema({"type": "object", "properties": {"v": {}}})
        for branch in result["properties"]["v"]["anyOf"]:
            assert isinstance(branch.get("type"), str), \
                f"branch type must be a string, got {branch.get('type')!r}"
            assert "anyOf" not in branch  # No nesting


class TestStrictifySchemaFailLoudly:
    """Unsupported shapes raise ValueError (not silent passthrough)."""

    def test_raises_on_nested_object_in_property(self):
        from app.adapters.ai.remote.openai import _strictify_schema

        schema = {
            "type": "object",
            "properties": {
                "nested": {"type": "object", "properties": {"x": {"type": "string"}}}
            },
        }
        with pytest.raises(ValueError, match="nested object"):
            _strictify_schema(schema)

    def test_raises_on_array_of_object_in_property(self):
        from app.adapters.ai.remote.openai import _strictify_schema

        schema = {
            "type": "object",
            "properties": {
                "items": {"type": "array", "items": {"type": "object", "properties": {}}}
            },
        }
        with pytest.raises(ValueError, match="array-of-object"):
            _strictify_schema(schema)

    def test_raises_on_anyOf_in_property(self):
        from app.adapters.ai.remote.openai import _strictify_schema

        # NB: this is *caller-supplied* anyOf — distinct from the self-inserted
        # primitive union which Task 6 exempts via idempotency guard.
        schema = {
            "type": "object",
            "properties": {"v": {"anyOf": [{"type": "string"}, {"type": "integer"}]}},
        }
        with pytest.raises(ValueError, match="'anyOf'"):
            _strictify_schema(schema)

    def test_raises_on_oneOf_in_property(self):
        from app.adapters.ai.remote.openai import _strictify_schema

        schema = {"type": "object", "properties": {"v": {"oneOf": []}}}
        with pytest.raises(ValueError, match="'oneOf'"):
            _strictify_schema(schema)

    def test_raises_on_allOf_in_property(self):
        from app.adapters.ai.remote.openai import _strictify_schema

        schema = {"type": "object", "properties": {"v": {"allOf": []}}}
        with pytest.raises(ValueError, match="'allOf'"):
            _strictify_schema(schema)

    def test_raises_on_ref_in_property(self):
        from app.adapters.ai.remote.openai import _strictify_schema

        schema = {"type": "object", "properties": {"v": {"$ref": "#/$defs/X"}}}
        with pytest.raises(ValueError, match=r"'\$ref'"):
            _strictify_schema(schema)

    def test_raises_on_defs_in_property(self):
        from app.adapters.ai.remote.openai import _strictify_schema

        schema = {"type": "object", "properties": {"v": {"$defs": {}}}}
        with pytest.raises(ValueError, match=r"'\$defs'"):
            _strictify_schema(schema)

    def test_raises_on_non_dict_property_value(self):
        from app.adapters.ai.remote.openai import _strictify_schema

        schema = {"type": "object", "properties": {"x": "not-a-dict"}}
        with pytest.raises(ValueError, match="not a dict schema"):
            _strictify_schema(schema)


class TestStrictifySchemaIdempotency:
    """Applying _strictify_schema twice produces the same result.

    Critical for the set_field case: the second pass sees self-inserted
    anyOf in the value-slot and must NOT raise (would contradict Task 5's
    anyOf rejection rule).  Self-recognition guard exempts it.
    """

    def test_is_idempotent_for_plain_schema(self):
        from app.adapters.ai.remote.openai import _strictify_schema

        schema = {
            "type": "object",
            "properties": {"route": {"type": "string", "enum": ["/a"]}},
            "required": ["route"],
        }
        once = _strictify_schema(schema)
        twice = _strictify_schema(once)
        assert once == twice

    def test_idempotent_on_set_field_shape(self):
        """Self-inserted anyOf primitive-union passes through the anyOf-reject
        guard via the self-recognition exemption."""
        from app.adapters.ai.remote.openai import _strictify_schema

        schema = {
            "type": "object",
            "properties": {"field": {"type": "string"}, "value": {}},
            "required": ["field", "value"],
        }
        once = _strictify_schema(schema)
        # Sanity: first pass inserted the anyOf
        assert "anyOf" in once["properties"]["value"]
        # Second pass MUST NOT raise (would happen without self-recognition)
        twice = _strictify_schema(once)
        assert once == twice


class TestToOpenAIStrictTools:
    """Wraps AG-UI flat shape into OpenAI nested strict shape."""

    def test_empty_input_returns_empty(self):
        from app.adapters.ai.remote.openai import _to_openai_strict_tools

        assert _to_openai_strict_tools([]) == []

    def test_wraps_flat_with_strict_true(self):
        from app.adapters.ai.remote.openai import _to_openai_strict_tools

        result = _to_openai_strict_tools([
            {
                "name": "navigate_to",
                "description": "Navigate to a route.",
                "parameters": {
                    "type": "object",
                    "properties": {"route": {"type": "string"}},
                    "required": ["route"],
                },
            }
        ])
        assert len(result) == 1
        assert result[0]["type"] == "function"
        fn = result[0]["function"]
        assert fn["name"] == "navigate_to"
        assert fn["description"] == "Navigate to a route."
        assert fn["strict"] is True
        # parameters went through _strictify_schema
        assert fn["parameters"]["additionalProperties"] is False
        assert fn["parameters"]["required"] == ["route"]

    def test_includes_description(self):
        from app.adapters.ai.remote.openai import _to_openai_strict_tools

        result = _to_openai_strict_tools([
            {"name": "x", "description": "DESC", "parameters": {"type": "object"}}
        ])
        assert result[0]["function"]["description"] == "DESC"

    def test_raises_on_caller_built_nested_shape(self):
        from app.adapters.ai.remote.openai import _to_openai_strict_tools

        # Even if the caller built {"type":"function","function":{...}}, refuse it
        # — agent path is flat-only.  Accepting nested risks silently shipping
        # tools without strict:true.
        with pytest.raises(ValueError, match="nested OpenAI shape not accepted"):
            _to_openai_strict_tools([
                {"type": "function", "function": {"name": "x", "description": "y", "parameters": {"type": "object"}, "strict": True}}
            ])

    def test_raises_on_missing_name(self):
        from app.adapters.ai.remote.openai import _to_openai_strict_tools

        with pytest.raises(ValueError, match="missing 'name'"):
            _to_openai_strict_tools([{"description": "d", "parameters": {"type": "object"}}])

    def test_raises_on_missing_description(self):
        from app.adapters.ai.remote.openai import _to_openai_strict_tools

        with pytest.raises(ValueError, match="missing 'description'"):
            _to_openai_strict_tools([{"name": "x", "parameters": {"type": "object"}}])

    def test_raises_on_missing_parameters(self):
        from app.adapters.ai.remote.openai import _to_openai_strict_tools

        with pytest.raises(ValueError, match="missing 'parameters'"):
            _to_openai_strict_tools([{"name": "x", "description": "d"}])


class TestRealShapeSanity:
    """All 9 frontend TOOLS (mirror of useAgentTools.ts:76-160) must pass
    _to_openai_strict_tools without raising, and produce strict-valid wire.
    """

    # Verbatim mirror of core/frontend/src/composables/useAgentTools.ts:76-160
    # If frontend TOOLS changes (name/description/parameters), update this
    # fixture (followup §11 in spec — auto-dump from frontend).
    FRONTEND_TOOLS = [
        {
            "name": "navigate_to",
            "description": "Navigate to a top-level domain view (image/audio/video/document/settings/tasks/home).",
            "parameters": {
                "type": "object",
                "properties": {
                    "route": {
                        "type": "string",
                        "enum": ["/", "/image", "/audio", "/video", "/document", "/settings", "/tasks"],
                    },
                },
                "required": ["route"],
            },
        },
        {
            "name": "select_subfunction",
            "description": 'Select a sub-function within the current view (e.g. "upscale", "transcode"). For settings, also selects tab.',
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
        {
            "name": "load_file",
            "description": "Set the active file by file_id. Use list_files first to discover ids.",
            "parameters": {
                "type": "object",
                "properties": {"file_id": {"type": "string"}},
                "required": ["file_id"],
            },
        },
        {
            "name": "list_files",
            "description": "List currently uploaded files. Returns array of {id, name, kind, size_bytes}.",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "open_dropdown",
            "description": "Open a dropdown field on the active panel (educational/optional, for visibility).",
            "parameters": {
                "type": "object",
                "properties": {"field": {"type": "string"}},
                "required": ["field"],
            },
        },
        {
            "name": "set_field",
            "description": "Set a field on the active panel. Field name & valid values are in state.panel_schema.",
            "parameters": {
                "type": "object",
                "properties": {"field": {"type": "string"}, "value": {}},
                "required": ["field", "value"],
            },
        },
        {
            "name": "click_execute",
            "description": "Submit the active panel's task with the currently set fields.",
            "parameters": {"type": "object", "properties": {}},
        },
        {
            "name": "click_action",
            "description": "Invoke a named action button on the active panel/settings (browse, download, restart, delete...).",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
        },
        {
            "name": "get_task_status",
            "description": "Get current status of a submitted task by id.",
            "parameters": {
                "type": "object",
                "properties": {"task_id": {"type": "string"}},
                "required": ["task_id"],
            },
        },
    ]

    def test_all_9_tools_pass_strictify_without_raising(self):
        from app.adapters.ai.remote.openai import _to_openai_strict_tools

        wire = _to_openai_strict_tools(self.FRONTEND_TOOLS)
        assert len(wire) == 9
        for entry in wire:
            assert entry["type"] == "function"
            assert entry["function"]["strict"] is True

    def test_set_field_value_wire_shape_is_anyOf_4_branches(self):
        from app.adapters.ai.remote.openai import _to_openai_strict_tools

        wire = _to_openai_strict_tools(self.FRONTEND_TOOLS)
        set_field = next(e for e in wire if e["function"]["name"] == "set_field")
        value_schema = set_field["function"]["parameters"]["properties"]["value"]
        assert "anyOf" in value_schema
        assert len(value_schema["anyOf"]) == 4
        types = {b["type"] for b in value_schema["anyOf"]}
        assert types == {"string", "number", "boolean", "null"}

    def test_navigate_to_enum_preserved_after_strictify(self):
        from app.adapters.ai.remote.openai import _to_openai_strict_tools

        wire = _to_openai_strict_tools(self.FRONTEND_TOOLS)
        nav = next(e for e in wire if e["function"]["name"] == "navigate_to")
        route_schema = nav["function"]["parameters"]["properties"]["route"]
        assert route_schema["type"] == "string"
        assert "/video" in route_schema["enum"]

    def test_zero_arg_tools_wire_shape_has_empty_required(self):
        from app.adapters.ai.remote.openai import _to_openai_strict_tools

        wire = _to_openai_strict_tools(self.FRONTEND_TOOLS)
        for name in ("list_files", "click_execute"):
            tool = next(e for e in wire if e["function"]["name"] == name)
            params = tool["function"]["parameters"]
            assert params["properties"] == {}
            assert params["required"] == []
            assert params["additionalProperties"] is False

    def test_every_tool_satisfies_strict_invariants(self):
        """Generic invariant: every wire tool has additionalProperties:false,
        required = list(properties.keys()), and no empty {} value-slot."""
        from app.adapters.ai.remote.openai import _to_openai_strict_tools

        wire = _to_openai_strict_tools(self.FRONTEND_TOOLS)
        for entry in wire:
            params = entry["function"]["parameters"]
            assert params["additionalProperties"] is False, entry["function"]["name"]
            assert set(params["required"]) == set(params["properties"].keys()), \
                entry["function"]["name"]
            for prop_name, prop_schema in params["properties"].items():
                assert prop_schema != {}, f"{entry['function']['name']}.{prop_name}"
