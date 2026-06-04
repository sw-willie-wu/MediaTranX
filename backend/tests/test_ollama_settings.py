import pytest
from pydantic import ValidationError

from app.schemas.ollama_settings import (
    OllamaSettings,
    OllamaSettingsUpdate,
    _NUM_CTX_MIN,
    _NUM_CTX_MAX,
)


def test_defaults_to_8192():
    assert OllamaSettings().ollama_num_ctx_cap == 8192


def test_bounds_constants():
    assert _NUM_CTX_MIN == 4096
    assert _NUM_CTX_MAX == 131072


def test_accepts_min_and_max():
    assert OllamaSettings(ollama_num_ctx_cap=4096).ollama_num_ctx_cap == 4096
    assert OllamaSettings(ollama_num_ctx_cap=131072).ollama_num_ctx_cap == 131072


def test_rejects_below_min():
    with pytest.raises(ValidationError):
        OllamaSettings(ollama_num_ctx_cap=4095)


def test_rejects_above_max():
    with pytest.raises(ValidationError):
        OllamaSettings(ollama_num_ctx_cap=131073)


def test_update_is_optional():
    assert OllamaSettingsUpdate().ollama_num_ctx_cap is None
    assert OllamaSettingsUpdate(ollama_num_ctx_cap=8192).ollama_num_ctx_cap == 8192


def test_update_rejects_out_of_bounds():
    with pytest.raises(ValidationError):
        OllamaSettingsUpdate(ollama_num_ctx_cap=100)
