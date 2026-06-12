"""FORMAT_NCNN registry tree: schema invariants the wrapper/downloader rely on."""
from app.adapters.ai import registry


def _variants():
    for family, spec in registry.MODELS_REGISTRY[registry.FORMAT_NCNN].items():
        for vname, v in spec["variants"].items():
            yield family, spec, vname, v


def test_ncnn_tree_has_exactly_the_migrated_families():
    # Real-CUGAN is intentionally absent: its bilibili/ailab weights are
    # unlicensed (R6) so the ncnn port was dropped; it stays PTH-only.
    assert set(registry.MODELS_REGISTRY[registry.FORMAT_NCNN]) == {
        "realesrgan", "waifu2x"}


def test_every_variant_has_param_bin_pair_and_core_fields():
    for family, spec, vname, v in _variants():
        assert spec["slot"] and spec["label"] and spec["category"] == "upscale"
        exts = sorted(f.rsplit(".", 1)[1] for f in v["files"])
        assert exts == ["bin", "param"], (family, vname)
        assert v["exe_tool"] in {"realesrgan", "waifu2x"}
        assert v["scale"] in (2, 3, 4)
        assert v["vram_mb"] > 0 and v["size_mb"] > 0


def test_realesrgan_variants_dropped_x2plus_and_split_animevideo():
    vs = set(registry.MODELS_REGISTRY[registry.FORMAT_NCNN]["realesrgan"]["variants"])
    assert vs == {"x4plus", "x4plus-anime",
                  "animevideov3-x2", "animevideov3-x3", "animevideov3-x4"}


def test_cli_fields_are_mutually_exclusive_by_tool():
    for family, spec, vname, v in _variants():
        if v["exe_tool"] == "realesrgan":
            assert "cli_model_name" in v and "cli_noise" not in v
        else:
            assert "cli_noise" in v and "cli_model_name" not in v


def test_migrated_families_have_ui_text():
    # (The PTH realesrgan/waifu2x entries were deleted in T11, so there are no
    # originals left to compare against — just assert the NCNN rows carry text.)
    ncnn = registry.MODELS_REGISTRY[registry.FORMAT_NCNN]
    for fam in ("realesrgan", "waifu2x"):
        assert ncnn[fam]["label"] and ncnn[fam].get("description")
