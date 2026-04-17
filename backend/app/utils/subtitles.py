"""Pure subtitle format/parse helpers — no AI or engine dependencies.

Formats: SRT, VTT, TXT, LRC.
Parses: SRT, VTT.
Consumers:
  - Transcribe services (audio/transcribe, audio/lyrics, video/subtitle) — format path
  - document/translate_service — parse + format (it translates existing SRT/VTT files, no STT)
  - video/summary/service — not used directly; summary builds its own markdown
  - translate pipeline (SRT batch) — dict-shaped segments_to_srt + parse_srt_response
"""
from __future__ import annotations
from dataclasses import dataclass
import logging
import re

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Segment:
    start: float  # seconds
    end: float
    text: str


# -- Time formatters --

def format_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int(round((seconds - int(seconds)) * 1000))
    # Handle rounding edge: 999.5 -> 1000, carry up
    if ms == 1000:
        ms = 0
        s += 1
        if s == 60:
            s = 0
            m += 1
            if m == 60:
                m = 0
                h += 1
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def format_vtt_time(seconds: float) -> str:
    return format_srt_time(seconds).replace(",", ".")


def format_lrc_time(seconds: float) -> str:
    m = int(seconds // 60)
    s = seconds - m * 60
    return f"[{m:02d}:{s:05.2f}]"


# -- Time parser --

_TS_PARSE_RE = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)")


def parse_srt_time(text: str) -> float:
    m = _TS_PARSE_RE.match(text.strip())
    if not m:
        raise ValueError(f"Invalid timestamp: {text!r}")
    h, mi, s, ms = m.groups()
    return int(h) * 3600 + int(mi) * 60 + int(s) + int(ms) / 1000


# -- Parsers --

_TS_RANGE_RE = re.compile(r"(\d+:\d+:\d+[,.]\d+)\s*-->\s*(\d+:\d+:\d+[,.]\d+)")


def parse_srt(text: str) -> list[Segment]:
    """Parse SRT. Tolerant: skips malformed blocks, handles missing index line."""
    text = text.lstrip("\ufeff").strip()
    if not text:
        return []
    blocks = re.split(r"\n\s*\n", text)
    segments: list[Segment] = []
    for b in blocks:
        lines = b.strip().splitlines()
        if len(lines) < 2:
            continue
        # Timestamp may be on line 1 (with index at line 0) or line 0 (no index)
        ts_line_idx = None
        for idx in (1, 0):
            if idx < len(lines) and _TS_RANGE_RE.match(lines[idx]):
                ts_line_idx = idx
                break
        if ts_line_idx is None:
            continue
        ts_m = _TS_RANGE_RE.match(lines[ts_line_idx])
        start = parse_srt_time(ts_m.group(1))
        end = parse_srt_time(ts_m.group(2))
        content_lines = lines[ts_line_idx + 1:]
        content = "\n".join(l for l in content_lines if l.strip()).strip()
        if content:
            segments.append(Segment(start=start, end=end, text=content))
    return segments


def parse_vtt(text: str) -> list[Segment]:
    """Parse WEBVTT. Drops WEBVTT header + NOTE/STYLE blocks before the first timestamp."""
    text = text.lstrip("\ufeff").strip()
    if not text:
        return []
    lines = text.splitlines()
    # Find first line with a timestamp range
    start_idx = None
    for i, line in enumerate(lines):
        if _TS_RANGE_RE.match(line):
            start_idx = i
            # If previous non-blank line is a cue identifier (not a timestamp), include it
            j = i - 1
            while j >= 0 and not lines[j].strip():
                j -= 1
            if j >= 0 and not _TS_RANGE_RE.match(lines[j]):
                # Cue identifier present; include it as the "index" line
                start_idx = j
            break
    if start_idx is None:
        return []
    remaining = "\n".join(lines[start_idx:])
    return parse_srt(remaining)


# -- Formatters (from Segment list) --

def format_srt(segments: list[Segment]) -> str:
    if not segments:
        return ""
    parts: list[str] = []
    for i, seg in enumerate(segments, start=1):
        parts.append(str(i))
        parts.append(f"{format_srt_time(seg.start)} --> {format_srt_time(seg.end)}")
        parts.append(seg.text.strip())
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def format_vtt(segments: list[Segment]) -> str:
    parts: list[str] = ["WEBVTT", ""]
    for seg in segments:
        parts.append(f"{format_vtt_time(seg.start)} --> {format_vtt_time(seg.end)}")
        parts.append(seg.text.strip())
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def format_txt(segments: list[Segment]) -> str:
    return "\n".join(seg.text.strip() for seg in segments)


def format_lrc(segments: list[Segment]) -> str:
    return "\n".join(f"{format_lrc_time(seg.start)}{seg.text.strip()}" for seg in segments)


# -- Adapter --

def from_whisper_result(result) -> list[Segment]:
    """Convert a faster-whisper TranscribeResult to a plain Segment list."""
    return [Segment(start=s.start, end=s.end, text=s.text) for s in result.segments]


# -- Dict-shaped helpers for translate pipeline (LLM input/output) --

def segments_to_srt(segments: list[dict], start_index: int = 1) -> str:
    """Convert dict segments to SRT format string. Supports start_index for batched output."""
    lines: list[str] = []
    for i, seg in enumerate(segments, start_index):
        start_time = format_srt_time(seg["start"])
        end_time = format_srt_time(seg["end"])
        lines.append(f"{i}")
        lines.append(f"{start_time} --> {end_time}")
        lines.append(seg["text"])
        lines.append("")
    return "\n".join(lines)


def parse_srt_response(srt_text: str, original_segments: list[dict]) -> list[dict]:
    """Parse translated SRT text and return segments.

    Falls back to original text for segments that can't be parsed (LLM-robust).
    Preserves original timestamps even if the LLM modified them.
    """
    # Strip markdown code fences (some models wrap output in ```srt ... ```)
    cleaned = srt_text.strip()
    cleaned = re.sub(r'^```(?:srt)?\s*\n', '', cleaned)
    cleaned = re.sub(r'\n```\s*$', '', cleaned)

    pattern = r'(\d+)\s*\n(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})\s*\n([\s\S]*?)(?=\n\n\d+\s*\n|\n\d+\s*\n|\n*$)'
    matches = re.findall(pattern, cleaned.strip() + "\n\n")

    translated: list[dict] = []
    fallback_count = 0
    for i, orig_seg in enumerate(original_segments):
        if i < len(matches):
            _, _, _, text = matches[i]
            text_clean = text.strip()
            translated.append({
                "start": orig_seg["start"],
                "end": orig_seg["end"],
                "text": text_clean if text_clean else orig_seg["text"],
            })
        else:
            translated.append(orig_seg)
            fallback_count += 1

    if fallback_count > 0:
        logger.warning(
            f"SRT parse: {fallback_count}/{len(original_segments)} segments fell back to original "
            f"(parsed {len(matches)}, expected {len(original_segments)})"
        )
        logger.debug(f"SRT parse raw response (first 500 chars): {srt_text[:500]}")

    return translated
