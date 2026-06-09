import base64
import json
import types
import pytest

from app.services.setup import model_download_service as mds
from app.adapters.ai.registry import SOUNDFONT_VERSION_TAG
from app.init.configs import SETTINGS


@pytest.fixture
def sf_root(tmp_path, monkeypatch):
    try:
        monkeypatch.setattr(SETTINGS.path, "root", tmp_path)
        return SETTINGS.path.soundfonts
    except Exception:
        sf = tmp_path / "sf"
        monkeypatch.setattr(SETTINGS, "path", types.SimpleNamespace(soundfonts=sf, models=SETTINGS.path.models))
        return sf


class _FakeResp:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


def test_download_soundfont_parses_and_writes(sf_root, monkeypatch):
    # 只跑 1 個樂器；鼓組仍跑 35-81，用 fake_get 統一回應
    monkeypatch.setattr(mds, "_soundfont_instruments", lambda: ["acoustic_grand_piano"], raising=False)

    sample_b64 = base64.b64encode(b"FAKE_MP3_BYTES").decode()
    inst_js = f'MIDI.Soundfont.acoustic_grand_piano = {{ "A4": "data:audio/mp3;base64,{sample_b64}" }}'
    drum_b64 = base64.b64encode(b"DRUM").decode()
    drum_js = f"file: '{drum_b64}'"

    def fake_get(url, **kw):
        return _FakeResp(drum_js if "FluidR3" in url else inst_js)

    import requests
    monkeypatch.setattr(requests, "get", fake_get)

    msgs = []
    mds._download_soundfont(lambda frac, msg: msgs.append((frac, msg)))

    sf = sf_root
    assert (sf / "acoustic_grand_piano-mp3" / "A4.mp3").read_bytes() == b"FAKE_MP3_BYTES"
    assert (sf / "drums-mp3" / "35.mp3").read_bytes() == b"DRUM"
    assert json.loads((sf / ".version").read_text("utf-8"))["tag"] == SOUNDFONT_VERSION_TAG
    assert any(m[1].startswith("task.progress.downloading_soundfont") for m in msgs)


def test_handle_model_download_dispatches_soundfont(monkeypatch):
    called = {}
    monkeypatch.setattr(mds, "_download_soundfont", lambda cb: called.setdefault("hit", True))
    mds.handle_model_download({"id": "soundfont-musyngkite"}, lambda f, m: None)
    assert called.get("hit") is True
