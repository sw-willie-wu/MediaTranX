"""SPIKE-E: gemma4-E4B streaming tool call probe — 3 trials.

Tests whether gemma4-E4B (Gemma 4 Expert 4B, Google MoE architecture)
can reliably emit tool calls via llama-server, to inform whether
spec §5.5.1 conservative decision (gemma4 excluded from "tools" capability)
should be updated.

Acceptance criteria per trial:
  1. Stream emits >= 1 ToolCallChunkEvent (tool_calls delta in SSE stream)
  2. Accumulated arguments = valid JSON
  3. name == "set_field"
  4. Parsed JSON has field == non-empty string
  5. Parsed JSON value contains "x4plus" (case-insensitive)

Verdict:
  STRONG-PASS  : 3/3 trials PASS all ACs
  PASS-with-caveats : 2/3 trials PASS
  FAIL         : 0-1/3 trials PASS

Usage:
    uv run --project core/backend python scripts/_spike_agent_e_gemma_tools.py
"""
from __future__ import annotations

import json
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# ---------------------------------------------------------------------------
# Path discovery
# ---------------------------------------------------------------------------

BACKEND_DIR = Path(__file__).parent.parent  # core/backend/
LLAMA_BIN = BACKEND_DIR / "bin" / "llama" / "llama-server.exe"
MODEL_PATH = BACKEND_DIR / "models" / "gemma4" / "gemma-4-e4b-it-Q4_K_M.gguf"

STARTUP_TIMEOUT = 300  # seconds — gemma4 is larger, give extra time

NUM_TRIALS = 3

# ---------------------------------------------------------------------------
# Tool definition (same as SPIKE-B for apples-to-apples comparison)
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "set_field",
            "description": "Set a field on the active panel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {"type": "string"},
                    "value": {},
                },
                "required": ["field", "value"],
            },
        },
    }
]

# Same system + user prompt as SPIKE-B (zh-TW system prompt per spec §5.8)
MESSAGES = [
    {"role": "system", "content": "你是 MediaTranX 工具呼叫測試 agent。"},
    {
        "role": "user",
        "content": "請呼叫 set_field 把 model 設為 realesrgan-x4plus",
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_free_port(start: int = 19380, end: int = 19480) -> int:
    for port in range(start, end):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("No free port found")


def _wait_ready(port: int, proc: subprocess.Popen, timeout: int = STARTUP_TIMEOUT) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"llama-server exited unexpectedly (rc={proc.returncode})")
        try:
            url = f"http://127.0.0.1:{port}/health"
            with urllib.request.urlopen(url, timeout=2) as resp:
                data = json.loads(resp.read())
                if data.get("status") == "ok":
                    return
        except Exception:
            pass
        time.sleep(0.5)
    raise TimeoutError(f"llama-server startup timed out ({timeout}s)")


def _start_server(port: int) -> subprocess.Popen:
    cmd = [
        str(LLAMA_BIN),
        "--model", str(MODEL_PATH),
        "--port", str(port),
        "--host", "127.0.0.1",
        "--ctx-size", "4096",
        "--n-gpu-layers", "99",
        "--jinja",
    ]

    print(f"  CMD: {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        cwd=str(LLAMA_BIN.parent),
    )
    print(f"  PID: {proc.pid}  waiting for /health ...")
    _wait_ready(port, proc)
    print(f"  Server ready on port {port}")
    return proc


def _stop_server(proc: subprocess.Popen) -> None:
    try:
        proc.terminate()
        proc.wait(timeout=15)
    except Exception:
        try:
            proc.kill()
            proc.wait(timeout=5)
        except Exception:
            pass
    print(f"  Server stopped (rc={proc.poll()})")


# ---------------------------------------------------------------------------
# OpenAI streaming tool_calls accumulator (same logic as SPIKE-B)
# ---------------------------------------------------------------------------


def _accumulate_tool_calls(port: int, payload: dict) -> tuple[list[dict], dict | None]:
    """Stream /v1/chat/completions and accumulate tool_calls."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    tool_calls_buf: dict[int, dict] = {}
    chunk_count = 0
    tool_call_chunk_count = 0
    usage: dict | None = None
    # Also capture plain text content (for models that respond in text instead of tool_calls)
    content_buf = ""
    finish_reason = None

    with urllib.request.urlopen(req, timeout=120) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            payload_str = line[len("data:"):].strip()
            if payload_str == "[DONE]":
                break
            try:
                chunk = json.loads(payload_str)
            except json.JSONDecodeError:
                continue

            chunk_count += 1

            if "usage" in chunk and chunk["usage"] is not None:
                usage = chunk["usage"]

            choices = chunk.get("choices", [])
            if not choices:
                continue
            delta = choices[0].get("delta", {})
            if "finish_reason" in choices[0] and choices[0]["finish_reason"]:
                finish_reason = choices[0]["finish_reason"]

            # Capture text content (for diagnosis if no tool_calls)
            if delta.get("content"):
                content_buf += delta["content"]

            tc_deltas = delta.get("tool_calls", [])
            for tc_delta in tc_deltas:
                idx = tc_delta.get("index", 0)
                if idx not in tool_calls_buf:
                    tool_calls_buf[idx] = {"id": "", "name": "", "args_buf": ""}
                if tc_delta.get("id"):
                    tool_calls_buf[idx]["id"] = tc_delta["id"]
                fn = tc_delta.get("function", {})
                if fn.get("name"):
                    tool_calls_buf[idx]["name"] = fn["name"]
                if fn.get("arguments"):
                    tool_calls_buf[idx]["args_buf"] += fn["arguments"]
                    tool_call_chunk_count += 1

    print(f"  Total SSE data chunks: {chunk_count}")
    print(f"  tool_call delta chunks: {tool_call_chunk_count}")
    print(f"  finish_reason: {finish_reason!r}")
    if content_buf:
        print(f"  text content (truncated): {content_buf[:200]!r}")

    tool_calls_list = [
        {"id": v["id"], "name": v["name"], "arguments": v["args_buf"]}
        for v in sorted(tool_calls_buf.values(), key=lambda x: list(tool_calls_buf.keys())[list(tool_calls_buf.values()).index(x)])
    ]
    return tool_calls_list, usage


# ---------------------------------------------------------------------------
# Single trial
# ---------------------------------------------------------------------------


def _run_trial(port: int, trial_num: int) -> dict:
    """Run one tool-call trial. Returns trial result dict."""
    print(f"\n  --- Trial {trial_num} ---")
    t0 = time.time()

    payload = {
        "model": "local",
        "messages": MESSAGES,
        "tools": TOOLS,
        "max_tokens": 512,
        "temperature": 0.1,
        "stream": True,
        "stream_options": {"include_usage": True},
    }

    try:
        tool_calls_result, usage_result = _accumulate_tool_calls(port, payload)
        elapsed = time.time() - t0
    except Exception as e:
        elapsed = time.time() - t0
        print(f"  ERROR during trial {trial_num}: {e}")
        return {
            "trial": trial_num,
            "elapsed_s": round(elapsed, 1),
            "error": str(e),
            "tool_calls": [],
            "usage": None,
            "checks": [],
            "passed": False,
            "failure_reason": str(e),
        }

    print(f"  Accumulated tool_calls ({len(tool_calls_result)}):")
    for tc in tool_calls_result:
        print(f"    id={tc['id']!r}  name={tc['name']!r}")
        print(f"    arguments_raw: {tc['arguments']!r}")
    print(f"  Usage: {usage_result}")
    print(f"  Elapsed: {elapsed:.1f}s")

    checks = []

    # AC1: >= 1 tool call
    if len(tool_calls_result) >= 1:
        checks.append(("AC1: >=1 tool_call", True, f"got {len(tool_calls_result)}"))
    else:
        checks.append(("AC1: >=1 tool_call", False, "got 0 tool_calls"))

    # AC2: name == "set_field"
    if tool_calls_result:
        name = tool_calls_result[0]["name"]
        checks.append(("AC2: name==set_field", name == "set_field", f"got {name!r}"))
    else:
        checks.append(("AC2: name==set_field", False, "no tool_calls"))

    # AC3: arguments is valid JSON
    parsed_args = None
    if tool_calls_result:
        try:
            parsed_args = json.loads(tool_calls_result[0]["arguments"])
            checks.append(("AC3: valid JSON args", True, f"{parsed_args}"))
        except json.JSONDecodeError as e:
            checks.append(("AC3: valid JSON args", False, f"JSONDecodeError: {e}"))

    # AC4: field is a non-empty string
    if parsed_args is not None:
        field_val = parsed_args.get("field", "")
        checks.append(("AC4: field is non-empty str", bool(field_val), f"got {field_val!r}"))
    else:
        checks.append(("AC4: field is non-empty str", False, "no parsed args"))

    # AC5: value contains "x4plus" (case-insensitive)
    if parsed_args is not None:
        value_str = str(parsed_args.get("value", "")).lower()
        checks.append(("AC5: value contains x4plus", "x4plus" in value_str, f"got {value_str!r}"))
    else:
        checks.append(("AC5: value contains x4plus", False, "no parsed args"))

    all_ok = all(ok for _, ok, _ in checks)
    failure_reason = next((f"{label}: {detail}" for label, ok, detail in checks if not ok), None)

    print("  Acceptance criteria:")
    for label, ok, detail in checks:
        marker = "[OK]" if ok else "[NO]"
        print(f"    {marker} {label}: {detail}")

    return {
        "trial": trial_num,
        "elapsed_s": round(elapsed, 1),
        "error": None,
        "tool_calls": tool_calls_result,
        "usage": usage_result,
        "checks": checks,
        "passed": all_ok,
        "failure_reason": failure_reason,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 60)
    print("SPIKE-E: gemma4-E4B streaming tool call probe (3 trials)")
    print("=" * 60)

    if not LLAMA_BIN.exists():
        print(f"FATAL: llama-server binary not found: {LLAMA_BIN}")
        sys.exit(1)
    if not MODEL_PATH.exists():
        print(f"FATAL: model not found: {MODEL_PATH}")
        sys.exit(1)

    model_size_mb = MODEL_PATH.stat().st_size / (1024 * 1024)
    print(f"\n  Binary : {LLAMA_BIN}")
    print(f"  Model  : {MODEL_PATH}")
    print(f"  Size   : {model_size_mb:.0f} MB")

    port = _find_free_port()
    proc = None
    trials: list[dict] = []

    try:
        print(f"\n  Starting llama-server with --jinja on port {port} ...")
        proc = _start_server(port)

        for i in range(1, NUM_TRIALS + 1):
            result = _run_trial(port, i)
            trials.append(result)

    except Exception as e:
        print(f"\n  FATAL EXCEPTION: {e}")
        import traceback
        traceback.print_exc()
    finally:
        if proc:
            _stop_server(proc)

    # Summary
    passes = sum(1 for t in trials if t["passed"])
    print("\n" + "=" * 60)
    print(f"SPIKE-E SUMMARY: {passes}/{len(trials)} trials PASSED")
    for t in trials:
        status = "PASS" if t["passed"] else "FAIL"
        reason = f" — {t['failure_reason']}" if not t["passed"] else ""
        print(f"  Trial {t['trial']}: {status} ({t['elapsed_s']}s){reason}")

    if passes == 3:
        verdict = "STRONG-PASS"
    elif passes == 2:
        verdict = "PASS-with-caveats"
    else:
        verdict = "FAIL"

    print(f"\n  Verdict: {verdict}")
    print("=" * 60)

    return {
        "trials": trials,
        "passes": passes,
        "verdict": verdict,
    }


if __name__ == "__main__":
    main()
