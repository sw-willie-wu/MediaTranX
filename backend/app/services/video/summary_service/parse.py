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


def compute_bullet_target(content_sec: float, rate: float = 1.5,
                          k_min: int = 8, k_max: int = 40) -> int:
    """Duration-scaled cap on how many bullets get an inline frame.

    ``content_sec`` = spoken-content duration (max subtitle end). Scales at
    ``rate`` bullets/min, clamped to ``[k_min, k_max]``. The rendered summary
    text still contains every bullet; this only bounds frame-extraction work.
    """
    return max(k_min, min(k_max, round(content_sec / 60.0 * rate)))


def even_indices(n: int, k: int) -> list[int]:
    """``k`` evenly-spaced unique ascending indices in ``[0, n-1]``.

    ``k >= n`` → ``range(n)``. ``k <= 1`` → ``[0]`` (defensive; production call
    sites pass ``k >= K_MIN = 8`` via :func:`compute_bullet_target`, so this
    branch is unreachable there). For ``n > k >= 2`` the step
    ``(n-1)/(k-1) > 1`` so ``round()`` yields ``k`` unique ascending indices
    spanning both ends.
    """
    if n <= 0:
        return []
    if k >= n:
        return list(range(n))
    if k <= 1:
        return [0]
    return [round(i * (n - 1) / (k - 1)) for i in range(k)]


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
    """Format entries as LLM-facing transcript lines (seconds format).

    Used by narrative mode (which asks the LLM for float-second timestamps)
    and by :func:`chunk_entries_by_tokens` for token budgeting.
    """
    return "\n".join(_format_entry_line(e) for e in entries)


def format_transcript_numbered(entries: list[SubtitleEntry], start_index: int = 1) -> str:
    """Format entries as LLM-facing lines prefixed with a global line number.

    Each line is ``[L<n>] <text>`` where ``n`` is a 1-based line number kept
    continuous across chunks (callers pass ``start_index`` = the running
    offset). Unlike :func:`format_transcript` this carries no timestamps — the
    bullets-mode LLM cites these line numbers and the service resolves them
    back to real Whisper timestamps (see :func:`resolve_bullet_windows`).
    """
    return "\n".join(
        f"[L{start_index + i}] {e.text}" for i, e in enumerate(entries)
    )


@dataclass
class SummaryChunkResult:
    # Bullets mode
    bullets_markdown: str = ""           # cleaned markdown ([L..] cite tags stripped)
    bullet_items: list[dict] = field(default_factory=list)
    # ^ each item dict, by lifecycle stage:
    #   parse_bullets_markdown -> {"line_index": int (0-based pos in bullets_markdown),
    #                              "line_range": (a, b) — 1-based global transcript lines}
    #   merge_chunk_outputs    -> "line_index" offset; "line_range" passed through unchanged
    #   resolve_bullet_windows -> adds "time_range": (start_sec, end_sec) | None
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


# Match a line-citation tag `[L<a>-L<b>]` at the end of a bullet line. `a`/`b`
# are 1-based global transcript line numbers (see format_transcript_numbered).
# The literal `L` prefix makes the token distinctive, so this is safe to use
# both to extract the cite (.search) and to strip it (.sub) from any line —
# legitimate bracketed content like `[80-120]` is never matched.
_CITE_RE = re.compile(r"\[\s*L(\d+)\s*-\s*L(\d+)\s*\]\s*$")
_BULLET_LABEL_RE = re.compile(r"^\s*-\s*\*\*[^*]+\*\*")


def parse_bullets_markdown(raw: str) -> SummaryChunkResult:
    """Parse hierarchical bullets-mode markdown.

    Strips any wrapping code fence, then walks line-by-line:
      - top-level bullet lines (`- **label：** text [L<a>-L<b>]`) whose trailing
        `[L<a>-L<b>]` cite matches get added to bullet_items with line_index +
        line_range (the 1-based global transcript line numbers the LLM cited)
      - the `[L<a>-L<b>]` cite tag is stripped from every line (recorded or not,
        bullet or sub-bullet) so it never leaks into the rendered markdown
      - all other content passes through unchanged
    """
    text = raw.strip()
    text = re.sub(r"^```(?:markdown|md)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text)

    items: list[dict] = []
    out_lines: list[str] = []
    for line in text.splitlines():
        is_bullet = _BULLET_LABEL_RE.match(line)
        cite = _CITE_RE.search(line) if is_bullet else None
        if cite:
            items.append({
                "line_index": len(out_lines),
                "line_range": (int(cite.group(1)), int(cite.group(2))),
            })
        # Strip the trailing [L<a>-L<b>] cite from the rendered line. Run on
        # every line: the `L` prefix means legit bracketed content is untouched.
        line = _CITE_RE.sub("", line).rstrip()
        out_lines.append(line)

    return SummaryChunkResult(
        bullets_markdown="\n".join(out_lines),
        bullet_items=items,
    )


def resolve_bullet_windows(items: list[dict], entries: list[SubtitleEntry]) -> None:
    """Resolve each bullet_item's cited line range to a real time window.

    Sets ``item["time_range"]`` in place to ``(start_sec, end_sec)`` taken from
    the cited Whisper ``entries``, or ``None`` when the citation is unusable.

    ``items`` carry ``line_range = (a, b)`` — 1-based global transcript line
    numbers. ``entries`` MUST be the full global list those line numbers index
    into (not a per-chunk slice). Out-of-range indices are clamped into range;
    a citation still inverted after clamping (``a > b``) is dropped (``None``)
    rather than fabricating a window from self-evidently-garbage output.
    """
    n = len(entries)
    for item in items:
        if n == 0:
            item["time_range"] = None
            continue
        a, b = item["line_range"]
        ia = min(max(int(a), 1), n) - 1
        ib = min(max(int(b), 1), n) - 1
        if ia > ib:
            item["time_range"] = None
        else:
            item["time_range"] = (entries[ia].start, entries[ib].end)


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
                    # line_range is a global transcript line cite — NOT offset.
                    "line_range": item["line_range"],
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
