from app.services.agent._render_state import render_state, AGENT_STATE_CHAR_BUDGET


def _snap(active_panel=None, files=None):
    return {
        "map": {
            "views": [
                {"route": "/video", "label": "Video",
                 "subfunctions": ["transcode", "cut", "crop"]},
                {"route": "/image", "label": "Image", "subfunctions": ["upscale"]},
            ],
            "files": files if files is not None else [
                {"id": "f1", "name": "clip.mp4", "kind": "video"}],
            "current_position": {"view": "/video", "subfunction": "transcode"},
        },
        "active_panel": active_panel,
        "active_file": {"id": "f1", "name": "clip.mp4", "kind": "video"},
    }


def test_renders_map_and_current_position():
    out = render_state(_snap())
    assert "# 當前狀態" in out
    assert "/video" in out and "transcode" in out
    assert "clip.mp4" in out


def test_active_panel_none_renders_map_only():
    out = render_state(_snap(active_panel=None))
    assert "# 當前狀態" in out
    assert "當前 panel" not in out


def test_active_panel_fields_with_current_value_and_options():
    ap = {
        "panel_id": "video.transcode",
        "fields": [
            {"name": "output_format", "type": "enum", "current_value": "mp4",
             "options": ["mp4", "mkv", "webm"], "visible": True},
            {"name": "crf", "type": "number", "current_value": 23,
             "min": 0, "max": 51, "step": 1, "visible": True},
        ],
        "actions": [{"name": "browse", "label": "Browse"}],
        "execute": {"requires_confirm": True, "label": "Transcode"},
    }
    out = render_state(_snap(active_panel=ap))
    assert "output_format" in out and "mp4" in out and "mkv" in out
    assert "crf" in out and "23" in out


def test_budget_drops_longest_options_first():
    # Tiny map (1 view, no files) + one HUGE-options field + one tiny field.
    # budget=250 is well above the post-Stage-1 size but below the full render,
    # so ONLY Stage 1 (drop longest options) fires and the short field survives.
    snap = {
        "map": {
            "views": [{"route": "/v", "label": "V", "subfunctions": ["t"]}],
            "files": [],
            "current_position": {"view": "/v", "subfunction": "t"},
        },
        "active_panel": {
            "panel_id": "p",
            "fields": [
                {"name": "long", "type": "enum", "current_value": "a",
                 "options": ["a" * 120, "b" * 120, "c" * 120], "visible": True},
                {"name": "short", "type": "enum", "current_value": "x",
                 "options": ["x", "y"], "visible": True},
            ],
            "actions": [], "execute": None,
        },
        "active_file": None,
    }
    out = render_state(snap, char_budget=250)
    assert len(out) <= 250
    assert "short" in out
    assert "options 省略" in out
    assert "b" * 120 not in out


def test_default_budget_is_a_positive_int():
    assert isinstance(AGENT_STATE_CHAR_BUDGET, int) and AGENT_STATE_CHAR_BUDGET > 0


def test_stage2_drops_invisible_fields():
    # All fields have NO options (Stage 1 is a no-op), several are invisible.
    # Measured: full render = 410 chars, after dropping invisible = 106 chars.
    # Budget=200 sits between the two: Stage 1 is a no-op (no options), Stage 2
    # fires (drop invisible fields) and the result (106) fits within budget.
    snap = {
        "map": {
            "views": [{"route": "/v", "label": "V", "subfunctions": ["t"]}],
            "files": [],
            "current_position": {"view": "/v", "subfunction": "t"},
        },
        "active_panel": {
            "panel_id": "p",
            "fields": (
                [{"name": "keep", "type": "string", "current_value": "x", "visible": True}]
                + [{"name": f"hidden{i}", "type": "string",
                    "current_value": "v" * 25, "visible": False} for i in range(8)]
            ),
            "actions": [], "execute": None,
        },
        "active_file": None,
    }
    out = render_state(snap, char_budget=200)
    assert len(out) <= 200
    assert "keep" in out          # visible field survives
    assert "hidden0" not in out   # invisible fields dropped


def test_stage3_trims_files_from_tail():
    # No active_panel (Stages 1-2 are no-ops); many files force Stage 3.
    # Measured: full render = 482 chars, budget=200 keeps file_limit=3 (172 chars).
    snap = {
        "map": {
            "views": [{"route": "/v", "label": "V", "subfunctions": ["t"]}],
            "files": [{"id": f"file{i}", "name": f"n{i}.mp4", "kind": "video"}
                      for i in range(12)],
            "current_position": {"view": "/v", "subfunction": "t"},
        },
        "active_panel": None,
        "active_file": None,
    }
    out = render_state(snap, char_budget=200)
    assert len(out) <= 200
    assert "file0" in out          # head kept
    assert "file11" not in out     # tail trimmed


def test_stage4_hard_truncate_guarantees_budget():
    # Big map, no panel, no files → Stage 3 loop is empty (nothing to trim),
    # Stage 4 must fire.
    # Measured: full render = 492 chars; budget=120 forces hard truncation.
    snap = {
        "map": {
            "views": [{"route": f"/view{i}", "label": f"V{i}",
                       "subfunctions": ["alpha", "bravo", "charlie", "delta", "echo"]}
                      for i in range(10)],
            "files": [],
            "current_position": {"view": "/view0", "subfunction": "alpha"},
        },
        "active_panel": None,
        "active_file": None,
    }
    out = render_state(snap, char_budget=120)
    assert len(out) <= 120
    assert "…[截斷]" in out        # Stage 4 marker present
