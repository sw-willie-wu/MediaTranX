from app.utils.video_summary import (
    SubtitleEntry,
    parse_srt_text,
    chunk_entries_by_tokens,
)


SAMPLE_SRT = """1
00:00:01,000 --> 00:00:03,500
第一句

2
00:00:03,500 --> 00:00:06,000
第二句

3
00:00:06,000 --> 00:00:09,000
第三句
"""


def test_parse_srt_text_returns_entries_with_seconds():
    entries = parse_srt_text(SAMPLE_SRT)
    assert len(entries) == 3
    assert entries[0].start == 1.0
    assert entries[0].end == 3.5
    assert entries[0].text == "第一句"
    assert entries[2].end == 9.0


def test_parse_srt_handles_utf8_bom():
    entries = parse_srt_text("\ufeff" + SAMPLE_SRT)
    assert len(entries) == 3


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


def test_parse_srt_text_handles_empty_and_garbage():
    assert parse_srt_text("") == []
    assert parse_srt_text("not an srt") == []


def test_chunk_single_oversize_entry_still_produces_one_chunk():
    # A single cue that alone exceeds the budget should still form a chunk
    # rather than being dropped or causing an infinite loop.
    entries = [SubtitleEntry(start=0.0, end=1.0, text="中" * 500)]
    chunks = chunk_entries_by_tokens(entries, max_input_tokens=10)
    assert len(chunks) == 1
    assert chunks[0] == entries


def test_format_transcript_joins_entries_with_newline():
    from app.utils.video_summary import format_transcript
    entries = [
        SubtitleEntry(start=1.0, end=2.0, text="x"),
        SubtitleEntry(start=2.0, end=3.5, text="y"),
    ]
    assert format_transcript(entries) == "[1.0-2.0] x\n[2.0-3.5] y"


from app.utils.video_summary import (
    build_summary_prompt,
    parse_summary_json,
    parse_bullets_markdown,
    merge_chunk_outputs,
    SummaryChunkResult,
)


def test_build_summary_prompt_contains_transcript():
    entries = [SubtitleEntry(start=0.0, end=2.0, text="hello")]
    prompt = build_summary_prompt(entries, output_language="zh-TW")
    assert "[0.0-2.0] hello" in prompt
    assert "Traditional Chinese" in prompt


def test_build_summary_prompt_simplified_chinese():
    entries = [SubtitleEntry(start=0.0, end=2.0, text="hello")]
    prompt = build_summary_prompt(entries, output_language="zh-CN")
    assert "Simplified Chinese" in prompt


def test_build_summary_prompt_fallback_when_no_language():
    entries = [SubtitleEntry(start=0.0, end=2.0, text="hello")]
    prompt = build_summary_prompt(entries)
    assert "same language as the transcript" in prompt


def test_build_summary_prompt_bullets_mode_asks_for_markdown():
    entries = [SubtitleEntry(start=0.0, end=2.0, text="hello")]
    prompt = build_summary_prompt(entries, summary_mode="bullets")
    assert "Markdown" in prompt or "markdown" in prompt
    assert "[mm:ss-mm:ss]" in prompt
    # bullets mode never mentions narrative/turning_points
    assert "narrative" not in prompt
    assert "turning_points" not in prompt


def test_build_summary_prompt_narrative_mode_asks_for_json():
    entries = [SubtitleEntry(start=0.0, end=2.0, text="hello")]
    prompt = build_summary_prompt(entries, summary_mode="narrative")
    assert "JSON" in prompt
    assert "narrative" in prompt
    assert "turning_points" in prompt


# ---- bullets-mode markdown parser ----

def test_parse_bullets_markdown_extracts_timestamps_and_strips_tags():
    raw = """## 主題
### 子主題
- **活動背景：** 描述一 [01:08-01:40]
- **開發方向：** 描述二 [02:25-03:20]
"""
    result = parse_bullets_markdown(raw)
    assert len(result.bullet_items) == 2
    assert result.bullet_items[0]["time_range"] == (68.0, 100.0)
    assert result.bullet_items[1]["time_range"] == (145.0, 200.0)
    # Tags removed from rendered markdown
    assert "[01:08-01:40]" not in result.bullets_markdown
    assert "[02:25-03:20]" not in result.bullets_markdown
    # Headings preserved
    assert "## 主題" in result.bullets_markdown
    assert "### 子主題" in result.bullets_markdown


def test_parse_bullets_markdown_skips_lines_without_label_or_tag():
    raw = """## 主題
- 沒有粗體標籤的 bullet [00:00-00:30]
- **有粗體但沒時間：** 描述
- **有粗體有時間：** 描述 [01:00-01:30]
    - 巢狀子項不會被收
"""
    result = parse_bullets_markdown(raw)
    assert len(result.bullet_items) == 1
    assert result.bullet_items[0]["time_range"] == (60.0, 90.0)


def test_parse_bullets_markdown_accepts_seconds_only_format():
    raw = "- **fallback：** desc [120.5-150.0]\n"
    result = parse_bullets_markdown(raw)
    assert result.bullet_items[0]["time_range"] == (120.5, 150.0)


def test_parse_bullets_markdown_strips_code_fence():
    raw = "```markdown\n- **x：** y [00:01-00:02]\n```"
    result = parse_bullets_markdown(raw)
    assert len(result.bullet_items) == 1
    assert "```" not in result.bullets_markdown


def test_parse_bullets_markdown_line_index_points_to_correct_line():
    raw = "## H2\n\n- **a：** desc1 [00:00-00:10]\n- **b：** desc2 [00:10-00:20]\n"
    result = parse_bullets_markdown(raw)
    md_lines = result.bullets_markdown.splitlines()
    assert md_lines[result.bullet_items[0]["line_index"]].startswith("- **a")
    assert md_lines[result.bullet_items[1]["line_index"]].startswith("- **b")


# ---- narrative-mode JSON parser ----

def test_parse_summary_json_strips_code_fence():
    raw = """```json
{"narrative": {"summary": "", "turning_points": []}}
```"""
    parsed = parse_summary_json(raw)
    assert parsed.narrative_summary == ""
    assert parsed.turning_points == []


def test_parse_summary_json_rejects_invalid():
    import pytest
    with pytest.raises(ValueError):
        parse_summary_json("not json")


def test_parse_summary_json_accepts_narrative():
    raw = '{"narrative": {"summary": "s", "turning_points": [{"time": 5.0, "text": "tp"}]}}'
    parsed = parse_summary_json(raw)
    assert parsed.narrative_summary == "s"
    assert parsed.turning_points[0]["text"] == "tp"


def test_parse_summary_json_drops_turning_points_missing_time():
    raw = '{"narrative": {"summary": "s", "turning_points": [' \
          '{"text": "no time"}, {"time": "str", "text": "bad"}, ' \
          '{"time": 1.0, "text": "ok"}]}}'
    parsed = parse_summary_json(raw)
    assert len(parsed.turning_points) == 1
    assert parsed.turning_points[0]["text"] == "ok"


# ---- merge ----

def test_merge_bullets_offsets_line_index_across_chunks():
    c1 = parse_bullets_markdown("## A\n- **a1：** d [00:00-00:10]\n")
    c2 = parse_bullets_markdown("## B\n- **b1：** d [00:10-00:20]\n")
    merged = merge_chunk_outputs([c1, c2])

    md_lines = merged.bullets_markdown.splitlines()
    # Both items still point to their respective lines after concat
    assert md_lines[merged.bullet_items[0]["line_index"]].startswith("- **a1")
    assert md_lines[merged.bullet_items[1]["line_index"]].startswith("- **b1")


def test_merge_narrative_concats_summaries_and_tps():
    c1 = SummaryChunkResult(
        narrative_summary="開頭敘述。",
        turning_points=[{"time": 5.0, "text": "T1"}],
    )
    c2 = SummaryChunkResult(
        narrative_summary="後續敘述。",
        turning_points=[{"time": 15.0, "text": "T2"}],
    )
    merged = merge_chunk_outputs([c1, c2])
    assert "開頭敘述。" in merged.narrative_summary
    assert "後續敘述。" in merged.narrative_summary
    assert len(merged.turning_points) == 2


# ---- build_markdown ----

from app.utils.video_summary import build_markdown


def test_build_markdown_inserts_images_into_bullets_markdown():
    parsed = parse_bullets_markdown(
        "## 主題\n"
        "- **a：** desc [00:00-00:10]\n"
        "- **b：** desc [00:10-00:20]\n"
    )
    md = build_markdown(
        parsed,
        bullet_frames={0: "frames/b0.jpg", 1: "frames/b1.jpg"},
        tp_frames={},
        title="測試影片",
    )
    assert "# 測試影片" in md
    assert "## 主題" in md
    # Image inserted after each bullet
    assert "frames/b0.jpg" in md
    assert "frames/b1.jpg" in md
    # Indented (sub-bullet style) so it renders inside the parent bullet block
    assert "  ![](frames/b0.jpg)" in md


def test_build_markdown_renders_narrative_section_when_present():
    result = SummaryChunkResult(
        narrative_summary="整體而言這部影片...",
        turning_points=[{"time": 15.0, "text": "關鍵轉折"}],
    )
    md = build_markdown(
        result,
        bullet_frames={},
        tp_frames={0: "frames/tp_0.jpg"},
        title="測試影片",
    )
    assert "## 劇情摘要" in md
    assert "整體而言這部影片..." in md
    assert "關鍵轉折" in md
    assert "frames/tp_0.jpg" in md


def test_build_markdown_uses_english_headers_for_en_language():
    result = SummaryChunkResult(
        narrative_summary="overall narrative",
        turning_points=[{"time": 2.0, "text": "turn"}],
    )
    md = build_markdown(result, {}, {}, title="test", language="en")
    assert "## Narrative Summary" in md
    assert "### Highlights" in md
    assert "## 劇情摘要" not in md


def test_build_markdown_handles_missing_bullet_frames_gracefully():
    parsed = parse_bullets_markdown("- **x：** desc [00:00-00:10]\n")
    md = build_markdown(parsed, bullet_frames={}, tp_frames={}, title="T")
    assert "**x：**" in md
    assert "![" not in md
