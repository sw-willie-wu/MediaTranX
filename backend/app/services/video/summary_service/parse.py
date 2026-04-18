"""Video summary parse + chunking helpers (single consumer: summary/service).

Data classes, token-budget chunking, LLM output parsing (bullets + narrative),
and chunk merging. Markdown rendering is in `markdown.py`.
"""
from __future__ import annotations
import json
import logging
import re
from dataclasses import dataclass, field

from app.utils.inference import estimate_tokens

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SubtitleEntry:
    start: float  # seconds
    end: float
    text: str


def chunk_entries_by_tokens(
    entries: list[SubtitleEntry],
    max_input_tokens: int,
) -> list[list[SubtitleEntry]]:
    """Split entries into chunks whose formatted transcript fits within budget."""
    if not entries:
        return []

    chunks: list[list[SubtitleEntry]] = []
    current: list[SubtitleEntry] = []
    current_text_parts: list[str] = []

    for e in entries:
        line = _format_entry_line(e)
        candidate = "\n".join(current_text_parts + [line])
        if current and estimate_tokens(candidate) > max_input_tokens:
            chunks.append(current)
            current = [e]
            current_text_parts = [line]
        else:
            current.append(e)
            current_text_parts.append(line)

    if current:
        chunks.append(current)
    return chunks


def _format_entry_line(e: SubtitleEntry) -> str:
    return f"[{e.start:.1f}-{e.end:.1f}] {e.text}"


def format_transcript(entries: list[SubtitleEntry]) -> str:
    """Format entries as LLM-facing transcript lines."""
    return "\n".join(_format_entry_line(e) for e in entries)


@dataclass
class SummaryChunkResult:
    # Bullets mode
    bullets_markdown: str = ""           # cleaned markdown (timestamp tags stripped)
    bullet_items: list[dict] = field(default_factory=list)
    # ^ each item: {"line_index": int (0-based, position in bullets_markdown),
    #               "time_range": (start_sec: float, end_sec: float)}
    # Narrative mode (existing)
    narrative_summary: str = ""
    turning_points: list[dict] = field(default_factory=list)


def parse_summary_json(raw: str) -> SummaryChunkResult:
    """Parse narrative-mode LLM output (JSON) into SummaryChunkResult."""
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text)

    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        raise ValueError(f"LLM output is not valid JSON: {e}") from e

    narrative_raw = obj.get("narrative", {}) or {}
    if not isinstance(narrative_raw, dict):
        logger.warning(f"Unexpected narrative shape {type(narrative_raw).__name__}; treating as empty")
        narrative_raw = {}

    tps_raw = narrative_raw.get("turning_points", []) or []
    if not isinstance(tps_raw, list):
        logger.warning(f"Unexpected turning_points shape {type(tps_raw).__name__}; treating as empty")
        tps_raw = []

    tps_clean: list[dict] = []
    for t in tps_raw:
        if not isinstance(t, dict):
            continue
        if not isinstance(t.get("time"), (int, float)):
            continue
        if not isinstance(t.get("text"), str):
            continue
        tps_clean.append(t)

    return SummaryChunkResult(
        narrative_summary=str(narrative_raw.get("summary", "")),
        turning_points=tps_clean,
    )


# Match `[mm:ss-mm:ss]`, `[m:ss-m:ss]`, or seconds-only `[123-456]` at end of bullet line.
_TS_TAG_RE = re.compile(
    r"\[\s*"
    r"(?:(\d+):(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?))"  # start: mm:ss OR raw_seconds
    r"\s*-\s*"
    r"(?:(\d+):(\d+(?:\.\d+)?)|(\d+(?:\.\d+)?))"  # end: mm:ss OR raw_seconds
    r"\s*\]"
)
_BULLET_LABEL_RE = re.compile(r"^\s*-\s*\*\*[^*]+\*\*")


def _parse_time_groups(g1, g2, g3) -> float:
    """g1/g2 = mm/ss (preferred); g3 = raw seconds."""
    if g1 is not None and g2 is not None:
        return int(g1) * 60 + float(g2)
    return float(g3)


def parse_bullets_markdown(raw: str) -> SummaryChunkResult:
    """Parse hierarchical bullets-mode markdown.

    Strips any wrapping code fence, then walks line-by-line:
      - lines that look like `- **label：** text [mm:ss-mm:ss]` get added to
        bullet_items with line_index + time_range, and the timestamp tag is
        stripped from the rendered markdown
      - all other lines pass through unchanged
    """
    text = raw.strip()
    text = re.sub(r"^```(?:markdown|md)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text)

    items: list[dict] = []
    out_lines: list[str] = []
    for line in text.splitlines():
        m = _TS_TAG_RE.search(line)
        if m and _BULLET_LABEL_RE.match(line):
            sm, ss, s_raw, em, es, e_raw = m.groups()
            t_start = _parse_time_groups(sm, ss, s_raw)
            t_end = _parse_time_groups(em, es, e_raw)
            items.append({
                "line_index": len(out_lines),
                "time_range": (t_start, t_end),
            })
            line = _TS_TAG_RE.sub("", line).rstrip()
        out_lines.append(line)

    return SummaryChunkResult(
        bullets_markdown="\n".join(out_lines),
        bullet_items=items,
    )


def merge_chunk_outputs(chunks: list[SummaryChunkResult]) -> SummaryChunkResult:
    """Merge per-chunk results.

    For bullets mode: concatenate markdown blocks (separator = blank line),
      offset bullet line_index accordingly so they remain valid in the merged text.
    For narrative mode: concat turning_points, join summaries with blank lines.
    """
    md_parts: list[str] = []
    merged_items: list[dict] = []
    line_offset = 0

    all_tps: list[dict] = []
    summaries: list[str] = []

    for c in chunks:
        # --- bullets mode merge ---
        if c.bullets_markdown.strip():
            md_parts.append(c.bullets_markdown)
            for item in c.bullet_items:
                merged_items.append({
                    "line_index": item["line_index"] + line_offset,
                    "time_range": item["time_range"],
                })
            # +2 for the blank separator line we'll insert (\n\n joins → +2 lines).
            line_offset += c.bullets_markdown.count("\n") + 2
        # --- narrative mode merge ---
        all_tps.extend(c.turning_points)
        if c.narrative_summary.strip():
            summaries.append(c.narrative_summary.strip())

    return SummaryChunkResult(
        bullets_markdown="\n\n".join(md_parts),
        bullet_items=merged_items,
        narrative_summary="\n\n".join(summaries),
        turning_points=all_tps,
    )
