"""Tests for ApiConnectionDAO chunk_ctx_budget support (sentinel semantics)."""
import pytest
from app.db.dao.api_connection_dao import ApiConnectionDAO


@pytest.fixture
def dao(real_db):
    return ApiConnectionDAO()


def test_create_with_budget(dao):
    c = dao.create(provider="ollama", name="x", endpoint="http://h", chunk_ctx_budget=20000)
    assert c.chunk_ctx_budget == 20000


def test_update_sets_budget(dao):
    c = dao.create(provider="ollama", name="x", endpoint="http://h")
    out = dao.update(c.id, chunk_ctx_budget=16384)
    assert out.chunk_ctx_budget == 16384


def test_update_null_clears_to_auto(dao):
    c = dao.create(provider="ollama", name="x", endpoint="http://h", chunk_ctx_budget=16384)
    out = dao.update(c.id, chunk_ctx_budget=None)  # explicit null -> clear to auto
    assert out.chunk_ctx_budget is None


def test_update_omitted_keeps_budget(dao):
    c = dao.create(provider="ollama", name="x", endpoint="http://h", chunk_ctx_budget=16384)
    out = dao.update(c.id, name="renamed")  # budget omitted -> preserved
    assert out.chunk_ctx_budget == 16384
