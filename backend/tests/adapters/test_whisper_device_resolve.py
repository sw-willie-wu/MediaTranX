from unittest.mock import MagicMock, patch
from app.adapters.ai.wrapper.whisper import WhisperWrapper


def test_create_model_uses_resolve_device(monkeypatch):
    w = WhisperWrapper()
    captured = {}

    fake_model = MagicMock()
    with patch("faster_whisper.WhisperModel", return_value=fake_model) as mk, \
         patch("app.adapters.compute_policy.resolve_device_for_task", return_value="cpu") as rdt, \
         patch("app.adapters.device.compute_type_for", return_value="int8"):
        w._create_model("model/path", {"vram_mb": 3000, "model_id": "whisper-medium"}, "cuda")
        rdt.assert_called_once()
        _, kwargs = mk.call_args
        captured["device"] = kwargs.get("device")
    assert captured["device"] == "cpu"
    assert w._device == "cpu"
