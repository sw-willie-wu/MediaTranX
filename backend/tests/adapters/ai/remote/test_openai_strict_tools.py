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
