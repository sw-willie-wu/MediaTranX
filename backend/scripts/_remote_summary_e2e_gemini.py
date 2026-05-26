"""Ad-hoc real-AI smoke: full VideoSummaryService remote path against
Gemini + a real (short) test video.

Usage:
    uv run --project core/backend python core/backend/scripts/_remote_summary_e2e_gemini.py path/to/clip.mp4

Environment:
    MTX_GEMINI_LLM_MODEL  (default: gemini-2.5-flash)
    MTX_GEMINI_VLM_MODEL  (default: gemini-2.5-flash)
    MTX_REMOTE_CONN_ID    (default: 1) — Gemini connection ID from RemoteService DB

Prereqs:
- Active Gemini connection registered in the app DB at MTX_REMOTE_CONN_ID.
- A short video clip (~10-30s).

Spec §6.3 / §6.4 AC#9.
"""
from __future__ import annotations
import asyncio
import os
import sys
from pathlib import Path

# Bootstrap: make `app` importable when this file is run directly as a script
# (sys.path[0] is scripts/ by default; app lives one level up).
_BACKEND_DIR = str(Path(__file__).resolve().parent.parent)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)


async def _run_remote_summary(clip_path: Path, mode: str,
                              llm_model: str, vlm_model: str,
                              conn_id: int) -> str:
    from app.init.container import init_container

    container = init_container()
    file_service = container.file_service()
    video_summary = container.video_summary()

    file_info = file_service.register_local_file(str(clip_path))
    file_id = file_info.file_id

    task_id = await video_summary.submit_summary(
        file_id=file_id,
        llm_remote=True, llm_provider="gemini", llm_conn_id=conn_id,
        llm_remote_model=llm_model,
        vlm_remote=True, vlm_provider="gemini", vlm_conn_id=conn_id,
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

    llm_model = os.environ.get("MTX_GEMINI_LLM_MODEL", "gemini-2.5-flash")
    vlm_model = os.environ.get("MTX_GEMINI_VLM_MODEL", "gemini-2.5-flash")
    conn_id = int(os.environ.get("MTX_REMOTE_CONN_ID", "1"))
    print(f"[setup] provider=gemini llm={llm_model} vlm={vlm_model} conn_id={conn_id}")

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
