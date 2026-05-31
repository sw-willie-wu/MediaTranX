"""Regression guard for gemma4 e4b GGUF filename casing.

HF repo paths are case-sensitive. The repo ``ggml-org/gemma-4-E4B-it-GGUF``
serves files named ``gemma-4-E4B-it-*.gguf`` (uppercase E4B — verified against
the live repo). The registry previously declared lowercase ``e4b`` filenames,
which 404 on a fresh install (the local file only worked because it was already
downloaded). repo_id already used uppercase E4B; only the filenames disagreed.
"""
from app.adapters.ai.registry import MODELS_REGISTRY, FORMAT_GGUF


def test_gemma4_e4b_filenames_match_uppercase_repo():
    e4b = MODELS_REGISTRY[FORMAT_GGUF]["gemma4"]["specs"]["e4b"]["variants"]["Q4_K_M"]
    # filenames must match the case-sensitive repo_id token (E4B, not e4b)
    assert e4b["repo_id"] == "ggml-org/gemma-4-E4B-it-GGUF"
    assert e4b["filename"] == "gemma-4-E4B-it-Q4_K_M.gguf"
    assert e4b["mmproj_filename"] == "mmproj-gemma-4-E4B-it-bf16.gguf"
    # no lowercase 'e4b' leaked into the download paths
    assert "e4b" not in e4b["filename"]
    assert "e4b" not in e4b["mmproj_filename"]
