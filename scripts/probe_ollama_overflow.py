"""Wave-0 probe: does dev-ollama bridge HARD-ERROR or SILENTLY TRUNCATE
when input exceeds a vllm model's context, and does the response carry
prompt_eval_count?  Run once; record findings in the implementation plan.

Background: after we stop sending num_ctx, an oversized chunk must be
surfaced to the user. Whether we map a hard error (context_exceeded) or
detect silent truncation via prompt_eval_count depends on what the bridge
actually does — this probe decides it empirically.
"""
import json
import urllib.error
import urllib.request

ENDPOINT = "https://dev-ollama.thinktron.co"
# vllm-bridge model whose /api/show model_info is EMPTY (no detectable max).
VLLM_MODEL = "gpt-oss-120b-vllm-openai"
# native ollama model for the silent-truncation comparison.
NATIVE_MODEL = "gemma3:latest"
BIG = "word " * 200_000  # ~200k tokens, far beyond any context window


def probe(model: str) -> None:
    print(f"\n=== {model} ===")
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": BIG}],
        "stream": False,
        "options": {"num_predict": 1},
    }
    req = urllib.request.Request(
        f"{ENDPOINT}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            body = json.loads(r.read())
        print("STATUS: 200 OK")
        print("  done_reason:", body.get("done_reason"))
        print("  error:", body.get("error"), "| detail:", body.get("detail"))
        print("  prompt_eval_count:", body.get("prompt_eval_count"))
    except urllib.error.HTTPError as e:
        print("HTTP ERROR", e.code)
        print("  body:", e.read().decode("utf-8", "replace")[:600])
    except Exception as e:  # noqa: BLE001
        print("EXC:", type(e).__name__, e)


if __name__ == "__main__":
    probe(VLLM_MODEL)
    probe(NATIVE_MODEL)
