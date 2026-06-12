"""ModelManager FORMAT_NCNN discovery + path resolution (Phase-1 wiring)."""
from app.adapters.ai import registry
from app.adapters.ai.model_manager import ModelManager
from app.init.configs import SETTINGS


def test_get_model_format_resolves_ncnn_families():
    mm = ModelManager()
    assert mm.get_model_format("waifu2x") == registry.FORMAT_NCNN
    # realesrgan lives in BOTH trees during the transition → NCNN must win
    # (search order PKG, GGUF, NCNN, PTH).
    assert mm.get_model_format("realesrgan") == registry.FORMAT_NCNN
    # families with no NCNN entry stay PTH. real-cugan was dropped from the ncnn
    # port over weight licensing (R6) → it stays PTH-only like bsrgan/swinir.
    assert mm.get_model_format("real-cugan") == registry.FORMAT_PTH
    assert mm.get_model_format("bsrgan") == registry.FORMAT_PTH


def test_get_model_config_merges_slot_and_variant():
    mm = ModelManager()
    cfg = mm.get_model_config("realesrgan", "x4plus")
    assert cfg is not None
    assert cfg["exe_tool"] == "realesrgan"
    assert cfg["scale"] == 4
    assert cfg["cli_model_name"] == "realesrgan-x4plus"
    # family `slot` merged in (the wrapper needs it; variant spec has no slot).
    assert cfg["slot"] == "realesrgan"


def test_get_model_path_param_when_all_files_exist_else_none(monkeypatch, tmp_path):
    monkeypatch.setattr(SETTINGS.path, "models", tmp_path)
    mm = ModelManager()
    slot_dir = tmp_path / "waifu2x"
    slot_dir.mkdir(parents=True)
    files = ["scale2.0x_model.param", "scale2.0x_model.bin"]
    for f in files:
        (slot_dir / f).write_bytes(b"x")

    # all files present → returns the .param path (wrapper derives model_dir).
    assert mm.get_model_path("waifu2x", "cunet-art-2x") == slot_dir / "scale2.0x_model.param"

    # any file missing → None (same no-raise/no-download contract as the PTH branch).
    (slot_dir / "scale2.0x_model.bin").unlink()
    assert mm.get_model_path("waifu2x", "cunet-art-2x") is None
