"""Video summary service — transcript -> LLM -> key frames -> markdown -> zip."""
from __future__ import annotations
import logging
import shutil
import threading
import zipfile
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from app.handler.exceptions import TaskCancelledError
from app.services.files.file_service import FileService
from app.adapters.ai.wrapper.whisper import WhisperWrapper
from app.adapters.ai.wrapper.demucs import DemucsWrapper
from app.adapters.ai.wrapper.wav2vec2 import AlignmentEngine
from app.adapters.ai.inference_config import get_inference_config
from app.utils.inference import calc_max_tokens, estimate_tokens
from app.pipeline.transcribe import TranscribeOptions, transcribe_audio_sync
from app.utils.prompts import (
    SUMMARY_MODE_BULLETS,
    SUMMARY_MODE_NARRATIVE,
    build_summary_prompt,
)
from .scene_detect import SceneDetector
from .frame_picker import pick_frame_timestamp
from .parse import (
    SubtitleEntry,
    SummaryChunkResult,
    chunk_entries_by_tokens,
    compute_bullet_target,
    even_indices,
    format_transcript_numbered,
    merge_chunk_outputs,
    parse_bullets_markdown,
    parse_narrative_paragraphs,
    resolve_line_windows,
)
from .markdown import build_markdown
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_VIDEO_SUMMARY = "video.summary"

# Safety cap on how many narrative paragraphs get an inline frame. Narrative
# mode frames every paragraph (no duration-scaled subsampling like bullets);
# this only guards against a pathological LLM emitting hundreds of paragraphs.
MAX_NARRATIVE_FRAMES = 50


def _map_language_to_whisper(ui_language: str) -> Optional[str]:
    """Map UI language ('zh-TW', 'en', ...) to Whisper language code ('zh', 'en', ...)."""
    if ui_language.startswith("zh"):
        return "zh"
    if ui_language.startswith("en"):
        return "en"
    # Other locales: let Whisper auto-detect
    return None


def _resolve_output_language(ui_language: str, whisper_language: Optional[str]) -> Optional[str]:
    """Pick BCP-47-ish language code for LLM output.

    Whisper returns "zh" without TW/CN distinction; the whisper wrapper post-converts
    output to Traditional (default) or Simplified based on UI hint. Mirror that here so
    the LLM matches the transcript script.
    """
    if not whisper_language:
        return None
    if whisper_language == "zh":
        return "zh-CN" if ui_language == "zh-CN" else "zh-TW"
    return whisper_language


class VideoSummaryService:
    """Generate a markdown summary of a video with key frames, packaged as ZIP."""

    def __init__(
        self,
        ffmpeg,
        file_service: FileService,
        task_manager: TaskManager,
        chat_service,
        model_manager,
        remote_service,
        whisper: WhisperWrapper,
        demucs: DemucsWrapper = None,
        alignment_engine: AlignmentEngine = None,
    ):
        self._ffmpeg = ffmpeg
        self._file_service = file_service
        self._task_manager = task_manager
        self._chat_service = chat_service
        self._model_manager = model_manager
        self._remote_service = remote_service
        self._whisper = whisper
        self._demucs = demucs
        self._alignment_engine = alignment_engine

        self._task_manager.register_handler(
            TASK_TYPE_VIDEO_SUMMARY,
            self._handle_task,
            output_policy="results",
        )

        logger.info("VideoSummaryService initialized")

    async def submit_summary(
        self,
        file_id: str,
        # LLM — either local (family+size) OR remote (remote+provider+conn_id+remote_model)
        llm_model_family: Optional[str] = None,        # MODIFIED: was required
        llm_model_size: Optional[str] = None,          # MODIFIED: was required
        llm_remote: bool = False,                      # NEW
        llm_provider: Optional[str] = None,            # NEW
        llm_conn_id: Optional[int] = None,             # NEW
        llm_remote_model: Optional[str] = None,        # NEW
        language: str = "zh-TW",
        # VLM — wholly optional; if present, either local OR remote
        vlm_model_family: Optional[str] = None,
        vlm_model_size: Optional[str] = None,
        vlm_remote: bool = False,                      # NEW
        vlm_provider: Optional[str] = None,            # NEW
        vlm_conn_id: Optional[int] = None,             # NEW
        vlm_remote_model: Optional[str] = None,        # NEW
        whisper_model_size: str = "medium",
        vocal_separation: bool = False,
        align: bool = False,
        word_timestamps: bool = False,
        condition_on_previous_text: bool = True,
        min_silence_duration_ms: int = 200,
        vad_threshold: float = 0.3,
        summary_mode: str = "bullets",
    ) -> str:
        """Submit a summary task.

        LLM is required: caller must supply EITHER local (model_family +
        model_size) OR remote (llm_remote=True + provider + conn_id +
        remote_model). Mixed combinations raise ValueError.

        VLM is fully optional: same local-OR-remote rule when present,
        but both absent is valid (→ midpoint-nearest fallback in
        frame_picker).
        """
        # ---- LLM validation ----
        llm_has_local = bool(llm_model_family and llm_model_size)
        llm_has_remote = bool(
            llm_remote and llm_provider and llm_conn_id is not None and llm_remote_model
        )
        if llm_remote and not llm_has_remote:
            missing = [
                k for k, v in (
                    ("llm_provider", llm_provider),
                    ("llm_conn_id", llm_conn_id),
                    ("llm_remote_model", llm_remote_model),
                ) if (v is None if k.endswith("_conn_id") else not v)
            ]
            raise ValueError(
                f"llm_remote=True but missing: {', '.join(missing)}"
            )
        if not llm_has_local and not llm_has_remote:
            raise ValueError(
                "LLM is required: pass either llm_model_family+llm_model_size "
                "(local) or llm_remote=True with llm_provider+llm_conn_id+"
                "llm_remote_model (remote)"
            )
        if llm_has_local and llm_has_remote:
            raise ValueError(
                "LLM must specify exactly one of local (llm_model_family+"
                "llm_model_size) or remote (llm_remote+llm_provider+...)"
            )

        # ---- VLM validation (optional) ----
        vlm_has_local = bool(vlm_model_family and vlm_model_size)
        vlm_has_remote = bool(
            vlm_remote and vlm_provider and vlm_conn_id is not None and vlm_remote_model
        )
        if vlm_remote and not vlm_has_remote:
            missing = [
                k for k, v in (
                    ("vlm_provider", vlm_provider),
                    ("vlm_conn_id", vlm_conn_id),
                    ("vlm_remote_model", vlm_remote_model),
                ) if (v is None if k.endswith("_conn_id") else not v)
            ]
            raise ValueError(
                f"vlm_remote=True but missing: {', '.join(missing)}"
            )
        if vlm_has_local and vlm_has_remote:
            raise ValueError(
                "VLM must specify exactly one of local or remote (or omit "
                "both for midpoint-nearest fallback)"
            )

        file_info = self._file_service.require_file(file_id)

        params = {
            "file_id": file_id,
            "llm_model_family": llm_model_family,
            "llm_model_size": llm_model_size,
            "llm_remote": llm_remote,
            "llm_provider": llm_provider,
            "llm_conn_id": llm_conn_id,
            "llm_remote_model": llm_remote_model,
            "language": language,
            "vlm_model_family": vlm_model_family,
            "vlm_model_size": vlm_model_size,
            "vlm_remote": vlm_remote,
            "vlm_provider": vlm_provider,
            "vlm_conn_id": vlm_conn_id,
            "vlm_remote_model": vlm_remote_model,
            "whisper_model_size": whisper_model_size,
            "vocal_separation": vocal_separation,
            "align": align,
            "word_timestamps": word_timestamps,
            "condition_on_previous_text": condition_on_previous_text,
            "min_silence_duration_ms": min_silence_duration_ms,
            "vad_threshold": vad_threshold,
            "summary_mode": summary_mode,
        }
        task_id = await self._task_manager.submit(TASK_TYPE_VIDEO_SUMMARY, params)
        logger.info(f"Summary task submitted: {task_id} for file {file_id}")
        return task_id

    def _handle_task(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None],
    ) -> dict:
        return self._execute(params, progress_callback)

    def _execute(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None],
    ) -> dict:
        """Run the summary pipeline with scene detection parallelized.

        detect_all() only needs the video file — no data dependency on Whisper
        or the LLM, and it is CPU-bound FFmpeg software decode that does not
        contend with the GPU. So it runs in a background thread spawned here at
        task start and is joined at the frame-picking merge point. The whole
        rest of the pipeline runs inside the try whose finally guarantees the
        thread is cancelled + joined on every exit path. See spec 2026-05-22 §3.
        """
        file_id = params["file_id"]
        file_info = self._file_service.require_file(file_id)
        video_path = Path(file_info.file_path)

        detector = SceneDetector(ffmpeg=self._ffmpeg)
        detect_cancel = threading.Event()
        detect_holder: dict = {}

        def _detect_on_progress(_fraction: float) -> None:
            # Background thread's detect_all on_progress: NOT a progress
            # reporter (the bar is driven solely by the main thread) — its only
            # job is to raise on cancel so detect_scenes kills its FFmpeg
            # subprocess (spec 2026-05-22 §3.4). Called every ~0.5-0.7s.
            if detect_cancel.is_set():
                raise TaskCancelledError("summary scene-detect cancelled")

        def _detect_worker() -> None:
            try:
                detect_holder["scenes"] = detector.detect_all(
                    video_path, on_progress=_detect_on_progress
                )
            except TaskCancelledError:
                pass  # main thread owns cancel semantics; nothing to store
            except Exception as e:  # defensive — detect_all already best-efforts to []
                logger.warning(f"summary: background scene-detect failed ({e})")
                detect_holder["scenes"] = []

        detect_thread = threading.Thread(
            target=_detect_worker, name="summary-detect", daemon=True
        )
        detect_thread.start()
        try:
            return self._run_summary_pipeline(
                params, progress_callback, detector, detect_thread, detect_holder
            )
        finally:
            # Reap the background detect thread on EVERY exit path (success,
            # cancel, error). On success it is already joined at the merge
            # loop, so this join is a no-op. On cancel/error: set() before
            # join() so detect's next on_progress tick (~0.5-0.7s apart) raises
            # and detect_scenes kills its FFmpeg subprocess — the normal cancel
            # path reaps in ~1s.
            #
            # The join timeout bounds the rare degenerate case: if FFmpeg's
            # -progress output STALLS past the timeout (no tick → cancel is
            # never observed), join() returns with the thread + its ffmpeg.exe
            # still running. That is a *bounded, self-resolving* orphan — a
            # scdet pass is a finite CPU-only scan that exits on its own (no
            # VRAM / handle leak, unlike a pinned model). daemon=True
            # guarantees it cannot block Python process exit. 30s is generous
            # against the ~1s normal path while not holding the task's
            # terminal state long on a stall.
            detect_cancel.set()
            detect_thread.join(timeout=30.0)

    def _run_summary_pipeline(
        self,
        params: dict,
        progress_callback: Callable[[float, str], None],
        detector,
        detect_thread: threading.Thread,
        detect_holder: dict,
    ) -> dict:
        file_id = params["file_id"]
        llm_family = params["llm_model_family"]
        llm_size = params["llm_model_size"]
        vlm_family = params.get("vlm_model_family")
        vlm_size = params.get("vlm_model_size")
        language = params.get("language", "zh-TW")
        summary_mode = params.get("summary_mode", "bullets")

        file_info = self._file_service.require_file(file_id)

        video_path = Path(file_info.file_path)

        # Step 1a: extract audio from video
        temp_audio = self._file_service.upload_dir / f"summary_audio_{uuid4().hex[:8]}.wav"
        try:
            progress_callback(0.02, "task.progress.extract_audio_starting")
            self._ffmpeg.extract_audio_sync(
                video_path, temp_audio,
                audio_format="wav", sample_rate=16000, channels=1,
            )
            progress_callback(0.05, "task.progress.audio_extracted")

            # Step 1b: transcribe (0.05 ~ 0.50)
            opts = TranscribeOptions(
                language=_map_language_to_whisper(language),
                model_size=params.get("whisper_model_size", "medium"),
                word_timestamps=params.get("word_timestamps", False),
                condition_on_previous_text=params.get("condition_on_previous_text", True),
                min_silence_duration_ms=params.get("min_silence_duration_ms", 200),
                vad_threshold=params.get("vad_threshold", 0.3),
                separate_vocals=params.get("vocal_separation", False),
                align=params.get("align", False),
            )

            def _t_progress(p: float, m: str) -> None:
                # Map [0,1] from whisper to [0.05, 0.50] of overall progress.
                progress_callback(0.05 + p * 0.45, m)

            result = transcribe_audio_sync(
                temp_audio, opts,
                self._model_manager,
                self._ffmpeg.ffmpeg_path,
                whisper=self._whisper,
                demucs=self._demucs,
                alignment_engine=self._alignment_engine,
                on_progress=_t_progress,
            )
        finally:
            temp_audio.unlink(missing_ok=True)

        # Convert TranscribeResult.segments to SubtitleEntry (downstream expects SubtitleEntry)
        entries = [
            SubtitleEntry(start=s.start, end=s.end, text=s.text) for s in result.segments
        ]
        if not entries:
            raise RuntimeError("Transcription returned no segments")

        # Duration-scaled cap on how many bullets get an inline frame. The
        # rendered summary keeps every bullet; this only bounds frame work so
        # a long video doesn't run ~N per-item scene-detects + extracts.
        content_sec = max(e.end for e in entries)
        bullet_cap = compute_bullet_target(content_sec)

        # Step 2: chunk + LLM (50% ~ 70%)
        cfg = get_inference_config(llm_family, llm_size, "summarize")
        n_ctx = cfg["n_ctx"]
        # Budget the input with two upper bounds:
        #   (a) context-fit: n_ctx - output_cap - prompt_overhead
        #   (b) model-size cap: bigger model → bigger chunk.
        #
        # Piecewise scaling by parameter count:
        #   ≤ 5B: 4000 tokens — small models struggle with structural JSON on
        #                        long inputs; keep chunks moderate.
        #   6~15B: 6000 tokens — sweet spot (tested: qwen3.5:9b handles ~6300
        #                        tokens ≈ 10min transcript cleanly in ~2 min).
        #   ≥ 16B: 16000 tokens — large models are designed for long contexts
        #                         (32k+ native); smaller chunks waste capability
        #                         AND force unnecessary merges that hurt summary
        #                         coherence. At 27B, 16k input takes ~200s —
        #                         well under the 900s HTTP timeout.
        PROMPT_OVERHEAD = 600  # template/instruction tokens
        output_cap = cfg.get("max_tokens_cap", 4096)

        # Extract param count from variant name ("e2b", "4b", "9b", "26b", "27b"...)
        import re as _re
        _m = _re.search(r"(\d+)", llm_size)
        size_b = int(_m.group(1)) if _m else 9
        if size_b <= 5:
            model_cap = 4000
        elif size_b <= 15:
            model_cap = 6000
        else:
            model_cap = 16000

        context_cap = max(1024, n_ctx - output_cap - PROMPT_OVERHEAD)
        input_budget = min(context_cap, model_cap)

        chunks = chunk_entries_by_tokens(entries, max_input_tokens=input_budget)
        logger.info(
            f"Video summary chunking: model={llm_family}:{llm_size} (~{size_b}B), "
            f"n_ctx={n_ctx}, context_cap={context_cap}, model_cap={model_cap}, "
            f"input_budget={input_budget}, num_chunks={len(chunks)}, num_entries={len(entries)}"
        )

        chunk_results: list[SummaryChunkResult] = []
        # 1-based global transcript line number for the next chunk. Bullets mode
        # numbers transcript lines so the LLM cites [L<n>] ranges; the numbering
        # must stay continuous across chunks for resolve_line_windows to map
        # cites back onto the global `entries` list.
        line_offset = 1
        for i, chunk in enumerate(chunks):
            pct = 0.50 + 0.20 * (i / max(1, len(chunks)))
            progress_callback(
                pct, f"task.progress.summary_chunk|{i + 1}|{len(chunks)}"
            )
            # Note: deliberately bypasses get_prompt_builder("summarize", ...) because this task
            # uses dedicated structured prompts (hierarchical-markdown for bullets mode,
            # flat prose paragraphs for narrative mode) — see prompts.py for the templates.
            output_lang = _resolve_output_language(language, result.language)
            # Both modes feed a line-numbered transcript; the LLM cites
            # [L<n>] ranges and the service resolves them to real timestamps.
            transcript = format_transcript_numbered(chunk, start_index=line_offset)
            line_offset += len(chunk)
            prompt = build_summary_prompt(
                transcript,
                output_language=output_lang,
                summary_mode=summary_mode,
            )
            prompt_tokens = estimate_tokens(prompt)
            max_tokens = calc_max_tokens(cfg, n_ctx, prompt_tokens)
            raw = self._chat_service.chat(
                prompt=prompt,
                model_family=llm_family,
                model_size=llm_size,
                max_tokens=max_tokens,
                temperature=cfg["temperature"],
                on_progress=progress_callback,
                cancel_pct=pct,
                cancel_msg=f"task.progress.summary_chunk|{i + 1}|{len(chunks)}",
            )
            try:
                if summary_mode == SUMMARY_MODE_NARRATIVE:
                    chunk_results.append(parse_narrative_paragraphs(raw))
                else:
                    chunk_results.append(parse_bullets_markdown(raw))
            except ValueError as e:
                logger.warning(f"Chunk {i} parse failed: {e}; skipping")

        if not chunk_results:
            raise RuntimeError("All chunks failed to produce a usable summary")

        merged = merge_chunk_outputs(chunk_results)

        # Resolve cited transcript line ranges ([L<a>-L<b>]) to real Whisper
        # time windows. `entries` is the full global list the line numbers
        # index into. Unusable cites get time_range=None (skipped below).
        # Mode-agnostic: the inactive mode's list is empty → no-op.
        resolve_line_windows(merged.bullet_items, entries)
        resolve_line_windows(merged.narrative_paragraphs, entries)

        # Probe duration/fps once to clamp LLM-drifted frame timestamps.
        # Best-effort: the per-item try/except below is the actual guarantee
        # (an out-of-range -ss seek decodes 0 frames and ffmpeg hard-fails).
        try:
            _mi = self._ffmpeg.get_media_info_sync(video_path)
            video_duration = _mi.duration if _mi.duration and _mi.duration > 0 else None
            video_fps = _mi.fps if _mi.fps and _mi.fps > 0 else None
        except Exception as e:
            logger.warning(
                f"summary: media_info probe failed ({e}); frame ts clamp disabled"
            )
            video_duration, video_fps = None, None

        # Step 3: set up output staging
        output_id = str(uuid4())
        stem = Path(file_info.original_filename).stem
        work_dir = self._file_service.output_dir / f"summary_{output_id[:8]}"
        frames_dir = work_dir / "frames"
        frames_dir.mkdir(parents=True, exist_ok=True)

        zip_path = (
            self._file_service.output_dir / f"{stem}_summary_{output_id[:8]}.zip"
        )

        try:
            # Step 3.5: join the background scene-detect thread (started at the
            # top of _execute). It usually finished during Whisper+LLM. If not,
            # poll-join in 0.5s ticks so the bar still gets a cancel heartbeat;
            # the bar holds at 0.70 showing summary_detecting_scenes until done.
            while detect_thread.is_alive():
                detect_thread.join(timeout=0.5)
                progress_callback(0.70, "task.progress.summary_detecting_scenes")
            global_scenes = detect_holder.get("scenes", [])

            # vlm_cb is (re)built per loop iteration so the cancel heartbeat
            # carries that iteration's live pct/message (shape (a)). The build
            # is cheap (a get_inference_config registry lookup, no model load).
            vlm_cb = None

            # Step 4: bullet frames (70% ~ 95%)
            # Iterate over merged.bullet_items (each carries time_range + line_index for image insertion).
            # Per-item resilience: a single frame-extraction failure (e.g. an
            # LLM-drifted timestamp ffmpeg can't decode) must NOT abort the
            # whole job — the summary text is already generated. Skip the inline
            # image for that item and continue. progress_callback stays OUTSIDE
            # the try so cooperative TaskCancelledError still propagates.
            # Deterministic frame cap: only ``bullet_cap`` evenly-spaced bullets
            # get an inline frame. Keys/filenames use the ORIGINAL index into
            # merged.bullet_items because build_markdown iterates the full list
            # and does bullet_frames.get(idx) — keying by subset position would
            # paste images onto the wrong bullets.
            bullet_frames: dict[int, str] = {}
            bullet_fail = 0
            md_lines = merged.bullets_markdown.splitlines()
            bullet_sel = even_indices(len(merged.bullet_items), bullet_cap)
            for n_done, orig_i in enumerate(bullet_sel):
                item = merged.bullet_items[orig_i]
                pct = 0.70 + 0.25 * (n_done / max(1, len(bullet_sel)))
                progress_callback(
                    pct,
                    f"task.progress.summary_bullet_frame|{n_done + 1}|{len(bullet_sel)}",
                )
                # Bullet whose line citation didn't resolve to a usable window
                # (resolve_line_windows set time_range=None): deliberately skip
                # — no inline image. This is NOT a failure, so it stays out of
                # bullet_fail. progress_callback above already fired (keeps the
                # cancel heartbeat / monotonic progress).
                if item["time_range"] is None:
                    continue
                vlm_cb = (self._make_vlm_callback(
                    vlm_family, vlm_size, on_progress=progress_callback,
                    cancel_pct=pct,
                    cancel_msg=f"task.progress.summary_bullet_frame|{n_done + 1}|{len(bullet_sel)}",
                ) if vlm_family and vlm_size else None)
                cand_max_edge = (
                    get_inference_config(
                        vlm_family, vlm_size, "frame_select"
                    )["max_image_edge"]
                    if vlm_family and vlm_size else None
                )
                try:
                    t_start, t_end = item["time_range"]
                    # Use the bullet's own markdown line as VLM context (label + description).
                    line_i = item["line_index"]
                    context_text = md_lines[line_i] if 0 <= line_i < len(md_lines) else ""
                    ts = pick_frame_timestamp(
                        detector=detector,
                        vlm_callback=vlm_cb,
                        video_path=video_path,
                        window_start=t_start,
                        window_end=t_end,
                        context_text=context_text,
                        temp_dir=work_dir / f"candidates_b{orig_i}",
                        duration=video_duration,
                        fps=video_fps,
                        scenes=global_scenes,
                        candidate_max_edge=cand_max_edge,
                    )
                    if ts is None:
                        continue  # VLM judged no candidate matches — no image
                    out = frames_dir / f"bullet_{orig_i:03d}.jpg"
                    detector.extract_frame(
                        input_path=video_path, output_path=out, timestamp=ts
                    )
                    bullet_frames[orig_i] = f"frames/bullet_{orig_i:03d}.jpg"
                except TaskCancelledError:
                    raise
                except Exception as e:
                    bullet_fail += 1
                    logger.warning(
                        f"summary: bullet {orig_i} frame failed ({e}); skipping image"
                    )
                    continue

            # Step 5: narrative paragraph frames (70% ~ 95%)
            # Narrative mode frames EVERY paragraph (no bullet_cap subsampling);
            # MAX_NARRATIVE_FRAMES is only a pathological-output safety cap.
            # Empty in bullets mode (narrative_paragraphs == []) → loop no-ops.
            para_frames: dict[int, str] = {}
            para_fail = 0
            para_sel = even_indices(
                len(merged.narrative_paragraphs), MAX_NARRATIVE_FRAMES
            )
            for n_done, orig_i in enumerate(para_sel):
                para = merged.narrative_paragraphs[orig_i]
                pct = 0.70 + 0.25 * (n_done / max(1, len(para_sel)))
                progress_callback(
                    pct,
                    f"task.progress.summary_paragraph_frame|{n_done + 1}|{len(para_sel)}",
                )
                # Paragraph whose line citation didn't resolve to a usable
                # window: skip (no image) — not a failure.
                if para["time_range"] is None:
                    continue
                vlm_cb = (self._make_vlm_callback(
                    vlm_family, vlm_size, on_progress=progress_callback,
                    cancel_pct=pct,
                    cancel_msg=f"task.progress.summary_paragraph_frame|{n_done + 1}|{len(para_sel)}",
                ) if vlm_family and vlm_size else None)
                cand_max_edge = (
                    get_inference_config(
                        vlm_family, vlm_size, "frame_select"
                    )["max_image_edge"]
                    if vlm_family and vlm_size else None
                )
                try:
                    t_start, t_end = para["time_range"]
                    ts = pick_frame_timestamp(
                        detector=detector,
                        vlm_callback=vlm_cb,
                        video_path=video_path,
                        window_start=t_start,
                        window_end=t_end,
                        context_text=para["text"],
                        temp_dir=work_dir / f"candidates_p{orig_i}",
                        duration=video_duration,
                        fps=video_fps,
                        scenes=global_scenes,
                        candidate_max_edge=cand_max_edge,
                    )
                    if ts is None:
                        continue  # VLM judged no candidate matches — no image
                    out = frames_dir / f"para_{orig_i:03d}.jpg"
                    detector.extract_frame(
                        input_path=video_path, output_path=out, timestamp=ts
                    )
                    para_frames[orig_i] = f"frames/para_{orig_i:03d}.jpg"
                except TaskCancelledError:
                    raise
                except Exception as e:
                    para_fail += 1
                    logger.warning(
                        f"summary: paragraph {orig_i} frame failed ({e}); skipping image"
                    )
                    continue

            if bullet_fail or para_fail:
                logger.warning(
                    f"summary: frame extraction failed "
                    f"bullets={bullet_fail}/{len(merged.bullet_items)} "
                    f"paragraphs={para_fail}/{len(merged.narrative_paragraphs)} "
                    f"(report still produced without those inline images)"
                )

            # Step 6: build markdown + zip (95%)
            progress_callback(0.95, "task.progress.summary_packaging")
            md_text = build_markdown(
                result=merged,
                bullet_frames=bullet_frames,
                para_frames=para_frames,
                title=stem,
                language=language,
            )
            (work_dir / "summary.md").write_text(md_text, encoding="utf-8")

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                zf.write(work_dir / "summary.md", arcname="summary.md")
                for img in sorted(frames_dir.glob("*.jpg")):
                    zf.write(img, arcname=f"frames/{img.name}")
        finally:
            # Always clean up staging, even on exception
            shutil.rmtree(work_dir, ignore_errors=True)

        # Step 7: register output (only reached if zip succeeded)
        output_info = self._file_service.register_output(
            file_id=output_id,
            file_path=zip_path,
            original_filename=file_info.original_filename,
        )

        progress_callback(1.0, "task.progress.summary_complete")

        return {
            "output_file_id": output_id,
            "output_filename": output_info.filename,
            "output_size": output_info.file_size,
            "bullet_count": len(merged.bullet_items),
            "paragraph_count": len(merged.narrative_paragraphs),
        }

    def _make_vlm_callback(self, family: str, size: str, *,
                           on_progress=None, cancel_pct: float = 0.0,
                           cancel_msg: str = "task.progress.summary_bullet_frame"):
        """Build a VLM callback: (context_text, frame_paths) -> chosen_index.

        In v1, if `chat_with_images` isn't available on ChatService, the callback
        raises RuntimeError which `pick_frame_timestamp` catches and falls back to
        midpoint-nearest. This keeps the feature shippable without VLM support
        while leaving the hook for later.
        """
        cfg = get_inference_config(family, size, "frame_select")

        def _cb(context_text: str, frame_paths: list) -> int:
            if not hasattr(self._chat_service, "chat_with_images"):
                raise RuntimeError("VLM chat_with_images not available; falling back")
            indexed = "\n".join(f"{i}. (圖片 {i})" for i in range(len(frame_paths)))
            prompt = (
                f"以下段落文字：\n{context_text}\n\n"
                f"我提供 {len(frame_paths)} 張候選影格，請選出最能代表上述文字的一張。\n"
                f"{indexed}\n\n"
                f"若沒有任何一張與上述文字相符，回答 -1。\n"
                f"只回答一個數字（-1 到 {len(frame_paths) - 1}），不要多餘文字。"
            )
            max_tokens = calc_max_tokens(cfg, n_ctx=cfg["n_ctx"], input_len=estimate_tokens(prompt))
            raw = self._chat_service.chat_with_images(
                prompt=prompt,
                images=frame_paths,
                model_family=family,
                model_size=size,
                max_tokens=max_tokens,
                temperature=cfg["temperature"],
                on_progress=on_progress,
                cancel_pct=cancel_pct,
                cancel_msg=cancel_msg,
            )
            import re
            # Take the LAST integer token: a reasoning model puts its final
            # answer last. The numeric-only Chinese prompt makes decimal /
            # hyphenated-word false matches unlikely.
            nums = re.findall(r"-?\d+", raw)
            if not nums:
                raise ValueError(f"VLM response not a number: {raw!r}")
            return int(nums[-1])

        return _cb
