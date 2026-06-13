import json
import pytest
import types

from app.services.setup.model_metadata_service import ModelMetadataService, _soundfont_downloaded
from app.adapters.ai.registry import SOUNDFONT_ID, SOUNDFONT_VERSION_TAG
from app.init.configs import SETTINGS


@pytest.fixture
def sf_root(tmp_path, monkeypatch):
    # SETTINGS.path.soundfonts is a pydantic computed_field = root/bin/soundfonts/musyngkite.
    # Patch root so soundfonts recomputes under tmp. (PathSettings is a mutable pydantic BaseModel.)
    try:
        monkeypatch.setattr(SETTINGS.path, "root", tmp_path)
        return SETTINGS.path.soundfonts
    except Exception:
        sf = tmp_path / "sf"
        monkeypatch.setattr(SETTINGS, "path", types.SimpleNamespace(soundfonts=sf, models=SETTINGS.path.models))
        return sf


def test_soundfont_downloaded_true_when_tag_matches(sf_root):
    sf_root.mkdir(parents=True, exist_ok=True)
    (sf_root / ".version").write_text(json.dumps({"tag": SOUNDFONT_VERSION_TAG}), encoding="utf-8")
    assert _soundfont_downloaded() is True


def test_soundfont_downloaded_false_when_absent(sf_root):
    assert _soundfont_downloaded() is False


def test_soundfont_downloaded_false_when_tag_mismatch(sf_root):
    sf_root.mkdir(parents=True, exist_ok=True)
    (sf_root / ".version").write_text(json.dumps({"tag": "999"}), encoding="utf-8")
    assert _soundfont_downloaded() is False


def test_enumerate_midi_returns_soundfont_item():
    svc = ModelMetadataService.__new__(ModelMetadataService)
    items = svc._enumerate_midi_models()
    assert len(items) == 1
    it = items[0]
    assert it["id"] == SOUNDFONT_ID
    assert it["category"] == "midi"
    assert it["size_mb"] == 267
    assert {"id", "family", "family_label", "variant", "variant_label",
            "category", "description", "downloaded", "size_mb", "vram_mb"}.issubset(it.keys())
