"""Ad-hoc real-AI smoke: full VideoSummaryService remote path against a
running Ollama instance + a real (short) test video.

Usage:
    uv run --project core/backend python core/backend/scripts/_remote_summary_e2e.py path/to/clip.mp4

Environment:
    MTX_REMOTE_LLM_MODEL (default: gpt-oss:120b)
    MTX_REMOTE_VLM_MODEL (default: qwen3.5:122b)
    MTX_REMOTE_CONN_ID   (default: 1) — Ollama connection ID from RemoteService DB

Prereqs:
- Ollama running with both LLM and VLM models pulled.
- A short video clip (~10-30s; longer is fine but takes minutes).
- Active Ollama connection registered in the app DB at MTX_REMOTE_CONN_ID
  (auto-created when the app inits with a fresh DB and the user adds a
  connection via UI; for this smoke we expect at least one is_active=True
  ollama connection to exist at the given conn_id).

Runs both bullets-mode and narrative-mode summaries. Prints task IDs
and asserts both submit without exception.

Spec: Testing §Real-AI smoke.
"""
from __future__ import annotations
import asyncio
import os
import sys
from pathlib import Path


async def _run_remote_summary(clip_path: Path, mode: str,
                                llm_model: str, vlm_model: str,
                                conn_id: int) -> str:
    """Returns the task id."""
    # Heavy: this brings up the container, registers wrappers, opens the DB.
    # Acceptable for an ad-hoc smoke; the harness is not in the unit suite.
    from app.init.container import init_container

    container = init_container()
    file_service = container.file_service()
    video_summary = container.video_summary()

    # Register the file (file_service.register_local_file is the real API).
    file_info = file_service.register_local_file(str(clip_path))
    file_id = file_info.file_id

    task_id = await video_summary.submit_summary(
        file_id=file_id,
        llm_remote=True, llm_provider="ollama", llm_conn_id=conn_id,
        llm_remote_model=llm_model,
        vlm_remote=True, vlm_provider="ollama", vlm_conn_id=conn_id,
        vlm_remote_model=vlm_model,
        summary_mode=mode,
        whisper_model_size="medium",
    )
    print(f"[{mode}] submitted task_id={task_id}")
    return task_id


def main() -> int:
    if len(sys.argv) < 2:
        print(f"Usage: {sys.argv[0]} path/to/clip.mp4", file=sys.stderr)
        return 2
    clip = Path(sys.argv[1])
    if not clip.exists():
        print(f"file not found: {clip}", file=sys.stderr)
        return 2

    llm_model = os.environ.get("MTX_REMOTE_LLM_MODEL", "gpt-oss:120b")
    vlm_model = os.environ.get("MTX_REMOTE_VLM_MODEL", "qwen3.5:122b")
    conn_id = int(os.environ.get("MTX_REMOTE_CONN_ID", "1"))
    print(f"[setup] llm={llm_model} vlm={vlm_model} conn_id={conn_id}")

    for mode in ("bullets", "narrative"):
        try:
            asyncio.run(_run_remote_summary(clip, mode, llm_model, vlm_model, conn_id))
        except Exception as e:
            print(f"FAIL {mode}: {e!r}", file=sys.stderr)
            return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
