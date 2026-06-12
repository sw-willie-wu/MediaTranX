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
    def test_includes_bsrgan(self, svc):
        # bsrgan is a PTH upscaler that stays torch through Phase 1 (Real-ESRGAN
        # moved to NCNN; see TestPthShadowGuard). Pins that the PTH enumerator
        # still yields upscaler rows.
        ids = [m["id"] for m in svc.list_all()["models"]]
        assert any(i.startswith("bsrgan-") for i in ids)

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


class TestDownloadStatus:
    def test_not_downloaded_when_path_returns_none(self, svc):
        # Default fixture: get_model_path returns None
        result = svc.list_all()
        # At least one PTH/GGUF model should be reported not-downloaded
        non_dl = [m for m in result["models"]
                  if m["family"] in ("bsrgan", "qwen3", "qwen3vl")
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
        # PTH families take the get_model_path path; all should show downloaded=True.
        # (realesrgan moved to NCNN — use a surviving PTH family.)
        pth = [m for m in models if m["family"] == "bsrgan"]
        assert pth and all(m["downloaded"] for m in pth)


class TestNcnnEnumeration:
    """FORMAT_NCNN enumerator: replaces the migrated families' rows that the
    PTH-shadow guard removes. `downloaded` is a direct filesystem check of the
    .param+.bin pair under models/<slot>/ (NOT via get_model_path)."""

    def test_ncnn_variants_listed_and_not_downloaded_without_files(self, svc, monkeypatch, tmp_path):
        from app.init.configs import SETTINGS
        monkeypatch.setattr(SETTINGS.path, "models", tmp_path)
        models = svc.list_all()["models"]
        ncnn = [m for m in models if m["family"] in ("realesrgan", "waifu2x")]
        assert ncnn, "migrated SR families must be listed via the NCNN enumerator"
        assert all(not m["downloaded"] for m in ncnn)
        ids = {m["id"] for m in ncnn}
        assert "realesrgan-x4plus" in ids
        assert "realesrgan-animevideov3-x2" in ids          # animevideov3 split
        assert "realesrgan-x2plus" not in ids               # dropped (D-P1-1)

    def test_ncnn_downloaded_true_when_both_files_present(self, svc, monkeypatch, tmp_path):
        from app.init.configs import SETTINGS
        monkeypatch.setattr(SETTINGS.path, "models", tmp_path)
        slot_dir = tmp_path / "waifu2x"
        slot_dir.mkdir(parents=True)
        for f in ("scale2.0x_model.param", "scale2.0x_model.bin"):
            (slot_dir / f).write_bytes(b"x")
        models = svc.list_all()["models"]
        waifu = next(m for m in models if m["id"] == "waifu2x-cunet-art-2x")
        assert waifu["downloaded"] is True

    def test_no_duplicate_ids_across_list_all(self, svc, monkeypatch, tmp_path):
        from app.init.configs import SETTINGS
        monkeypatch.setattr(SETTINGS.path, "models", tmp_path)
        ids = [m["id"] for m in svc.list_all()["models"]]
        assert len(ids) == len(set(ids))

    def test_pth_upscalers_still_listed(self, svc):
        ids = [m["id"] for m in svc.list_all()["models"]]
        assert any(i.startswith("bsrgan-") for i in ids)
        assert any(i.startswith("swinir-") for i in ids)


class TestPthShadowGuard:
    """During the NCNN transition the migrated SR families resolve as NCNN, so
    the PTH enumerator must not also surface them — a duplicate PTH row would
    carry a lying `downloaded` flag. Task 11 deletes the shadowed PTH pair."""

    def test_pth_enumeration_omits_ncnn_migrated_families(self, svc):
        fams = {m["family"] for m in svc._enumerate_pth_models()}
        assert not (fams & {"realesrgan", "waifu2x"})
        # non-migrated PTH upscalers stay enumerated. real-cugan was dropped from
        # the ncnn port (R6 licensing) so it is NOT shadowed → stays PTH-listed.
        assert {"bsrgan", "swinir", "real-cugan"} <= fams
