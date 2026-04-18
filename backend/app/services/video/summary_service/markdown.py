"""Video summary markdown composition.

Combines bullets / narrative result + per-item frame images into final markdown.
"""
from __future__ import annotations

from .parse import SummaryChunkResult


def build_markdown(
    result: SummaryChunkResult,
    bullet_frames: dict[int, str],  # bullet_items index -> relative image path
    tp_frames: dict[int, str],      # turning_point index -> relative image path
    title: str,
    language: str = "zh-TW",
) -> str:
    """Compose final markdown with title + hierarchical bullets (with images) + narrative."""
    if language.startswith("zh"):
        h_narrative = "劇情摘要"
        h_turning = "關鍵轉折"
    else:
        h_narrative = "Narrative Summary"
        h_turning = "Highlights"

    lines: list[str] = [f"# {title}", ""]

    if result.bullets_markdown.strip():
        # Split on newline, then insert image lines after each bullet_item's line.
        # Process in reverse to keep earlier line_index valid.
        md_lines = result.bullets_markdown.splitlines()
        for idx in range(len(result.bullet_items) - 1, -1, -1):
            item = result.bullet_items[idx]
            img = bullet_frames.get(idx)
            if not img:
                continue
            insert_at = item["line_index"] + 1
            # Indent image with 2 spaces so it renders as part of the bullet's block.
            md_lines.insert(insert_at, f"  ![]({img})")
        lines.extend(md_lines)
        lines.append("")

    if result.narrative_summary:
        lines.append(f"## {h_narrative}")
        lines.append("")
        lines.append(result.narrative_summary)
        lines.append("")

        if result.turning_points:
            lines.append(f"### {h_turning}")
            lines.append("")
            for i, tp in enumerate(result.turning_points):
                ts = _fmt_timestamp(tp["time"])
                lines.append(f"- **{ts}** — {tp['text']}")
                img = tp_frames.get(i)
                if img:
                    lines.append("")
                    lines.append(f"  ![]({img})")
            lines.append("")

    return "\n".join(lines)


def _fmt_timestamp(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"
