"""Video summary markdown composition.

Combines a bullets-mode hierarchical result or a narrative-mode paragraph
result with per-item frame images into the final markdown.
"""
from __future__ import annotations

from .parse import SummaryChunkResult


def build_markdown(
    result: SummaryChunkResult,
    bullet_frames: dict[int, str],   # bullet_items index -> relative image path
    para_frames: dict[int, str],     # narrative_paragraphs index -> image path
    title: str,
    language: str = "zh-TW",         # reserved; rendering is language-agnostic
) -> str:
    """Compose final markdown: title + (hierarchical bullets | flat paragraphs).

    Bullets mode: each framed bullet gets an indented image line inserted right
    after the bullet's markdown line. Narrative mode: each paragraph is plain
    prose followed by its frame (when one was picked); no headings, no markers.
    """
    lines: list[str] = [f"# {title}", ""]

    if result.bullets_markdown.strip():
        # Insert image lines after each bullet_item's line. Process in reverse
        # so earlier line_index values stay valid as we insert.
        md_lines = result.bullets_markdown.splitlines()
        for idx in range(len(result.bullet_items) - 1, -1, -1):
            item = result.bullet_items[idx]
            img = bullet_frames.get(idx)
            if not img:
                continue
            insert_at = item["line_index"] + 1
            # Indent so the image renders inside the bullet's block.
            md_lines.insert(insert_at, f"  ![]({img})")
        lines.extend(md_lines)
        lines.append("")

    if result.narrative_paragraphs:
        for idx, para in enumerate(result.narrative_paragraphs):
            lines.append(para["text"])
            lines.append("")
            img = para_frames.get(idx)
            if img:
                lines.append(f"![]({img})")
                lines.append("")

    return "\n".join(lines)
