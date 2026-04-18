"""Unit tests for calc_chunk_budget."""
import pytest
from app.services.audio.transcribe_service.summarize import calc_chunk_budget


def test_basic_half_of_ctx_minus_overhead():
    assert calc_chunk_budget(8000) == 4000 - 200  # 3800


def test_clamped_to_min_tokens():
    assert calc_chunk_budget(n_ctx=1000, min_tokens=500) == 500


def test_output_cap_applies():
    assert calc_chunk_budget(n_ctx=100000, output_cap=10000) == 10000


def test_prompt_overhead_custom():
    assert calc_chunk_budget(n_ctx=8000, prompt_overhead=500) == 3500


def test_zero_ctx_falls_back_to_min():
    assert calc_chunk_budget(n_ctx=0) == 500
