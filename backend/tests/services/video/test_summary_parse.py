from app.services.video.summary_service.parse import (
    SubtitleEntry,
    chunk_entries_by_tokens,
)


def test_chunk_entries_by_tokens_splits_when_budget_exceeded():
    entries = [
        SubtitleEntry(start=float(i), end=float(i + 1),
                      text="中文句子" * 20)
        for i in range(20)
    ]
    # Small budget forces multiple chunks
    chunks = chunk_entries_by_tokens(entries, max_input_tokens=200)
    assert len(chunks) >= 2
    # All entries covered, no duplicates
    total = sum(len(c) for c in chunks)
    assert total == 20
    # Chunks in order
    for chunk in chunks:
        for i in range(len(chunk) - 1):
            assert chunk[i].start <= chunk[i + 1].start


def test_chunk_single_when_budget_large():
    entries = [SubtitleEntry(start=0.0, end=1.0, text="短")]
    chunks = chunk_entries_by_tokens(entries, max_input_tokens=10000)
    assert len(chunks) == 1
    assert chunks[0] == entries


def test_chunk_single_oversize_entry_still_produces_one_chunk():
    # A single cue that alone exceeds the budget should still form a chunk
    # rather than being dropped or causing an infinite loop.
    entries = [SubtitleEntry(start=0.0, end=1.0, text="中" * 500)]
    chunks = chunk_entries_by_tokens(entries, max_input_tokens=10)
    assert len(chunks) == 1
    assert chunks[0] == entries


# ---- format_transcript_numbered (bullets mode, [L<n>] line numbers) ----

def test_format_transcript_numbered_single_chunk():
    from app.services.video.summary_service.parse import format_transcript_numbered
    entries = [
        SubtitleEntry(start=0.0, end=1.0, text="a"),
        SubtitleEntry(start=1.0, end=2.0, text="b"),
    ]
    assert format_transcript_numbered(entries) == "[L1] a\n[L2] b"


def test_format_transcript_numbered_offset_continues_across_chunks():
    from app.services.video.summary_service.parse import format_transcript_numbered
    entries = [
        SubtitleEntry(start=0.0, end=1.0, text="x"),
        SubtitleEntry(start=1.0, end=2.0, text="y"),
    ]
    assert format_transcript_numbered(entries, start_index=4) == "[L4] x\n[L5] y"


from app.utils.prompts import build_summary_prompt
from app.services.video.summary_service.parse import (
    format_transcript_numbered,
    parse_bullets_markdown,
    parse_narrative_paragraphs,
    merge_chunk_outputs,
    resolve_line_windows,
    SummaryChunkResult,
)
from app.services.video.summary_service.markdown import build_markdown


def _bullets_prompt_for(entries, **kwargs):
    """Bullets-mode prompt: transcript carries [L<n>] line numbers."""
    return build_summary_prompt(
        format_transcript_numbered(entries), summary_mode="bullets", **kwargs
    )


def _narrative_prompt_for(entries, **kwargs):
    """Narrative-mode prompt: transcript carries [L<n>] line numbers."""
    return build_summary_prompt(
        format_transcript_numbered(entries), summary_mode="narrative", **kwargs
    )


def test_build_summary_prompt_contains_transcript():
    entries = [SubtitleEntry(start=0.0, end=2.0, text="hello")]
    prompt = _bullets_prompt_for(entries, output_language="zh-TW")
    assert "[L1] hello" in prompt
    assert "Traditional Chinese" in prompt


def test_build_summary_prompt_simplified_chinese():
    entries = [SubtitleEntry(start=0.0, end=2.0, text="hello")]
    prompt = _bullets_prompt_for(entries, output_language="zh-CN")
    assert "Simplified Chinese" in prompt


def test_build_summary_prompt_fallback_when_no_language():
    entries = [SubtitleEntry(start=0.0, end=2.0, text="hello")]
    prompt = _bullets_prompt_for(entries)
    assert "same language as the transcript" in prompt


def test_build_summary_prompt_bullets_mode_asks_for_line_cites():
    entries = [SubtitleEntry(start=0.0, end=2.0, text="hello")]
    prompt = _bullets_prompt_for(entries)
    assert "Markdown" in prompt or "markdown" in prompt
    # bullets mode cites line numbers, never timestamps
    assert "[L<first>-L<last>]" in prompt
    assert "[mm:ss-mm:ss]" not in prompt
    # bullets mode never mentions narrative/turning_points
    assert "narrative" not in prompt
    assert "turning_points" not in prompt


def test_build_summary_prompt_narrative_mode_asks_for_prose_with_line_cites():
    entries = [SubtitleEntry(start=0.0, end=2.0, text="hello")]
    prompt = _narrative_prompt_for(entries)
    # narrative mode is prose with line-number citations, never JSON output / timestamps
    assert "turning_points" not in prompt
    assert "[L<first>-L<last>]" in prompt
    assert "[mm:ss-mm:ss]" not in prompt
    # must not ask LLM to produce a JSON object (old prompt did)
    assert '"narrative"' not in prompt
    assert "Output JSON only" not in prompt


# ---- bullets-mode markdown parser ([L<a>-L<b>] line citations) ----

def test_parse_bullets_markdown_extracts_line_ranges_and_strips_tags():
    raw = """## 主題
### 子主題
- **活動背景：** 描述一 [L3-L9]
- **開發方向：** 描述二 [L10-L18]
"""
    result = parse_bullets_markdown(raw)
    assert len(result.bullet_items) == 2
    assert result.bullet_items[0]["line_range"] == (3, 9)
    assert result.bullet_items[1]["line_range"] == (10, 18)
    # Cite tags removed from rendered markdown
    assert "[L3-L9]" not in result.bullets_markdown
    assert "[L10-L18]" not in result.bullets_markdown
    # Headings preserved
    assert "## 主題" in result.bullets_markdown
    assert "### 子主題" in result.bullets_markdown


def test_parse_bullets_markdown_skips_lines_without_label_or_cite():
    raw = """## 主題
- 沒有粗體標籤的 bullet [L1-L3]
- **有粗體但沒引用：** 描述
- **有粗體有引用：** 描述 [L4-L9]
    - 巢狀子項不會被收 [L10-L12]
"""
    result = parse_bullets_markdown(raw)
    assert len(result.bullet_items) == 1
    assert result.bullet_items[0]["line_range"] == (4, 9)
    # Cite stripped from render even on lines that were NOT recorded
    assert "[L1-L3]" not in result.bullets_markdown
    assert "[L10-L12]" not in result.bullets_markdown


def test_parse_bullets_markdown_single_line_cite():
    raw = "- **單行：** 描述 [L7-L7]\n"
    result = parse_bullets_markdown(raw)
    assert result.bullet_items[0]["line_range"] == (7, 7)


def test_parse_bullets_markdown_does_not_strip_plain_brackets():
    # A plain numeric bracket is legitimate content and must survive; only the
    # distinctive `[L<a>-L<b>]` token is stripped.
    raw = "- **價格：** 票價區間 [80-120]\n- **章節：** 詳見 [L5-L8]\n"
    result = parse_bullets_markdown(raw)
    assert "[80-120]" in result.bullets_markdown
    assert "[L5-L8]" not in result.bullets_markdown
    assert len(result.bullet_items) == 1
    assert result.bullet_items[0]["line_range"] == (5, 8)


def test_parse_bullets_markdown_strips_code_fence():
    raw = "```markdown\n- **x：** y [L1-L2]\n```"
    result = parse_bullets_markdown(raw)
    assert len(result.bullet_items) == 1
    assert "```" not in result.bullets_markdown


def test_parse_bullets_markdown_line_index_points_to_correct_line():
    raw = "## H2\n\n- **a：** desc1 [L1-L2]\n- **b：** desc2 [L3-L4]\n"
    result = parse_bullets_markdown(raw)
    md_lines = result.bullets_markdown.splitlines()
    assert md_lines[result.bullet_items[0]["line_index"]].startswith("- **a")
    assert md_lines[result.bullet_items[1]["line_index"]].startswith("- **b")


# ---- resolve_line_windows (line range -> real Whisper time window) ----

def _entries(n):
    return [SubtitleEntry(start=float(i), end=float(i) + 0.5, text=f"t{i}")
            for i in range(n)]


def test_resolve_line_windows_basic():
    entries = _entries(6)
    items = [{"line_index": 0, "line_range": (2, 5)}]
    resolve_line_windows(items, entries)
    # 1-based (2,5) -> 0-based idx 1..4
    assert items[0]["time_range"] == (entries[1].start, entries[4].end)


def test_resolve_line_windows_single_line():
    entries = _entries(6)
    items = [{"line_index": 0, "line_range": (3, 3)}]
    resolve_line_windows(items, entries)
    assert items[0]["time_range"] == (entries[2].start, entries[2].end)


def test_resolve_line_windows_clamps_out_of_range():
    entries = _entries(4)
    items = [{"line_index": 0, "line_range": (0, 999)}]
    resolve_line_windows(items, entries)
    # 0 -> clamp to 1 -> idx0 ; 999 -> clamp to 4 -> idx3
    assert items[0]["time_range"] == (entries[0].start, entries[3].end)


def test_resolve_line_windows_inverted_is_dropped():
    entries = _entries(6)
    # (8,3): clamp -> (6,3) -> idx (5,2) still inverted -> None
    items = [{"line_index": 0, "line_range": (8, 3)}]
    resolve_line_windows(items, entries)
    assert items[0]["time_range"] is None


def test_resolve_line_windows_single_entry():
    entries = [SubtitleEntry(start=5.0, end=9.0, text="only")]
    items = [{"line_index": 0, "line_range": (3, 7)}]  # both clamp to 1 -> idx0
    resolve_line_windows(items, entries)
    assert items[0]["time_range"] == (5.0, 9.0)


def test_resolve_line_windows_empty_entries():
    items = [{"line_index": 0, "line_range": (1, 2)}]
    resolve_line_windows(items, [])
    assert items[0]["time_range"] is None


def test_resolve_line_windows_empty_items_no_crash():
    resolve_line_windows([], _entries(3))  # must not raise


def test_resolve_line_windows_none_line_range_sets_none():
    """A cite-less paragraph (line_range=None) -> time_range=None, no crash."""
    entries = _entries(6)
    items = [{"line_range": None}]
    resolve_line_windows(items, entries)
    assert items[0]["time_range"] is None


# ---- narrative-mode paragraph parser ----

def test_parse_narrative_paragraphs_basic():
    raw = (
        "第一段敘事內容，連貫描述開頭。 [L1-L8]\n\n"
        "第二段敘事內容，描述中段發展。 [L9-L20]\n"
    )
    result = parse_narrative_paragraphs(raw)
    assert len(result.narrative_paragraphs) == 2
    p0, p1 = result.narrative_paragraphs
    assert p0["text"] == "第一段敘事內容，連貫描述開頭。"
    assert p0["line_range"] == (1, 8)
    assert p0["time_range"] is None          # filled later by resolve_line_windows
    assert p1["line_range"] == (9, 20)


def test_parse_narrative_paragraphs_multiline_block():
    """段落本身可跨多行；cite 在段落區塊末端。"""
    raw = "這段有兩行。\n第二行接續。 [L3-L7]"
    result = parse_narrative_paragraphs(raw)
    assert len(result.narrative_paragraphs) == 1
    assert result.narrative_paragraphs[0]["text"] == "這段有兩行。\n第二行接續。"
    assert result.narrative_paragraphs[0]["line_range"] == (3, 7)


def test_parse_narrative_paragraphs_keeps_block_without_cite():
    """無 cite 的段落仍保留文字，line_range=None（後續無圖）。"""
    raw = "有引用的段落。 [L1-L4]\n\n沒有引用的段落。"
    result = parse_narrative_paragraphs(raw)
    assert len(result.narrative_paragraphs) == 2
    assert result.narrative_paragraphs[1]["text"] == "沒有引用的段落。"
    assert result.narrative_paragraphs[1]["line_range"] is None


def test_parse_narrative_paragraphs_strips_code_fence():
    raw = "```\n敘事段落。 [L1-L2]\n```"
    result = parse_narrative_paragraphs(raw)
    assert len(result.narrative_paragraphs) == 1
    p = result.narrative_paragraphs[0]
    assert p["text"] == "敘事段落。"
    assert p["line_range"] == (1, 2)
    assert "```" not in p["text"]


def test_parse_narrative_paragraphs_empty_raises():
    import pytest
    with pytest.raises(ValueError):
        parse_narrative_paragraphs("   \n\n  ")


def test_parse_narrative_paragraphs_cite_only_block_dropped():
    """A block that is only a cite tag has no prose -> dropped."""
    raw = "[L1-L5]\n\n正常段落。 [L6-L10]"
    result = parse_narrative_paragraphs(raw)
    assert len(result.narrative_paragraphs) == 1
    assert result.narrative_paragraphs[0]["line_range"] == (6, 10)


def test_parse_narrative_paragraphs_does_not_strip_mid_block_bracket():
    """段落中間合法出現的 [L..] 不該被剝；只剝段落末端的 cite。"""
    raw = "提到 [L5-L9] 這個區段的內容很重要。 [L1-L20]"
    result = parse_narrative_paragraphs(raw)
    assert len(result.narrative_paragraphs) == 1
    assert result.narrative_paragraphs[0]["line_range"] == (1, 20)
    assert "[L5-L9]" in result.narrative_paragraphs[0]["text"]


# ---- merge ----

def test_merge_bullets_offsets_line_index_across_chunks():
    c1 = parse_bullets_markdown("## A\n- **a1：** d [L1-L5]\n")
    c2 = parse_bullets_markdown("## B\n- **b1：** d [L6-L9]\n")
    merged = merge_chunk_outputs([c1, c2])

    md_lines = merged.bullets_markdown.splitlines()
    # Both items still point to their respective lines after concat
    assert md_lines[merged.bullet_items[0]["line_index"]].startswith("- **a1")
    assert md_lines[merged.bullet_items[1]["line_index"]].startswith("- **b1")
    # line_range is a global transcript cite — NOT offset by merge
    assert merged.bullet_items[0]["line_range"] == (1, 5)
    assert merged.bullet_items[1]["line_range"] == (6, 9)


def test_merge_narrative_paragraphs_concatenated():
    c1 = SummaryChunkResult(narrative_paragraphs=[
        {"text": "段一", "line_range": (1, 5), "time_range": None},
    ])
    c2 = SummaryChunkResult(narrative_paragraphs=[
        {"text": "段二", "line_range": (6, 9), "time_range": None},
    ])
    merged = merge_chunk_outputs([c1, c2])
    assert [p["text"] for p in merged.narrative_paragraphs] == ["段一", "段二"]
    assert merged.narrative_paragraphs[1]["line_range"] == (6, 9)


# ---- build_markdown ----

def test_build_markdown_inserts_images_into_bullets_markdown():
    parsed = parse_bullets_markdown(
        "## 主題\n"
        "- **a：** desc [L1-L2]\n"
        "- **b：** desc [L3-L4]\n"
    )
    md = build_markdown(
        parsed,
        bullet_frames={0: "frames/b0.jpg", 1: "frames/b1.jpg"},
        para_frames={},
        title="測試影片",
    )
    assert "# 測試影片" in md
    assert "## 主題" in md
    # Image inserted after each bullet
    assert "frames/b0.jpg" in md
    assert "frames/b1.jpg" in md
    # Indented (sub-bullet style) so it renders inside the parent bullet block
    assert "  ![](frames/b0.jpg)" in md


def test_build_markdown_renders_narrative_paragraphs_with_images():
    result = SummaryChunkResult(narrative_paragraphs=[
        {"text": "第一段敘事。", "line_range": (1, 5), "time_range": (0.0, 5.0)},
        {"text": "第二段敘事。", "line_range": (6, 9), "time_range": (5.0, 9.0)},
    ])
    md = build_markdown(
        result,
        bullet_frames={},
        para_frames={0: "frames/para_000.jpg"},   # only para 0 has an image
        title="測試影片",
    )
    assert "# 測試影片" in md
    assert "第一段敘事。" in md
    assert "第二段敘事。" in md
    assert "![](frames/para_000.jpg)" in md
    # narrative mode has no headings / no turning-point section
    assert "## " not in md.replace("# 測試影片", "")
    assert "### " not in md



def test_build_markdown_handles_missing_bullet_frames_gracefully():
    parsed = parse_bullets_markdown("- **x：** desc [L1-L2]\n")
    md = build_markdown(parsed, bullet_frames={}, para_frames={}, title="T")
    assert "**x：**" in md
    assert "![" not in md


# ── perf/video-summary-bullet-cap-scene-once ───────────────────────────
import pytest as _pytest
from app.services.video.summary_service.parse import (
    compute_bullet_target,
    even_indices,
)


@_pytest.mark.parametrize("content_sec,expected", [
    (180.0, 8),     # 3min → round(4.5)→ clamp floor 8
    (600.0, 15),    # 10min → 15
    (2400.0, 40),   # 40min → 60 → clamp ceil 40
    (7200.0, 40),   # 120min → 180 → 40
    (0.0, 8),       # degenerate → floor 8
])
def test_compute_bullet_target(content_sec, expected):
    assert compute_bullet_target(content_sec) == expected


def test_even_indices_basic():
    assert even_indices(50, 8) == [0, 7, 14, 21, 28, 35, 42, 49]


@_pytest.mark.parametrize("n,k", [(2, 8), (8, 8), (5, 10)])
def test_even_indices_k_ge_n_is_range(n, k):
    assert even_indices(n, k) == list(range(n))


def test_even_indices_edge_cases():
    assert even_indices(0, 8) == []
    assert even_indices(10, 1) == [0]      # defensive guard (unreachable in prod)
    assert even_indices(10, 0) == [0]


@_pytest.mark.parametrize("n,k", [(50, 8), (109, 40), (41, 40), (100, 7), (9, 8)])
def test_even_indices_unique_sorted_in_range(n, k):
    idx = even_indices(n, k)
    assert idx == sorted(idx)
    assert len(idx) == len(set(idx))           # unique
    assert len(idx) == k
    assert idx[0] == 0 and idx[-1] == n - 1    # spans both ends
    assert all(0 <= i < n for i in idx)


def test_bullets_prompt_rule3_relaxed():
    entries = [SubtitleEntry(start=0.0, end=5.0, text="hello")]
    p = _bullets_prompt_for(entries)
    assert "60 seconds" not in p              # hard split rule removed
    assert "[L<first>-L<last>]" in p          # line-citation contract kept
    assert "narrative" not in p and "turning_points" not in p
