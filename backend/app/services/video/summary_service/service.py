"""Video summary service — transcript -> LLM -> key frames -> markdown -> zip."""
from __future__ import annotations
import logging
import shutil
import zipfile
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

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
    format_transcript,
    merge_chunk_outputs,
    parse_bullets_markdown,
    parse_summary_json,
)
from .markdown import build_markdown
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_VIDEO_SUMMARY = "video.summary"


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
        whisper: WhisperWrapper,
        demucs: DemucsWrapper = None,
        alignment_engine: AlignmentEngine = None,
    ):
        self._ffmpeg = ffmpeg
        self._file_service = file_service
        self._task_manager = task_manager
        self._chat_service = chat_service
        self._model_manager = model_manager
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
        llm_model_family: str,
        llm_model_size: str,
        language: str = "zh-TW",
        vlm_model_family: Optional[str] = None,
        vlm_model_size: Optional[str] = None,
        whisper_model_size: str = "medium",
        vocal_separation: bool = False,
        align: bool = False,
        word_timestamps: bool = False,
        condition_on_previous_text: bool = True,
        min_silence_duration_ms: int = 200,
        vad_threshold: float = 0.3,
        summary_mode: str = "bullets",
    ) -> str:
        """Submit a summary task."""
        file_info = self._file_service.require_file(file_id)

        params = {
            "file_id": file_id,
            "llm_model_family": llm_model_family,
            "llm_model_size": llm_model_size,
            "language": language,
            "vlm_model_family": vlm_model_family,
            "vlm_model_size": vlm_model_size,
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

            # Step 1b: transcribe (0.05 ~ 0.15)
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
                # Map [0,1] from whisper to [0.05, 0.15] of overall progress.
                progress_callback(0.05 + p * 0.10, m)

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

        # Step 2: chunk + LLM (15% ~ 60%)
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
        for i, chunk in enumerate(chunks):
            pct = 0.15 + 0.45 * (i / max(1, len(chunks)))
            progress_callback(
                pct, f"task.progress.summary_chunk|{i + 1}|{len(chunks)}"
            )
            # Note: deliberately bypasses get_prompt_builder("summarize", ...) because this task
            # uses dedicated structured prompts (hierarchical-markdown for bullets mode,
            # JSON for narrative mode) — see video_summary.py for the templates.
            output_lang = _resolve_output_language(language, result.language)
            prompt = build_summary_prompt(
                format_transcript(chunk),
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
            )
            try:
                if summary_mode == SUMMARY_MODE_NARRATIVE:
                    chunk_results.append(parse_summary_json(raw))
                else:
                    chunk_results.append(parse_bullets_markdown(raw))
            except ValueError as e:
                logger.warning(f"Chunk {i} parse failed: {e}; skipping")

        if not chunk_results:
            raise RuntimeError("All chunks failed to produce a usable summary")

        merged = merge_chunk_outputs(chunk_results)

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
            detector = SceneDetector(ffmpeg=self._ffmpeg)

            vlm_cb = None
            if vlm_family and vlm_size:
                vlm_cb = self._make_vlm_callback(vlm_family, vlm_size)

            # Step 4: bullet frames (60% ~ 80%)
            # Iterate over merged.bullet_items (each carries time_range + line_index for image insertion).
            # Per-item resilience: a single frame-extraction failure (e.g. an
            # LLM-drifted timestamp ffmpeg can't decode) must NOT abort the
            # whole job — the summary text is already generated. Skip the inline
            # image for that item and continue. progress_callback stays OUTSIDE
            # the try so cooperative TaskCancelledError still propagates.
            bullet_frames: dict[int, str] = {}
            bullet_fail = 0
            md_lines = merged.bullets_markdown.splitlines()
            for i, item in enumerate(merged.bullet_items):
                pct = 0.60 + 0.20 * (i / max(1, len(merged.bullet_items)))
                progress_callback(
                    pct,
                    f"task.progress.summary_bullet_frame|{i + 1}|{len(merged.bullet_items)}",
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
                        temp_dir=work_dir / f"candidates_b{i}",
                        duration=video_duration,
                        fps=video_fps,
                    )
                    out = frames_dir / f"bullet_{i:03d}.jpg"
                    detector.extract_frame(
                        input_path=video_path, output_path=out, timestamp=ts
                    )
                    bullet_frames[i] = f"frames/bullet_{i:03d}.jpg"
                except Exception as e:
                    bullet_fail += 1
                    logger.warning(
                        f"summary: bullet {i} frame failed ({e}); skipping image"
                    )
                    continue

            # Step 5: turning-point frames (80% ~ 90%)
            tp_frames: dict[int, str] = {}
            tp_fail = 0
            for i, tp in enumerate(merged.turning_points):
                pct = 0.80 + 0.10 * (i / max(1, len(merged.turning_points)))
                progress_callback(
                    pct,
                    f"task.progress.summary_tp_frame|{i + 1}|{len(merged.turning_points)}",
                )
                try:
                    t = tp["time"]
                    ts = pick_frame_timestamp(
                        detector=detector,
                        vlm_callback=vlm_cb,
                        video_path=video_path,
                        window_start=max(0.0, t - 5.0),
                        window_end=t + 5.0,
                        context_text=tp["text"],
                        temp_dir=work_dir / f"candidates_t{i}",
                        duration=video_duration,
                        fps=video_fps,
                    )
                    out = frames_dir / f"tp_{i:03d}.jpg"
                    detector.extract_frame(
                        input_path=video_path, output_path=out, timestamp=ts
                    )
                    tp_frames[i] = f"frames/tp_{i:03d}.jpg"
                except Exception as e:
                    tp_fail += 1
                    logger.warning(
                        f"summary: turning-point {i} frame failed ({e}); skipping image"
                    )
                    continue

            if bullet_fail or tp_fail:
                logger.warning(
                    f"summary: frame extraction failed "
                    f"bullets={bullet_fail}/{len(merged.bullet_items)} "
                    f"tp={tp_fail}/{len(merged.turning_points)} "
                    f"(report still produced without those inline images)"
                )

            # Step 6: build markdown + zip (90% ~ 95%)
            progress_callback(0.92, "task.progress.summary_packaging")
            md_text = build_markdown(
                result=merged,
                bullet_frames=bullet_frames,
                tp_frames=tp_frames,
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
            "turning_point_count": len(merged.turning_points),
        }

    def _make_vlm_callback(self, family: str, size: str):
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
                f"只回答一個數字（0 到 {len(frame_paths) - 1}），不要多餘文字。"
            )
            max_tokens = calc_max_tokens(cfg, n_ctx=cfg["n_ctx"], input_len=estimate_tokens(prompt))
            raw = self._chat_service.chat_with_images(
                prompt=prompt,
                images=frame_paths,
                model_family=family,
                model_size=size,
                max_tokens=max_tokens,
                temperature=cfg["temperature"],
            )
            import re
            m = re.search(r"\d+", raw)
            if not m:
                raise ValueError(f"VLM response not a number: {raw!r}")
            return int(m.group())

        return _cb
