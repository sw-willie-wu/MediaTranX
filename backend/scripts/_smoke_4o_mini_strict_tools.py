"""L3 real-AI smoke harness for gpt-4o-mini strict tool calling.

Spec: core/.claude/specs/2026-05-27-openai-strict-tool-calling-design.md §9.3

Run:
    set OPENAI_API_KEY=sk-...
    cd core/backend && uv run python scripts/_smoke_4o_mini_strict_tools.py

Cost: ~16 calls × 200-500 tokens at gpt-4o-mini pricing ≈ < $0.01 USD.

TODO: when useAgentTools.TOOLS changes, update FRONTEND_TOOLS below
(spec §11 follow-up: auto-dump from frontend).
"""
import json
import os
import sys

# Add backend root to sys.path so app imports work
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.adapters.ai.remote.openai import OpenAIProvider


# Mirror of core/frontend/src/composables/useAgentTools.ts:76-160
FRONTEND_TOOLS = [
    # ... (copy from test_openai_strict_tools.py TestRealShapeSanity.FRONTEND_TOOLS)
    # For brevity, import from the test module if possible — see below
]

# Reuse the test fixture to stay DRY
try:
    from tests.adapters.ai.remote.test_openai_strict_tools import TestRealShapeSanity
    FRONTEND_TOOLS = TestRealShapeSanity.FRONTEND_TOOLS
except ImportError:
    print("WARNING: could not import test fixture, FRONTEND_TOOLS may be stale", file=sys.stderr)


def run_one(prov: OpenAIProvider, prompt: str, label: str) -> dict:
    """Single call to chat_completions_stream; return {emitted, args, raw}.

    Emits "emitted" = first tool name seen, "args" = parsed JSON if any,
    "raw" = list of raw chunks for debugging.
    """
    raw_chunks = []
    tool_name = None
    args_str = ""
    for chunk in prov.chat_completions_stream(
        model="gpt-4o-mini",
        messages=[{"role": "user", "content": prompt}],
        tools=FRONTEND_TOOLS,
    ):
        raw_chunks.append(chunk)
        for choice in chunk.get("choices", []):
            delta = choice.get("delta") or {}
            tcs = delta.get("tool_calls") or []
            for tc in tcs:
                fn = tc.get("function") or {}
                if fn.get("name"):
                    tool_name = tool_name or fn["name"]
                if "arguments" in fn:
                    args_str += fn["arguments"]

    args = None
    if args_str:
        try:
            args = json.loads(args_str)
        except json.JSONDecodeError:
            args = {"__parse_error__": args_str}

    print(f"[{label}] emitted={tool_name!r} args={args!r}")
    return {"emitted": tool_name, "args": args, "raw_count": len(raw_chunks)}


def main():
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        sys.exit("OPENAI_API_KEY env var required")
    prov = OpenAIProvider("https://api.openai.com", key)

    results = {"set_field": [], "zero_arg": [], "execute": []}

    # Segment 1: agent 起手 — should hit navigate_to / select_subfunction
    print("=== Segment 1: agent kickoff (N=10) ===")
    for i in range(10):
        results["set_field"].append(run_one(
            prov,
            "我有一個影片想轉成 1080p MP4 格式",
            f"kickoff#{i + 1}",
        ))

    # Segment 2: zero-arg list_files coverage
    print("=== Segment 2: list_files (N=3) ===")
    for i in range(3):
        results["zero_arg"].append(run_one(
            prov,
            "列出目前上傳的檔案",
            f"list_files#{i + 1}",
        ))

    # Segment 3: click_execute coverage (panel pre-filled implied by prompt)
    print("=== Segment 3: click_execute (N=3) ===")
    for i in range(3):
        results["execute"].append(run_one(
            prov,
            "panel 已經設定好了、執行吧",
            f"execute#{i + 1}",
        ))

    # Summary
    print("\n=== Summary ===")
    s1_pass = sum(
        1 for r in results["set_field"]
        if r["emitted"] in ("navigate_to", "select_subfunction") and r["args"]
    )
    print(f"Segment 1 (need >= 10/10 emit valid tool call): {s1_pass}/10")
    s2_pass = sum(1 for r in results["zero_arg"] if r["emitted"] is not None)
    print(f"Segment 2 (zero-arg list_files no 400): {s2_pass}/3")
    s3_pass = sum(1 for r in results["execute"] if r["emitted"] is not None)
    print(f"Segment 3 (zero-arg click_execute no 400): {s3_pass}/3")

    if s1_pass < 10:
        sys.exit(1)
    if s2_pass < 1 or s3_pass < 1:
        # Spec accepts at least 1 zero-arg coverage each, 0 errors
        sys.exit(1)
    print("PASS")


if __name__ == "__main__":
    main()
