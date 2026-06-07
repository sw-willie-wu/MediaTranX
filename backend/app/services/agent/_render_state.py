"""Render the frontend-supplied UI state snapshot into a compact text block
for the agent system message, with a deterministic char-budget truncation.

Spec 2026-06-07 §3.2-§3.4. Pure functions; no I/O.
"""
from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

# Char budget for the rendered "# 當前狀態" block. Generous default; the
# transcode panel + map measures well under this in practice. Truncation only
# triggers for pathological panels. Tune after measuring real panels (spec R3).
AGENT_STATE_CHAR_BUDGET = 4000

_OPTIONS_DROPPED = "[options 省略]"


def _field_line(f: dict, drop_options: bool) -> str:
    name = f.get("name", "?")
    cur = f.get("current_value")
    line = f"- {name} = {cur}"
    if f.get("options") and not drop_options:
        line += "  [" + "|".join(str(o) for o in f["options"]) + "]"
    elif f.get("options") and drop_options:
        line += "  " + _OPTIONS_DROPPED
    elif f.get("type") == "number" and ("min" in f or "max" in f):
        line += f"  ({f.get('min', '?')}~{f.get('max', '?')})"
    return line


def _render(snapshot: dict, dropped_option_fields: set[str],
            keep_invisible: bool, file_limit: int | None) -> str:
    lines: list[str] = ["# 當前狀態", ""]
    m = snapshot.get("map") or {}

    pos = m.get("current_position") or {}
    lines.append(f"## 我在哪\nview: {pos.get('view')}  subfunction: {pos.get('subfunction')}")
    lines.append("")

    lines.append("## 可去的工具與子功能")
    for v in m.get("views", []):
        subs = ", ".join(v.get("subfunctions", []))
        lines.append(f"{v.get('route')}: {subs}" if subs else f"{v.get('route')}")
    lines.append("")

    files = m.get("files", [])
    if file_limit is not None:
        files = files[:file_limit]
    if files:
        lines.append("## 已上傳檔案")
        for fl in files:
            lines.append(f"- id={fl.get('id')} name={fl.get('name')} kind={fl.get('kind')}")
        lines.append("")

    ap = snapshot.get("active_panel")
    if ap:
        lines.append(f"## 當前 panel: {ap.get('panel_id')}")
        af = snapshot.get("active_file")
        if af:
            lines.append(f"作用檔案: id={af.get('id')} name={af.get('name')}")
        lines.append("欄位（只能設這些；值照括號內合法值）:")
        for f in ap.get("fields", []):
            if not keep_invisible and not f.get("visible", True):
                continue
            lines.append(_field_line(f, drop_options=f.get("name") in dropped_option_fields))
        actions = ap.get("actions", [])
        if actions:
            lines.append("動作鈕: " + ", ".join(a.get("name", "?") for a in actions))
        ex = ap.get("execute")
        if ex:
            confirm = "（需確認）" if ex.get("requires_confirm") else ""
            lines.append(f"執行: {ex.get('label', 'submit')}{confirm}")

    return "\n".join(lines)


def render_state(snapshot: dict[str, Any],
                 char_budget: int = AGENT_STATE_CHAR_BUDGET) -> str:
    """Render snapshot to text; apply deterministic truncation if over budget."""
    out = _render(snapshot, set(), keep_invisible=True, file_limit=None)
    if len(out) <= char_budget:
        return out

    ap = snapshot.get("active_panel") or {}
    fields = ap.get("fields", [])

    # Stage 1: drop options, longest options-string first.
    by_len = sorted(
        (f for f in fields if f.get("options")),
        key=lambda f: -len("|".join(str(o) for o in f["options"])),
    )
    dropped: set[str] = set()
    for f in by_len:
        dropped.add(f.get("name"))
        out = _render(snapshot, dropped, keep_invisible=True, file_limit=None)
        logger.info("agent state budget: dropped options for field %s", f.get("name"))
        if len(out) <= char_budget:
            return out

    # Stage 2: drop invisible fields.
    out = _render(snapshot, dropped, keep_invisible=False, file_limit=None)
    if len(out) <= char_budget:
        logger.info("agent state budget: dropped invisible fields")
        return out

    # Stage 3: trim files from the tail.
    files = (snapshot.get("map") or {}).get("files", [])
    for limit in range(len(files) - 1, -1, -1):
        out = _render(snapshot, dropped, keep_invisible=False, file_limit=limit)
        if len(out) <= char_budget:
            logger.info("agent state budget: trimmed files to %d", limit)
            return out

    # Stage 4: hard truncate (safety net).
    logger.info("agent state budget: hard-truncated")
    marker = "\n…[截斷]"
    return out[: max(0, char_budget - len(marker))] + marker
