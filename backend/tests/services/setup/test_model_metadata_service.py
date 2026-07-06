"""Tests for ModelMetadataService — registry enumeration + download state."""
from __future__ import annotations
from unittest.mock import MagicMock

import pytest

from app.services.setup.model_metadata_service import (
    ModelMetadataService,
    MODEL_CATEGORIES,
    _CATEGORY_MAP,
)


@pytest.fixture
def svc():
    """ModelMetadataService with a stubbed ModelManager.

    `manager.get_model_path` is what determines `downloaded` for PTH/GGUF
    families — make it return None by default (not-downloaded) so tests
    don't depend on what's actually on disk.
    """
    mm = MagicMock()
    mm.get_model_path.return_value = None
    return ModelMetadataService(model_manager=mm)


class TestListAll:
    def test_returns_categories_and_models_keys(self, svc):
        result = svc.list_all()
        assert "categories" in result
        assert "models" in result
        assert isinstance(result["models"], list)
        assert result["categories"] == MODEL_CATEGORIES

    def test_models_have_required_fields(self, svc):
        result = svc.list_all()
        for m in result["models"]:
            for key in ("id", "family", "category", "label", "downloaded"):
                assert key in m, f"model {m.get('id')} missing {key!r}"

    def test_categories_mapped_to_parent_tabs(self, svc):
        result = svc.list_all()
        valid_top_cats = {c["key"] for c in MODEL_CATEGORIES}
        for m in result["models"]:
            assert m["category"] in valid_top_cats, (
                f"model {m['id']} category={m['category']!r} not in {valid_top_cats}"
            )

    def test_subcategory_preserves_original(self, svc):
        """subcategory field is the original (frontend filtering); category is
        the parent tab (upscale → image, stt → audio, etc.)."""
        result = svc.list_all()
        for m in result["models"]:
            if m["subcategory"] in _CATEGORY_MAP:
                assert m["category"] == _CATEGORY_MAP[m["subcategory"]]


class TestPthEnumeration:
    def test_includes_realesrgan(self, svc):
        result = svc.list_all()
        ids = [m["id"] for m in result["models"]]
        # Real-ESRGAN has variants like x4plus / x2plus
        assert any(i.startswith("realesrgan-") for i in ids)

    def test_includes_gfpgan(self, svc):
        ids = [m["id"] for m in svc.list_all()["models"]]
        assert any(i.startswith("gfpgan-") for i in ids)

    def test_does_not_include_codeformer(self, svc):
        """Bug #5 follow-up: CodeFormer was removed; should not appear."""
        ids = [m["id"] for m in svc.list_all()["models"]]
        assert not any(i.startswith("codeformer-") for i in ids)


class TestWhisperEnumeration:
    def test_includes_whisper_sizes(self, svc):
        ids = [m["id"] for m in svc.list_all()["models"]]
        # Registry defines tiny/small/medium/large-v3 etc.
        assert any(i.startswith("whisper-") for i in ids)

    def test_whisper_category_is_audio(self, svc):
        whisper_models = [m for m in svc.list_all()["models"] if m["family"] == "whisper"]
        for m in whisper_models:
            assert m["category"] == "audio"


class TestGgufEnumeration:
    def test_includes_qwen3(self, svc):
        ids = [m["id"] for m in svc.list_all()["models"]]
        assert any(i.startswith("qwen3-") for i in ids)

    def test_gguf_category_is_llm(self, svc):
        gguf_families = ("qwen3", "qwen3vl", "qwen3.5", "gemma3", "gemma4")
        for m in svc.list_all()["models"]:
            if m["family"] in gguf_families:
                assert m["category"] == "llm"


class TestContractShape:
    """Guard: every item emits the 10 core keys + family-specific extras.

    This is a characterization/contract guard — it PASSES against the current
    code before the _make_model_item refactor.  Its real value is catching a
    dropped extra during (or after) the rewrite.
    """

    _CORE_KEYS = {
        "id", "family", "family_label", "variant", "variant_label",
        "category", "description", "downloaded", "size_mb", "vram_mb",
    }

    def test_core_keys_present_in_all_items(self, svc):
        models = svc.list_all()["models"]
        assert models, "list_all returned no models"
        for m in models:
            missing = self._CORE_KEYS - m.keys()
            assert not missing, f"model {m.get('id')!r} missing core keys {missing}"

    def test_family_specific_extras(self, svc):
        """PTH items must carry max_scale; GGUF items must carry the 4 ctx keys."""
        from app.adapters.ai.registry import MODELS_REGISTRY, FORMAT_PTH, FORMAT_GGUF

        pth_fams = set(MODELS_REGISTRY[FORMAT_PTH].keys())
        gguf_fams = set(MODELS_REGISTRY[FORMAT_GGUF].keys())
        models = svc.list_all()["models"]
        pth_items = [m for m in models if m["family"] in pth_fams]
        gguf_items = [m for m in models if m["family"] in gguf_fams]
        assert pth_items and gguf_items  # non-empty guard (avoid vacuous pass)
        for m in pth_items:
            assert "max_scale" in m, f"PTH model {m.get('id')!r} missing 'max_scale'"
        gguf_extras = {"capabilities", "n_ctx_default", "n_ctx_min", "n_ctx_max"}
        for m in gguf_items:
            assert gguf_extras <= m.keys(), (
                f"GGUF model {m.get('id')!r} missing extras {gguf_extras - m.keys()}"
            )


class TestDownloadStatus:
    def test_not_downloaded_when_path_returns_none(self, svc):
        # Default fixture: get_model_path returns None
        result = svc.list_all()
        # At least one PTH/GGUF model should be reported not-downloaded
        non_dl = [m for m in result["models"]
                  if m["family"] in ("realesrgan", "qwen3", "qwen3vl")
                  and not m["downloaded"]]
        assert non_dl, "expected at least one not-downloaded PTH/GGUF model"

    def test_downloaded_when_path_exists(self, tmp_path):
        """get_model_path returning a real existing path → downloaded=True."""
        fake_file = tmp_path / "fake_model.pth"
        fake_file.write_bytes(b"")
        mm = MagicMock()
        mm.get_model_path.return_value = fake_file
        svc = ModelMetadataService(model_manager=mm)
        models = svc.list_all()["models"]
        # PTH families take the get_model_path path; all should show downloaded=True
        pth = [m for m in models if m["family"] == "realesrgan"]
        assert pth and all(m["downloaded"] for m in pth)
