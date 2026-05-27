"""SPIKE Phase 2.A: qwen3.5:9b GGUF streaming tool call + enum probe.

Mirrors SPIKE-E (gemma4) but for qwen3.5:9b + adds enum-honor verification.

ACs per spec §7.2:
  AC-SPIKE-1: 5 trials @ temperature=0, top_k=1, >=4/5 emit valid tool_calls[]
  AC-SPIKE-2: model does NOT emit field outside enum [mode, format, scale]
  AC-SPIKE-3: re-run 1 trial without --jinja; if tool_calls still emitted,
              jinja is optional; else required

Verdict:
  PASS-FULL: AC-1 PASS + AC-2 strong + AC-3 documented
  PASS-DISPATCHER-GUARD: AC-1 PASS but AC-2 WEAK (dispatcher守底有意義)
  FAIL: AC-1 FAIL (qwen3.5 不可用 agent -> F3 取消)

Usage:
    uv run --project core/backend python scripts/_spike_phase2a_qwen35_tools.py
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

BACKEND_DIR = Path(__file__).parent.parent  # core/backend/
LLAMA_BIN = BACKEND_DIR / "bin" / "llama" / "llama-server.exe"
MODEL_PATH = BACKEND_DIR / "models" / "qwen3.5" / "Qwen3.5-9B-Q4_K_M.gguf"

STARTUP_TIMEOUT = 300
NUM_TRIALS = 5

TOOLS_WITH_ENUM = [
    {
        "type": "function",
        "function": {
            "name": "set_field",
            "description": "Set a field on the active panel.",
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {
                        "type": "string",
                        "enum": ["mode", "format", "scale"],
                    },
                    "value": {},
                },
                "required": ["field", "value"],
            },
        },
    }
]

MESSAGES = [
    {"role": "system", "content": "你是 MediaTranX 工具呼叫測試 agent。"},
    {
        "role": "user",
        "content": "請呼叫 set_field 把 mode 設為 anime。只呼叫工具、不要回文字。",
    },
]


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


def _start_server(port: int, jinja: bool) -> subprocess.Popen:
    cmd = [
        str(LLAMA_BIN),
        "--model", str(MODEL_PATH),
        "--port", str(port),
        "--host", "127.0.0.1",
        "--ctx-size", "4096",
        "--n-gpu-layers", "99",
    ]
    if jinja:
        cmd.append("--jinja")
    print(f"  CMD: {' '.join(cmd)}")
    proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=str(LLAMA_BIN.parent))
    print(f"  PID: {proc.pid}  waiting for /health ...")
    _wait_ready(port, proc)
    print(f"  Server ready on port {port} (jinja={jinja})")
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


def _accumulate_tool_calls(port: int, payload: dict) -> tuple[list[dict], str, dict | None]:
    """Stream /v1/chat/completions; return (tool_calls, text_content, usage)."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    tool_calls_buf: dict[int, dict] = {}
    content_buf = ""
    usage: dict | None = None

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

            if "usage" in chunk and chunk["usage"] is not None:
                usage = chunk["usage"]
            choices = chunk.get("choices", [])
            if not choices:
                continue
            delta = choices[0].get("delta", {})
            if delta.get("content"):
                content_buf += delta["content"]

            for tc_delta in delta.get("tool_calls", []):
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

    tool_calls = [
        {"id": v["id"], "name": v["name"], "arguments": v["args_buf"]}
        for v in tool_calls_buf.values()
    ]
    return tool_calls, content_buf, usage


def _run_trial(port: int, trial_num: int) -> dict:
    print(f"\n  --- Trial {trial_num} ---")
    t0 = time.time()
    payload = {
        "model": "local",
        "messages": MESSAGES,
        "tools": TOOLS_WITH_ENUM,
        "max_tokens": 256,
        "temperature": 0.0,
        "top_k": 1,
        "stream": True,
        "stream_options": {"include_usage": True},
    }
    try:
        tool_calls, content, usage = _accumulate_tool_calls(port, payload)
        elapsed = time.time() - t0
    except Exception as e:
        return {"trial": trial_num, "error": str(e), "elapsed_s": round(time.time() - t0, 1),
                "tool_calls": [], "passed": False, "field_in_enum": False, "args_parsed": None}

    has_tc = bool(tool_calls)
    parsed_args = None
    field_val = None
    if has_tc and tool_calls[0]["arguments"]:
        try:
            parsed_args = json.loads(tool_calls[0]["arguments"])
            field_val = parsed_args.get("field") if isinstance(parsed_args, dict) else None
        except json.JSONDecodeError:
            pass

    field_in_enum = field_val in ("mode", "format", "scale")

    print(f"  tool_calls: {len(tool_calls)}, name={tool_calls[0]['name'] if tool_calls else None}")
    print(f"  args_parsed: {parsed_args}")
    print(f"  field_in_enum: {field_in_enum}")
    if content:
        print(f"  text_content (truncated): {content[:120]!r}")
    print(f"  elapsed: {elapsed:.1f}s")

    return {
        "trial": trial_num, "error": None, "elapsed_s": round(elapsed, 1),
        "tool_calls": tool_calls, "args_parsed": parsed_args, "field_value": field_val,
        "field_in_enum": field_in_enum,
        "passed": has_tc and parsed_args is not None,
    }


def main() -> None:
    print("=" * 60)
    print(f"SPIKE Phase 2.A: qwen3.5:9b tool calling probe ({NUM_TRIALS} trials)")
    print("=" * 60)

    if not LLAMA_BIN.exists():
        print(f"FATAL: llama-server binary not found: {LLAMA_BIN}")
        sys.exit(1)
    if not MODEL_PATH.exists():
        print(f"FATAL: model not found: {MODEL_PATH}")
        print(f"  Adjust MODEL_PATH at top of script to actual filename.")
        sys.exit(1)

    print(f"\n  Binary : {LLAMA_BIN}")
    print(f"  Model  : {MODEL_PATH}")
    print(f"  Size   : {MODEL_PATH.stat().st_size / (1024*1024):.0f} MB")

    print("\n--- Phase 1: 5 trials WITH --jinja ---")
    port = _find_free_port()
    proc = _start_server(port, jinja=True)
    jinja_trials: list[dict] = []
    try:
        for i in range(1, NUM_TRIALS + 1):
            jinja_trials.append(_run_trial(port, i))
    finally:
        _stop_server(proc)

    print("\n--- Phase 2: 1 trial WITHOUT --jinja ---")
    port = _find_free_port()
    proc = _start_server(port, jinja=False)
    nojinja_trial = None
    try:
        nojinja_trial = _run_trial(port, 99)
    finally:
        _stop_server(proc)

    print("\n" + "=" * 60)
    print("SPIKE Phase 2.A SUMMARY")
    print("=" * 60)
    passes = sum(1 for t in jinja_trials if t["passed"])
    print(f"AC-SPIKE-1: {passes}/{NUM_TRIALS} valid tool_calls (need >=4)")
    out_of_enum = sum(1 for t in jinja_trials if t["tool_calls"] and not t["field_in_enum"])
    print(f"AC-SPIKE-2: {out_of_enum}/{NUM_TRIALS} trials emitted out-of-enum field")
    print(f"           -> {'STRONG' if out_of_enum == 0 else 'WEAK'} enum honor")
    nj_pass = nojinja_trial and nojinja_trial["passed"]
    print(f"AC-SPIKE-3: no-jinja trial -> {'PASS (jinja optional)' if nj_pass else 'FAIL (jinja required)'}")

    if passes >= 4 and out_of_enum == 0:
        verdict = "PASS-FULL"
    elif passes >= 4:
        verdict = "PASS-DISPATCHER-GUARD"
    else:
        verdict = "FAIL"
    print(f"\nVerdict: {verdict}")
    print("=" * 60)


if __name__ == "__main__":
    main()
