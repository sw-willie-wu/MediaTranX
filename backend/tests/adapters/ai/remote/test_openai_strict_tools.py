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
