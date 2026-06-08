from app.adapters.ai.remote.ollama import OllamaProvider


def test_provider_accepts_chunk_ctx_budget():
    p = OllamaProvider("http://h", None, chunk_ctx_budget=20000)
    assert p._chunk_ctx_budget == 20000


def test_provider_budget_defaults_none():
    p = OllamaProvider("http://h")
    assert p._chunk_ctx_budget is None
    assert p._truncation_warned is False
