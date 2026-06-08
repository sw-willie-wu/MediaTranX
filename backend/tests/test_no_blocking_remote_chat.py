"""Guard: no app code may call a RemoteProvider's BLOCKING .chat (provider-shape
call passing `model=` but no `abort_hook`). Remote chat must select the streaming
path — either via RemoteChatSession (5 service callers) or by passing an explicit
`abort_hook` directly (the pipeline SRT path; same pattern as probe.py).
Allowed: RemoteChatSession itself + the provider adapters + probe.py."""
import pathlib
import re

APP = pathlib.Path(__file__).resolve().parents[1] / "app"
ALLOW = {
    "services/llm/remote_chat.py",
    "adapters/ai/remote/ollama.py",
    "adapters/ai/remote/openai.py",
    "adapters/ai/remote/gemini.py",
    "adapters/ai/remote/base.py",
    "adapters/ai/remote/probe.py",
}
CALL = re.compile(r"\.chat(?:_with_images)?\(")

def test_no_provider_blocking_chat_calls():
    offenders = []
    for py in APP.rglob("*.py"):
        rel = py.relative_to(APP).as_posix()
        if rel in ALLOW:
            continue
        src = py.read_text(encoding="utf-8")
        for m in CALL.finditer(src):
            span = src[m.start():m.start() + 400]   # the call's argument span
            if "abort_hook" in span:                # streaming (session OR direct hook)
                continue
            # session.chat / runtime.chat have no `model=`; only provider-shape
            # blocking calls pass `model=` without an abort_hook.
            if "model=" in span:
                line = src[:m.start()].count("\n") + 1
                offenders.append(f"{rel}:{line}")
    assert not offenders, f"Blocking provider .chat calls (must pass abort_hook): {offenders}"
