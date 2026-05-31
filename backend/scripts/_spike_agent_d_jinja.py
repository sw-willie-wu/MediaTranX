"""SPIKE-D: llama-server --jinja flag + tool calling + include_usage verification.

Strategy: Direct subprocess spawn of llama-server binary.
- Binary: core/backend/bin/llama/llama-server.exe
- Model: core/backend/models/qwen3/Qwen3-8B-Q4_K_M.gguf

Three test cases:
  (a) WITHOUT --jinja + tools= payload -> expect plain text, no tool_calls
  (b) WITH --jinja + tools= payload -> expect tool_calls[]
  (c) WITH --jinja + stream=True + stream_options.include_usage=True
      -> last SSE chunk before [DONE] should contain usage

Usage:
    uv run --project core/backend python scripts/_spike_agent_d_jinja.py
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
# Path discovery (relative to core/backend/ cwd)
# ---------------------------------------------------------------------------

BACKEND_DIR = Path(__file__).parent.parent  # core/backend/
LLAMA_BIN = BACKEND_DIR / "bin" / "llama" / "llama-server.exe"
MODEL_PATH = BACKEND_DIR / "models" / "qwen3" / "Qwen3-8B-Q4_K_M.gguf"

STARTUP_TIMEOUT = 180  # seconds

# ---------------------------------------------------------------------------
# Test payload (same as SPIKE-B)
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


def _find_free_port(start: int = 19180, end: int = 19280) -> int:
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


def _start_server(port: int, extra_flags: list[str]) -> subprocess.Popen:
    """Spawn llama-server and wait until /health returns ok."""
    cmd = [
        str(LLAMA_BIN),
        "--model", str(MODEL_PATH),
        "--port", str(port),
        "--host", "127.0.0.1",
        "--ctx-size", "4096",
        "--n-gpu-layers", "99",
        "--reasoning", "off",
    ] + extra_flags

    print(f"\n  CMD: {' '.join(cmd)}")
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


def _post_chat(port: int, payload: dict) -> dict:
    """Send POST /v1/chat/completions, return parsed JSON response."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read())


def _post_chat_stream(port: int, payload: dict) -> list[dict]:
    """Send streaming POST, return parsed list of SSE data chunks."""
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}/v1/chat/completions",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    chunks = []
    with urllib.request.urlopen(req, timeout=300) as resp:
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if line.startswith("data:"):
                payload_str = line[len("data:"):].strip()
                if payload_str == "[DONE]":
                    chunks.append({"_sentinel": "[DONE]"})
                    break
                try:
                    chunks.append(json.loads(payload_str))
                except json.JSONDecodeError:
                    chunks.append({"_raw": payload_str})
    return chunks


def _stop_server(proc: subprocess.Popen) -> None:
    try:
        proc.terminate()
        proc.wait(timeout=10)
    except Exception:
        try:
            proc.kill()
            proc.wait(timeout=5)
        except Exception:
            pass
    print(f"  Server stopped (rc={proc.poll()})")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 60)
    print("SPIKE-D: llama-server --jinja tool calling verification")
    print("=" * 60)

    if not LLAMA_BIN.exists():
        print(f"FATAL: llama-server binary not found: {LLAMA_BIN}")
        sys.exit(1)
    if not MODEL_PATH.exists():
        print(f"FATAL: model not found: {MODEL_PATH}")
        sys.exit(1)

    print(f"\n  Binary : {LLAMA_BIN}")
    print(f"  Model  : {MODEL_PATH}")

    results = {}

    # -----------------------------------------------------------------------
    # Case (a): WITHOUT --jinja, non-streaming, tools= payload
    # -----------------------------------------------------------------------
    print("\n" + "-" * 50)
    print("Case (a): WITHOUT --jinja — expect plain text, no tool_calls")
    port_a = _find_free_port()
    proc_a = None
    try:
        proc_a = _start_server(port_a, extra_flags=[])
        payload_a = {
            "model": "local",
            "messages": MESSAGES,
            "tools": TOOLS,
            "max_tokens": 512,
            "temperature": 0.1,
        }
        resp_a = _post_chat(port_a, payload_a)
        msg_a = resp_a["choices"][0]["message"]
        has_tool_calls_a = bool(msg_a.get("tool_calls"))
        content_a = msg_a.get("content", "")
        snippet_a = (content_a or "")[:200]

        if has_tool_calls_a:
            results["a"] = ("FAIL", f"Unexpectedly got tool_calls: {msg_a['tool_calls']}")
        else:
            results["a"] = ("PASS", f"No tool_calls (plain text). Content[:200]: {snippet_a!r}")
        print(f"  tool_calls present: {has_tool_calls_a}")
        print(f"  content[:200]: {snippet_a!r}")
    except Exception as e:
        results["a"] = ("ERROR", str(e))
        print(f"  ERROR: {e}")
    finally:
        if proc_a:
            _stop_server(proc_a)

    # -----------------------------------------------------------------------
    # Case (b): WITH --jinja, non-streaming, tools= payload
    # -----------------------------------------------------------------------
    print("\n" + "-" * 50)
    print("Case (b): WITH --jinja — expect tool_calls[]")
    port_b = _find_free_port()
    proc_b = None
    try:
        proc_b = _start_server(port_b, extra_flags=["--jinja"])
        payload_b = {
            "model": "local",
            "messages": MESSAGES,
            "tools": TOOLS,
            "max_tokens": 512,
            "temperature": 0.1,
        }
        resp_b = _post_chat(port_b, payload_b)
        msg_b = resp_b["choices"][0]["message"]
        has_tool_calls_b = bool(msg_b.get("tool_calls"))
        tool_calls_b = msg_b.get("tool_calls", [])
        content_b = msg_b.get("content", "")
        snippet_b = (content_b or "")[:200]

        if has_tool_calls_b:
            results["b"] = ("PASS", f"Got tool_calls: {json.dumps(tool_calls_b)[:200]}")
        else:
            results["b"] = ("FAIL", f"No tool_calls even with --jinja. Content[:200]: {snippet_b!r}")
        print(f"  tool_calls present: {has_tool_calls_b}")
        print(f"  tool_calls: {json.dumps(tool_calls_b)[:300]}")
        print(f"  content[:200]: {snippet_b!r}")
    except Exception as e:
        results["b"] = ("ERROR", str(e))
        print(f"  ERROR: {e}")
    finally:
        if proc_b:
            _stop_server(proc_b)

    # -----------------------------------------------------------------------
    # Case (c): WITH --jinja + stream=True + stream_options.include_usage=True
    # -----------------------------------------------------------------------
    print("\n" + "-" * 50)
    print("Case (c): WITH --jinja + stream + include_usage — last chunk has usage")
    port_c = _find_free_port()
    proc_c = None
    try:
        proc_c = _start_server(port_c, extra_flags=["--jinja"])
        payload_c = {
            "model": "local",
            "messages": MESSAGES,
            "tools": TOOLS,
            "max_tokens": 512,
            "temperature": 0.1,
            "stream": True,
            "stream_options": {"include_usage": True},
        }
        chunks_c = _post_chat_stream(port_c, payload_c)
        last_data = None
        for chunk in reversed(chunks_c):
            if "_sentinel" not in chunk:
                last_data = chunk
                break

        usage_found = False
        usage_val = None
        if last_data and "usage" in last_data:
            usage_found = True
            usage_val = last_data["usage"]
        elif last_data:
            # Some implementations put usage in choices[0].delta or top-level
            usage_val = last_data.get("usage")
            usage_found = usage_val is not None

        print(f"  Total SSE chunks: {len(chunks_c)}")
        print(f"  Last data chunk (before [DONE]): {json.dumps(last_data)[:400] if last_data else 'None'}")
        if usage_found:
            results["c"] = ("PASS", f"usage found: {usage_val}")
        else:
            results["c"] = ("FAIL", f"No usage in last chunk. Last chunk: {json.dumps(last_data)[:200] if last_data else 'None'}")
        print(f"  usage: {usage_val}")
    except Exception as e:
        results["c"] = ("ERROR", str(e))
        print(f"  ERROR: {e}")
    finally:
        if proc_c:
            _stop_server(proc_c)

    # -----------------------------------------------------------------------
    # Summary
    # -----------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("SPIKE-D Summary")
    print("=" * 60)
    all_pass = True
    for case, (status, detail) in results.items():
        marker = "[PASS]" if status == "PASS" else "[FAIL]"
        print(f"  ({case}) {marker}: {detail[:120]}")
        if status != "PASS":
            all_pass = False

    # Consistency check: (a) and (b) should differ
    if results.get("a", ("",))[0] == "PASS" and results.get("b", ("",))[0] == "PASS":
        # Both pass means (a) had no tool_calls and (b) had tool_calls -- correct divergence
        print("\n  Divergence confirmed: (a) no tool_calls, (b) tool_calls. --jinja IS required.")
    elif results.get("a", ("",))[0] == "FAIL" and results.get("b", ("",))[0] == "FAIL":
        print("\n  WARNING: Both (a) and (b) behaved the same -- possible version issue.")
    elif results.get("a", ("",))[0] == "FAIL":
        print("\n  WARNING: (a) unexpectedly had tool_calls without --jinja.")
        print("  INTERPRETATION: This llama-server version may support tool calling without --jinja.")
        print("  If (b) also has tool_calls, the flag is NOT required for basic tool calling.")

    print(f"\n  Overall: {'SPIKE-D PASS' if all_pass else 'SPIKE-D FAIL'}")


if __name__ == "__main__":
    main()
