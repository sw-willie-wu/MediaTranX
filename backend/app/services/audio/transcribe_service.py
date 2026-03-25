"""
音訊逐字稿轉譯服務
使用 faster-whisper 將音訊轉為文字
"""
import asyncio
import logging
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from app.engine.ai.audio.whisper import WhisperWrapper, get_whisper, TranscribeResult
from app.utils.prompts import (
    WHISPER_TO_BCP47,
    build_srt_translate_prompt,
    build_translate_messages,
    build_summarize_prompt,
    build_chunk_summarize_prompt,
    build_merge_summaries_prompt,
    split_text_for_context,
    segments_to_srt,
    parse_srt_response,
    SUMMARIZE_PARAMS,
)
from app.services.files.file_service import FileService, get_file_service
from app.workers.task_manager import TaskManager, get_task_manager

logger = logging.getLogger(__name__)

TASK_TYPE_AUDIO_TRANSCRIBE = "audio.transcribe"


def _format_srt_time(seconds: float) -> str:
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    millis = int((seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _write_txt(result: TranscribeResult, output_path: Path) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        for seg in result.segments:
            f.write(seg.text.strip() + "\n")


def _write_srt(result: TranscribeResult, output_path: Path) -> None:
    with open(output_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(result.segments, 1):
            f.write(f"{i}\n")
            f.write(f"{_format_srt_time(seg.start)} --> {_format_srt_time(seg.end)}\n")
            f.write(f"{seg.text.strip()}\n\n")


class AudioTranscribeService:
    _instance: Optional["AudioTranscribeService"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._whisper: WhisperWrapper = get_whisper()
        self._file_service: FileService = get_file_service()
        self._task_manager: TaskManager = get_task_manager()
        self._task_manager.register_handler(TASK_TYPE_AUDIO_TRANSCRIBE, self._handle_task)
        self._initialized = True
        logger.info("AudioTranscribeService initialized")

    def get_model_status(self, model_size: str = "medium") -> dict:
        return self._whisper.get_model_status(model_size)

    async def submit_transcribe(
        self,
        file_id: str,
        language: Optional[str] = None,
        model_size: str = "medium",
        output_format: str = "txt",
        vocal_separation: bool = False,
        align: bool = False,
        translate: bool = False,
        target_lang: Optional[str] = None,
        translate_model_type: str = "translategemma",
        translate_model_size: str = "4b",
        translate_quantization: Optional[str] = None,
        translate_remote: bool = False,
        translate_provider: Optional[str] = None,
        translate_conn_id: Optional[int] = None,
        translate_remote_model: Optional[str] = None,
        summarize: bool = False,
        summarize_model_type: str = "qwen3",
        summarize_model_size: str = "4b",
        summarize_quantization: Optional[str] = None,
        summarize_remote: bool = False,
        summarize_provider: Optional[str] = None,
        summarize_conn_id: Optional[int] = None,
        summarize_remote_model: Optional[str] = None,
        output_dir: Optional[str] = None,
        output_filename: Optional[str] = None,
    ) -> str:
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")
        params = {
            "file_id": file_id,
            "language": language,
            "model_size": model_size,
            "output_format": output_format,
            "vocal_separation": vocal_separation,
            "align": align,
            "translate": translate,
            "target_lang": target_lang,
            "translate_model_type": translate_model_type,
            "translate_model_size": translate_model_size,
            "translate_quantization": translate_quantization,
            "translate_remote": translate_remote,
            "translate_provider": translate_provider,
            "translate_conn_id": translate_conn_id,
            "translate_remote_model": translate_remote_model,
            "summarize": summarize,
            "summarize_model_type": summarize_model_type,
            "summarize_model_size": summarize_model_size,
            "summarize_quantization": summarize_quantization,
            "summarize_remote": summarize_remote,
            "summarize_provider": summarize_provider,
            "summarize_conn_id": summarize_conn_id,
            "summarize_remote_model": summarize_remote_model,
            "output_dir": output_dir,
            "output_filename": output_filename,
        }
        task_id = await self._task_manager.submit(TASK_TYPE_AUDIO_TRANSCRIBE, params)
        logger.info(f"Audio transcribe task submitted: {task_id}")
        return task_id

    def _handle_task(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        file_id = params["file_id"]
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        output_format = params.get("output_format", "txt")
        do_align = params.get("align", False)
        do_translate = params.get("translate", False)
        target_lang = params.get("target_lang")
        do_summarize = params.get("summarize", False)

        original_stem = Path(file_info.original_filename).stem

        # 決定輸出目錄
        custom_output_dir = params.get("output_dir")
        if custom_output_dir:
            output_dir_path = Path(custom_output_dir)
        else:
            output_dir_path = self._file_service.output_dir
        output_dir_path.mkdir(parents=True, exist_ok=True)

        # 決定基礎檔名
        custom_output_filename = params.get("output_filename")
        if custom_output_filename:
            base_name = Path(custom_output_filename).stem
        else:
            base_name = original_stem

        do_vocal_sep = params.get("vocal_separation", False)
        audio_path = str(file_info.file_path)
        temp_vocals_path = None

        # ── 動態進度分配 ──
        # 根據啟用的功能分配權重，寫檔固定佔 5%
        weights = {"whisper": 5}  # whisper 是必做的，權重最高
        if do_vocal_sep:  weights["demucs"] = 3
        if do_align:      weights["align"] = 3
        if do_translate:  weights["translate"] = 2
        if do_summarize:  weights["summarize"] = 2
        total_weight = sum(weights.values())

        # 計算每個階段的起止比例（最後 5% 留給寫檔）
        stages: dict[str, tuple[float, float]] = {}
        cursor = 0.0
        for stage in ["demucs", "whisper", "align", "translate", "summarize"]:
            if stage in weights:
                w = weights[stage] / total_weight * 0.95
                stages[stage] = (cursor, cursor + w)
                cursor += w
        stages["write"] = (0.95, 1.0)

        def stage_progress(stage: str, p: float, msg: str):
            """在指定階段內回報進度 (p: 0.0~1.0)"""
            s, e = stages.get(stage, (0.0, 1.0))
            progress_callback(s + p * (e - s), msg)

        # === GPU 排隊管線 ===
        from app.engine.ai.model_manager import get_model_manager
        manager = get_model_manager()

        with manager.gpu_session():
            # === 人聲分離 ===
            if do_vocal_sep:
                stage_progress("demucs", 0.0, "人聲分離中...")
                from app.engine.ai.audio.demucs import get_demucs
                demucs = get_demucs()
                separated, sr = demucs.separate(
                    audio_path=audio_path,
                    variant="htdemucs_6s",
                    stems=["vocals"],
                    on_progress=lambda p, m: stage_progress("demucs", p, m),
                )

                import tempfile
                import soundfile as sf
                vocals = separated.get("vocals")
                if vocals is not None:
                    temp_vocals = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
                    temp_vocals_path = temp_vocals.name
                    temp_vocals.close()
                    sf.write(temp_vocals_path, vocals.T.numpy(), sr)
                    audio_path = temp_vocals_path
                stage_progress("demucs", 1.0, "人聲分離完成")

            try:
                # === Whisper 轉譯 ===
                stage_progress("whisper", 0.0, "載入模型...")

                result = self._whisper.transcribe(
                    audio_path=audio_path,
                    language=params.get("language"),
                    model_size=params.get("model_size", "medium"),
                    word_timestamps=do_align,
                    condition_on_previous_text=True,
                    on_progress=lambda p, m: stage_progress("whisper", p, m),
                )

                detected_lang = result.language
                stage_progress("whisper", 1.0, "語音辨識完成")
            finally:
                if temp_vocals_path:
                    try:
                        Path(temp_vocals_path).unlink(missing_ok=True)
                    except Exception:
                        pass

            # === Wav2Vec2 精準對齊 ===
            if do_align and detected_lang:
                from app.engine.ai.audio.wav2vec2 import get_alignment_engine
                aligner = get_alignment_engine()
                if aligner.is_language_supported(detected_lang):
                    stage_progress("align", 0.0, "精準對齊中...")
                    result.segments = aligner.align(
                        audio_path=str(file_info.file_path),
                        segments=result.segments,
                        language=detected_lang,
                        on_progress=lambda p, m: stage_progress("align", p, m),
                    )
                    stage_progress("align", 1.0, "對齊完成")

        # === 翻譯 ===
        from app.engine.ai.audio.whisper import TranscribeSegment

        original_segments = list(result.segments)

        if do_translate and target_lang:
            stage_progress("translate", 0.0, "準備翻譯...")

            translate_remote = params.get("translate_remote", False)

            if translate_remote:
                # 雲端翻譯
                from app.services.setup.remote_service import get_remote_service
                remote_svc = get_remote_service()
                provider = params.get("translate_provider", "")
                conn_id = params.get("translate_conn_id")
                remote_model = params.get("translate_remote_model", "")

                seg_texts = [s.text.strip() for s in result.segments]
                combined = "\n".join(seg_texts)

                translated_text = remote_svc.translate_text(
                    text=combined,
                    target_lang=target_lang,
                    source_lang=detected_lang,
                    provider=provider,
                    conn_id=conn_id,
                    model_id=remote_model,
                )
                translated_lines = translated_text.strip().split("\n")

                translated_segs = []
                for i, seg in enumerate(result.segments):
                    text = translated_lines[i] if i < len(translated_lines) else seg.text
                    translated_segs.append(TranscribeSegment(seg.start, seg.end, text))
                result.segments = translated_segs
            else:
                # 本地翻譯
                from app.engine.ai.runtime.llama_server import LlamaServerRuntime
                from app.engine.ai.registry import SLOT_LLM

                translate_model_type = params.get("translate_model_type", "translategemma")
                translate_model_size = params.get("translate_model_size", "4b")
                translate_quantization = params.get("translate_quantization")

                seg_dicts = [
                    {"start": s.start, "end": s.end, "text": s.text}
                    for s in result.segments
                ]

                def translate_progress(percent: float, msg: str):
                    stage_progress("translate", percent, msg)

                variant = f"{translate_model_size}:{translate_quantization}" if translate_quantization else translate_model_size
                src = WHISPER_TO_BCP47.get(detected_lang, detected_lang)
                runtime = LlamaServerRuntime(SLOT_LLM)
                batch_size = 5

                def _load_progress(p, msg):
                    translate_progress(p * 0.05, msg)

                translate_progress(0.0, "載入翻譯模型...")

                with runtime.acquire(translate_model_type, variant, _load_progress):
                    translate_progress(0.05, "開始翻譯字幕...")

                    total = len(seg_dicts)
                    translated_all = []
                    num_batches = (total + batch_size - 1) // batch_size

                    for batch_idx in range(num_batches):
                        start_idx = batch_idx * batch_size
                        end_idx = min(start_idx + batch_size, total)
                        batch_segments = seg_dicts[start_idx:end_idx]

                        srt_text = segments_to_srt(batch_segments, start_index=start_idx + 1)
                        prompt = build_srt_translate_prompt(
                            srt_text, src, target_lang,
                            model_id=translate_model_type,
                        )
                        messages = build_translate_messages(prompt, translate_model_type)
                        translated_srt = runtime.chat(
                            messages=messages,
                            max_tokens=min(len(srt_text) * 3, 4096),
                            temperature=0.1,
                        )

                        batch_translated = parse_srt_response(translated_srt, batch_segments)
                        translated_all.extend(batch_translated)

                        if num_batches > 0:
                            progress = min((batch_idx + 1) / num_batches, 1.0)
                            translate_progress(
                                0.05 + progress * 0.95,
                                f"翻譯中... {end_idx}/{total} 段"
                            )

                    translate_progress(1.0, "字幕翻譯完成")

                result.segments = [
                    TranscribeSegment(s["start"], s["end"], s["text"])
                    for s in translated_all
                ]

        # === 大綱整理 ===
        summary_text = None
        if do_summarize:
            stage_progress("summarize", 0.0, "正在生成摘要大綱...")

            # 摘要用的文本：有翻譯用翻譯後的，沒翻譯用原文
            if do_translate and translated_segments:
                full_text = "\n".join(s.text.strip() for s in translated_segments)
            else:
                full_text = "\n".join(s.text.strip() for s in original_segments)

            summarize_remote = params.get("summarize_remote", False)

            if summarize_remote:
                # 雲端模型 context window 夠大，直接送整段
                summary_prompt = build_summarize_prompt(full_text)
                from app.services.setup.remote_service import get_remote_service
                remote_svc = get_remote_service()
                conn_id = params.get("summarize_conn_id")

                from app.db.dao.api_connection_dao import ApiConnectionDAO
                dao = ApiConnectionDAO()
                conn_info = dao.get_by_id(conn_id) if conn_id else None
                if conn_info:
                    p = remote_svc._get_provider(conn_info.provider, conn_info.endpoint, conn_info.api_key)
                    remote_model = params.get("summarize_remote_model", "")
                    summary_text = p.chat(
                        model=remote_model or "",
                        messages=[{"role": "user", "content": summary_prompt}],
                        max_tokens=2048,
                    )
            else:
                # 本地模型用 map-reduce：分段摘要 → 合併
                from app.engine.ai.runtime.llama_server import LlamaServerRuntime
                from app.engine.ai.registry import SLOT_LLM
                summary_model_id = params.get("summarize_model_type", "qwen3")
                summary_model_size = params.get("summarize_model_size", "4b")
                summary_quantization = params.get("summarize_quantization")
                summary_variant = f"{summary_model_size}:{summary_quantization}" if summary_quantization else summary_model_size
                runtime = LlamaServerRuntime(SLOT_LLM)

                chunks = split_text_for_context(full_text, max_tokens=2000)

                with runtime.acquire(summary_model_id, summary_variant):
                    if len(chunks) == 1:
                        # 短文本：直接摘要
                        summary_text = runtime.chat(
                            messages=[{"role": "user", "content": build_summarize_prompt(full_text)}],
                            max_tokens=2048,
                            temperature=0.3,
                        )
                    else:
                        # Map: 各段獨立摘要
                        chunk_summaries = []
                        for ci, chunk in enumerate(chunks):
                            stage_progress(
                                "summarize",
                                0.1 + 0.7 * (ci / len(chunks)),
                                f"摘要分段 {ci + 1}/{len(chunks)}...",
                            )
                            chunk_summary = runtime.chat(
                                messages=[{"role": "user", "content": build_chunk_summarize_prompt(chunk)}],
                                max_tokens=1024,
                                temperature=0.3,
                            )
                            chunk_summaries.append(chunk_summary.strip())

                        # Reduce: 合併所有分段摘要
                        stage_progress("summarize", 0.85, "合併摘要...")
                        merged = "\n\n".join(chunk_summaries)
                        summary_text = runtime.chat(
                            messages=[{"role": "user", "content": build_merge_summaries_prompt(merged)}],
                            max_tokens=2048,
                            temperature=0.3,
                        )

            stage_progress("summarize", 1.0, "摘要完成")

        # === 寫入輸出檔案 ===
        stage_progress("write", 0.0, "正在寫入檔案...")

        output_files = []

        if do_translate and target_lang:
            # 有翻譯：輸出兩個檔案
            # 1. 原始語言逐字稿
            source_filename = f"{base_name}.{detected_lang}.{output_format}"
            source_path = output_dir_path / source_filename
            source_result = TranscribeResult(
                segments=original_segments, language=detected_lang
            )
            if output_format == "srt":
                _write_srt(source_result, source_path)
            else:
                _write_txt(source_result, source_path)

            source_file_id = str(uuid4())
            source_info = self._file_service.register_output(
                file_id=source_file_id,
                file_path=source_path,
                original_filename=file_info.original_filename,
            )
            output_files.append({
                "file_id": source_file_id,
                "filename": source_info.filename,
                "language": detected_lang,
                "type": "source",
            })

            # 2. 翻譯後逐字稿
            target_filename = f"{base_name}.{target_lang}.{output_format}"
            target_path = output_dir_path / target_filename
            target_result = TranscribeResult(
                segments=result.segments, language=target_lang
            )
            if output_format == "srt":
                _write_srt(target_result, target_path)
            else:
                _write_txt(target_result, target_path)

            target_file_id = str(uuid4())
            target_info = self._file_service.register_output(
                file_id=target_file_id,
                file_path=target_path,
                original_filename=file_info.original_filename,
            )
            output_files.append({
                "file_id": target_file_id,
                "filename": target_info.filename,
                "language": target_lang,
                "type": "translated",
            })

            output_file_id = target_file_id
            output_filename_result = target_info.filename
        else:
            # 無翻譯：輸出單一檔案
            final_filename = f"{base_name}.{output_format}"
            output_path = output_dir_path / final_filename
            if output_format == "srt":
                _write_srt(result, output_path)
            else:
                _write_txt(result, output_path)

            output_file_id = str(uuid4())
            output_info = self._file_service.register_output(
                file_id=output_file_id,
                file_path=output_path,
                original_filename=file_info.original_filename,
            )
            output_files.append({
                "file_id": output_file_id,
                "filename": output_info.filename,
                "language": detected_lang,
                "type": "source",
            })
            output_filename_result = output_info.filename

        # 寫入摘要檔案
        if summary_text:
            summary_filename = f"{base_name}.draft.txt"
            summary_path = output_dir_path / summary_filename
            with open(summary_path, "w", encoding="utf-8") as f:
                f.write(summary_text)

            summary_file_id = str(uuid4())
            summary_info = self._file_service.register_output(
                file_id=summary_file_id,
                file_path=summary_path,
                original_filename=file_info.original_filename,
            )
            output_files.append({
                "file_id": summary_file_id,
                "filename": summary_info.filename,
                "language": detected_lang,
                "type": "summary",
            })

        progress_callback(1.0, "轉譯完成")

        # Read transcript content for preview
        text_content = None
        if output_files:
            try:
                fid = output_files[0]["file_id"]
                info = self._file_service.get_file_info(fid)
                if info and info.file_path:
                    with open(info.file_path, "r", encoding="utf-8") as f:
                        text_content = f.read()
            except Exception:
                pass

        return {
            "output_file_id": output_file_id,
            "output_filename": output_filename_result,
            "output_files": output_files,
            "text_file_id": output_file_id,
            "text_content": text_content,
            "detected_language": detected_lang,
            "segment_count": len(result.segments),
            "translated": do_translate and target_lang is not None,
            "target_language": target_lang,
            "summarized": do_summarize,
        }


_service: Optional[AudioTranscribeService] = None

def get_audio_transcribe_service() -> AudioTranscribeService:
    global _service
    if _service is None:
        _service = AudioTranscribeService()
    return _service
