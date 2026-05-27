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
