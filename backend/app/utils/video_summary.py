"""Utilities for video summary pipeline.

Tasks 2: SRT parse + token-budget chunking.
Task 3: prompt builder, JSON parser, chunk merger.
Task 4: markdown builder.
"""
from __future__ import annotations
import json
import logging
import re
from dataclasses import dataclass, field

from app.utils.inference import estimate_tokens
from app.utils.prompts import LANG_NAMES_EN

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SubtitleEntry:
    start: float  # seconds
    end: float
    text: str


_TS_RE = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)\s*-->\s*(\d+):(\d+):(\d+)[,.](\d+)")


def parse_srt_text(text: str) -> list[SubtitleEntry]:
    """Parse SRT text into ordered SubtitleEntry list."""
    text = text.lstrip("\ufeff").strip()
    blocks = re.split(r"\n\s*\n", text)
    entries: list[SubtitleEntry] = []
    for b in blocks:
        lines = b.strip().splitlines()
        if len(lines) < 3:
            continue
        m = _TS_RE.match(lines[1])
        if not m:
            continue
        sh, sm, ss, sms, eh, em, es, ems = m.groups()
        start = int(sh) * 3600 + int(sm) * 60 + int(ss) + int(sms) / 1000
        end = int(eh) * 3600 + int(em) * 60 + int(es) + int(ems) / 1000
        content = " ".join(l.strip() for l in lines[2:] if l.strip())
        if content:
            entries.append(SubtitleEntry(start=start, end=end, text=content))
    return entries


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


SUMMARY_MODE_BULLETS = "bullets"
SUMMARY_MODE_NARRATIVE = "narrative"

_PROMPT_BULLETS = """Below is a subtitle transcript in format [start_sec-end_sec] text:

{transcript}

Write a **hierarchical Markdown summary** of the transcript. Structure:

```
## {{H2 major theme}}
### {{H3 sub-theme — only when grouping helps}}
- **{{short label}}：** {{one-sentence description}} [mm:ss-mm:ss]
- **{{another label}}：** {{description}} [mm:ss-mm:ss]
    - {{optional nested sub-bullet — no timestamp needed}}
```

Rules:
1. Use `##` for major themes (3~6 sections) and `###` for sub-themes when helpful
2. Every top-level bullet (line starting with `- **label：**`) MUST end with a timestamp range in the form `[mm:ss-mm:ss]` covering when the topic appears in the transcript
3. **Each bullet's [mm:ss-mm:ss] range MUST NOT exceed 60 seconds** — split longer topics into multiple adjacent bullets, each describing the concrete content of that span (no broad/summarising sentences)
4. Use bold labels at the start of each bullet (e.g., `**活動背景：**`); nested sub-bullets (indented 4 spaces) are optional and do NOT need timestamps
5. All timestamps must fall within the transcript range
6. Output Markdown only — no JSON, no code fences, no extra text
7. {language_directive}
"""

_PROMPT_NARRATIVE = """Below is a subtitle transcript in format [start_sec-end_sec] text:

{transcript}

Analyze it and output a **JSON object** (no extra text, no markdown fence) with this structure:

{{
  "narrative": {{
    "summary": "narrative summary (~200 words for English, ~200 characters for CJK)",
    "turning_points": [
      {{"time": sec(float), "text": "one-sentence description of this highlight/turn"}}
    ]
  }}
}}

Rules:
1. summary: a coherent, flowing narrative — not a bullet list
2. 2~5 turning_points marking the most pivotal moments in the transcript
3. All timestamps must fall within the transcript range
4. Output JSON only, no other text
5. {language_directive}
"""


def build_summary_prompt(
    entries: list[SubtitleEntry],
    output_language: str | None = None,
    summary_mode: str = SUMMARY_MODE_BULLETS,
) -> str:
    """Build summary prompt for the given mode.

    summary_mode: "bullets" (hierarchical-friendly key points with frames per item)
                  or "narrative" (prose summary + turning points with frames per turn).
    output_language: ISO-ish code (e.g. "zh", "en", "ja") from Whisper detection.
    Falls back to "match transcript language" when None.
    """
    transcript = format_transcript(entries)
    if output_language:
        name = LANG_NAMES_EN.get(output_language, output_language)
        directive = (
            f'Write all natural-language fields ("text" and "summary") in '
            f'{name} (matching the transcript language).'
        )
    else:
        directive = (
            'Write all natural-language fields ("text" and "summary") in the '
            'same language as the transcript above.'
        )
    if summary_mode == SUMMARY_MODE_NARRATIVE:
        tmpl = _PROMPT_NARRATIVE
    else:
        tmpl = _PROMPT_BULLETS
    return tmpl.format(transcript=transcript, language_directive=directive)


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
# Captures: (start_min, start_sec_or_None, start_total_sec, end_min, end_sec_or_None, end_total_sec)
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
