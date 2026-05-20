"""Unit tests for StageProgress."""
import pytest
from app.utils.progress_stages import StageProgress


def _collect_calls():
    calls = []
    def cb(p: float, msg: str) -> None:
        calls.append((round(p, 6), msg))
    return cb, calls


def test_single_stage_maps_to_pre_final_range():
    cb, calls = _collect_calls()
    sp = StageProgress(cb, weights={"only": 1})
    sp.stage("only", 0.0, "start")
    sp.stage("only", 0.5, "mid")
    sp.stage("only", 1.0, "end")
    # "only" occupies [0, 0.95) — final_weight=0.05 reserved
    assert calls == [(0.0, "start"), (0.475, "mid"), (0.95, "end")]


def test_multi_stage_weights_normalize():
    cb, calls = _collect_calls()
    sp = StageProgress(cb, weights={"demucs": 3, "whisper": 5, "align": 2})
    sp.stage("demucs", 1.0, "d")
    sp.stage("whisper", 1.0, "w")
    sp.stage("align", 1.0, "a")
    # total relative = 10; pre-final range = 0.95
    # demucs: 0 → 0.285; whisper: 0.285 → 0.76; align: 0.76 → 0.95
    assert calls[0] == (0.285, "d")
    assert calls[1] == (0.76, "w")
    assert calls[2] == (0.95, "a")


def test_final_stage_occupies_top_fraction():
    cb, calls = _collect_calls()
    sp = StageProgress(cb, weights={"demucs": 1})
    sp.stage("write", 0.0, "writing")
    sp.stage("write", 1.0, "written")
    assert calls == [(0.95, "writing"), (1.0, "written")]


def test_unknown_stage_falls_through_with_warning(caplog):
    cb, calls = _collect_calls()
    sp = StageProgress(cb, weights={"demucs": 1})
    with caplog.at_level("WARNING"):
        sp.stage("unknown", 0.5, "msg")
    assert any("unknown" in rec.message for rec in caplog.records)
    assert calls == [(0.5, "msg")]


def test_empty_weights_raises():
    cb, _ = _collect_calls()
    with pytest.raises(ValueError):
        StageProgress(cb, weights={})


def test_custom_final_stage_and_weight():
    cb, calls = _collect_calls()
    sp = StageProgress(cb, weights={"proc": 1}, final_stage="save", final_weight=0.1)
    sp.stage("proc", 1.0, "done")
    sp.stage("save", 1.0, "saved")
    assert calls == [(0.9, "done"), (1.0, "saved")]


def test_final_stage_collision_raises():
    cb, _ = _collect_calls()
    with pytest.raises(ValueError, match="collides"):
        StageProgress(cb, weights={"write": 3, "other": 2})
