"""set_num_ctx_cap live-updates the ceiling _compute_num_ctx uses.

Module-state teardown: every test restores the original _NUM_CTX_CAP via the
_restore_cap fixture so we never leak into test_ollama.py's clamp tests."""
import pytest

import app.adapters.ai.remote.ollama as ol


@pytest.fixture(autouse=True)
def _restore_cap():
    original = ol._NUM_CTX_CAP
    yield
    ol._NUM_CTX_CAP = original


def test_setter_updates_module_global():
    ol.set_num_ctx_cap(16384)
    assert ol._NUM_CTX_CAP == 16384


def test_setter_coerces_to_int():
    ol.set_num_ctx_cap("32768")  # str → int (DB/JSON round-trips can be loose)
    assert ol._NUM_CTX_CAP == 32768


def test_live_apply_raises_ceiling():
    ol.set_num_ctx_cap(32768)
    msgs = [{"role": "user", "content": "x" * 60000}]  # ~20k tokens
    n = ol._compute_num_ctx(msgs, max_tokens=2048, model_ctx=0)
    assert n > 8192 and n <= 32768


def test_live_apply_lowers_ceiling():
    ol.set_num_ctx_cap(4096)
    msgs = [{"role": "user", "content": "x" * 60000}]
    assert ol._compute_num_ctx(msgs, max_tokens=2048, model_ctx=0) == 4096


def test_cap_cannot_bypass_model_ctx_clamp():
    ol.set_num_ctx_cap(131072)
    msgs = [{"role": "user", "content": "x" * 60000}]
    assert ol._compute_num_ctx(msgs, max_tokens=2048, model_ctx=8192) == 8192
