"""Tests for LanguageService — language/style metadata + model status passthrough."""
from __future__ import annotations
from unittest.mock import MagicMock

from app.services.llm.language_service import LanguageService


def _make_svc(get_model_path_return=None, llama_ready=True):
    mm = MagicMock()
    mm.is_llama_ready.return_value = llama_ready
    mm.get_model_path.return_value = get_model_path_return
    return LanguageService(model_manager=mm), mm


class TestMetadataQueries:
    def test_get_whisper_languages_returns_list_of_dicts(self):
        svc, _ = _make_svc()
        result = svc.get_whisper_languages()
        assert isinstance(result, list)
        assert result and all(isinstance(item, dict) for item in result)

    def test_get_supported_languages_returns_list_of_dicts(self):
        svc, _ = _make_svc()
        result = svc.get_supported_languages()
        assert isinstance(result, list)
        assert all(isinstance(item, dict) for item in result)

    def test_get_translate_styles_returns_list_of_dicts(self):
        svc, _ = _make_svc()
        result = svc.get_translate_styles()
        assert isinstance(result, list)
        assert all(isinstance(item, dict) for item in result)

    def test_get_whisper_to_bcp47_returns_mapping(self):
        svc, _ = _make_svc()
        result = svc.get_whisper_to_bcp47()
        assert isinstance(result, dict)
        # whisper uses zh for Chinese; BCP47 maps it to a region-specific code
        assert "zh" in result

    def test_get_default_vlm_model_returns_string(self):
        svc, _ = _make_svc()
        assert isinstance(svc.get_default_vlm_model(), str)

    def test_get_lang_names_en_returns_dict(self):
        svc, _ = _make_svc()
        result = svc.get_lang_names_en()
        assert isinstance(result, dict)
        assert "en" in result


class TestGetModelStatus:
    def test_returns_status_with_downloaded_true(self):
        svc, mm = _make_svc(get_model_path_return="/fake/path.gguf", llama_ready=True)
        result = svc.get_model_status(model_family="qwen3", model_size="8b", quantization="Q4_K_M")
        assert result["available"] is True
        assert result["model_downloaded"] is True
        assert result["model_size"] == "8b"
        # Variant passed with colon when quantization given
        mm.get_model_path.assert_called_with("qwen3", "8b:Q4_K_M")

    def test_returns_status_without_quantization(self):
        svc, mm = _make_svc()
        svc.get_model_status(model_family="qwen3", model_size="8b")
        # No colon when quantization is None — uses size only
        mm.get_model_path.assert_called_with("qwen3", "8b")

    def test_returns_status_with_download_false(self):
        svc, _ = _make_svc(get_model_path_return=None)
        result = svc.get_model_status(model_family="qwen3", model_size="8b")
        assert result["model_downloaded"] is False

    def test_returns_status_with_llama_not_ready(self):
        svc, _ = _make_svc(llama_ready=False)
        result = svc.get_model_status(model_family="qwen3", model_size="8b")
        assert result["available"] is False


class TestGetVlmStatus:
    def test_returns_vlm_status_with_quantization(self):
        svc, mm = _make_svc(get_model_path_return="/fake/vlm.gguf")
        result = svc.get_vlm_status(model_family="qwen3vl", size="8b", quantization="Q4_K_M")
        assert result["available"] is True
        assert result["model_family"] == "qwen3vl"
        assert result["size"] == "8b"
        assert result["model_downloaded"] is True
        mm.get_model_path.assert_called_with("qwen3vl", "8b:Q4_K_M")

    def test_returns_vlm_not_downloaded(self):
        svc, _ = _make_svc(get_model_path_return=None)
        result = svc.get_vlm_status(model_family="qwen3vl", size="8b")
        assert result["model_downloaded"] is False
