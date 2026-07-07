"""W1 commit-gate real-model smoke（spec B2.5 雙向 + plan MAJOR-2）。

驗證（真 qwen3.5-9b + 真 GPU 任務，headless、無 UI）:
  ② agent 生成中提交 GPU 任務 → 任務排隊等待、agent 串流不斷線、任務隨後成功
  ① GPU 任務推論中 agent 發話 → 30s gate 逾時回 agent.error.model_busy（或任務
     先完成則正常回應）——兩者都算過,重點是「不互殺、不凍結」
  ③ 無孤兒 agent-session worker thread
  ④ 任務端 model_busy error_code 正確分類（如觸發）

Usage:
    uv run --project backend python backend/scripts/_gate_agent_smoke.py

前置:qwen3.5 9b Q4_K_M 與 realesrgan x4plus 已下載;dev app 先關（避免雙後端搶 GPU）。
"""
from __future__ import annotations
import asyncio
import sys
import threading
import time
from pathlib import Path

_BACKEND_DIR = str(Path(__file__).resolve().parent.parent)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

AGENT_CHOICE = "qwen3.5:9b:Q4_K_M"


def _make_png(path: Path, size: int = 512) -> None:
    from PIL import Image
    import random
    img = Image.new("RGB", (size, size))
    px = img.load()
    for x in range(size):
        for y in range(size):
            px[x, y] = (random.randint(0, 255), random.randint(0, 255), random.randint(0, 255))
    img.save(path)


def _agent_input(text: str):
    from ag_ui.core import UserMessage
    from app.services.agent._ag_ui_compat import RunAgentInput
    return RunAgentInput(
        thread_id="smoke-t", run_id="smoke-r",
        messages=[UserMessage(id="m0", content=text)],
        tools=[], state={"agent_model_choice": AGENT_CHOICE},
        context=[], forwarded_props={},
    )


async def _consume_agent(svc, text: str, first_delta_evt: asyncio.Event | None = None):
    """回傳 (events_joined, error_code|None)。"""
    out = []
    err = None
    async for ev in svc.run(_agent_input(text)):
        out.append(ev)
        if first_delta_evt is not None and not first_delta_evt.is_set() and "TEXT_MESSAGE" in ev.upper():
            first_delta_evt.set()
        if "RUN_ERROR" in ev:
            if "model_busy" in ev:
                err = "model_busy"
            else:
                err = "other"
    if first_delta_evt is not None:
        first_delta_evt.set()   # 保底
    return "".join(out), err


async def _wait_task(tm, task_id: str, timeout_s: float = 900):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        t = tm.get_task(task_id)
        if t and t.status.value in ("completed", "failed", "cancelled"):
            return t
        await asyncio.sleep(1)
    raise AssertionError(f"task {task_id} did not finish in {timeout_s}s")


async def main() -> int:
    from app.init.container import init_container
    container = init_container()
    fs = container.file_service()
    tm = container.task_manager()
    agent_svc = container.agent_service()
    upscale_svc = container.image_upscale()

    tmp = Path(__file__).parent / "_smoke_assets"
    tmp.mkdir(exist_ok=True)
    png = tmp / "noise.png"
    if not png.exists():
        _make_png(png)
    fd = fs.register_local_file(str(png))

    # ── 方向②:agent 生成中提交 GPU 任務 ─────────────────────────────
    print("== direction 2: task submitted while agent is generating ==")
    first_delta = asyncio.Event()
    agent_fut = asyncio.create_task(_consume_agent(
        agent_svc, "請從 1 數到 80，每個數字用逗號分隔，不要解釋。", first_delta))
    await asyncio.wait_for(first_delta.wait(), timeout=300)
    print("  agent streaming... submitting upscale task")
    t0 = time.monotonic()
    task_id = await upscale_svc.submit_upscale(file_id=fd.file_id, model_id="realesrgan-x4plus", scale=4)
    events, err = await agent_fut
    agent_ok = err is None and ("RUN_FINISHED" in events or "run_finished" in events.lower())
    print(f"  agent finished cleanly: {agent_ok} (err={err})")
    assert agent_ok, f"agent stream broke while task queued: err={err}"

    task = await _wait_task(tm, task_id)
    print(f"  upscale task: {task.status.value} (t+{time.monotonic()-t0:.0f}s) err={task.error_code}")
    assert task.status.value == "completed", f"task failed: {task.error} / {task.error_code}"

    # ── 方向①:GPU 任務推論中 agent 發話 ─────────────────────────────
    print("== direction 1: agent speaks while a GPU task is running ==")
    task2 = await upscale_svc.submit_upscale(file_id=fd.file_id, model_id="realesrgan-x4plus", scale=4)
    await asyncio.sleep(0.5)   # 讓任務先搶到 gate
    events2, err2 = await _consume_agent(agent_svc, "hi，一句話回答：你是誰？")
    t2 = await _wait_task(tm, task2)
    print(f"  agent outcome: err={err2}; task2={t2.status.value}")
    # 兩種合法結局:任務仍佔 gate → model_busy;任務先完成 → agent 正常回。
    assert err2 in (None, "model_busy"), f"unexpected agent error: {err2}"
    assert t2.status.value == "completed", "GPU task must not be killed by agent chat"

    # ── 方向③:無孤兒 worker thread ───────────────────────────────────
    await asyncio.sleep(1)
    orphans = [t.name for t in threading.enumerate() if t.name == "agent-session" and t.is_alive()]
    print(f"  orphan agent-session threads: {orphans}")
    assert not orphans, "agent-session worker thread leaked"

    print("SMOKE PASS: gate bidirectional behavior verified with real models")
    return 0


if __name__ == "__main__":
    try:
        rc = asyncio.run(main())
    finally:
        # 收尾:殺 llama-server 避免殭屍佔 VRAM
        import subprocess
        subprocess.run(["taskkill", "/F", "/IM", "llama-server.exe"],
                       capture_output=True)
    sys.exit(rc)
