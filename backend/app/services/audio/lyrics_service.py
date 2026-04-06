"""
歌詞提取服務
使用 Demucs 人聲分離 + Whisper 語音辨識，從音樂中提取歌詞
"""
import asyncio
import logging
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

import soundfile as sf

from app.utils.prompts import (
    WHISPER_TO_BCP47,
    build_srt_translate_prompt,
    build_translate_messages,
    segments_to_srt,
    parse_srt_response,
)
from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_AUDIO_LYRICS = "audio.lyrics"


def _format_lrc_time(seconds: float) -> str:
    """將秒數格式化為 LRC 時間格式 [mm:ss.xx]"""
    minutes = int(seconds // 60)
    secs = seconds % 60
    return f"{minutes:02d}:{secs:05.2f}"


class AudioLyricsService:

    def __init__(self, file_service: FileService, task_manager: TaskManager):
        self._file_service = file_service
        self._task_manager = task_manager
        self._task_manager.register_handler(TASK_TYPE_AUDIO_LYRICS, self._handle_task)
        logger.info("AudioLyricsService initialized")

    async def submit_lyrics(
        self,
        file_id: str,
        whisper_model: str = "faster-whisper",
        whisper_size: str = "medium",
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
        output_format: str = "lrc",
        output_dir: Optional[str] = None,
        output_filename: Optional[str] = None,
    ) -> str:
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")
        params = {
            "file_id": file_id,
            "whisper_model": whisper_model,
            "whisper_size": whisper_size,
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
            "output_format": output_format,
            "output_dir": output_dir,
            "output_filename": output_filename,
        }
        task_id = await self._task_manager.submit(TASK_TYPE_AUDIO_LYRICS, params)
        logger.info(f"Audio lyrics task submitted: {task_id}")
        return task_id

    def _handle_task(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(self._execute(params, progress_callback))
        finally:
            loop.close()

    async def _execute(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        file_id = params["file_id"]
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        whisper_size = params.get("whisper_size", "medium")
        align = params.get("align", False)
        do_translate = params.get("translate", False)
        target_lang = params.get("target_lang")
        output_format = params.get("output_format", "lrc")

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

        # ── 動態進度分配 ──
        weights = {"demucs": 3, "whisper": 5}  # demucs 和 whisper 必做
        if align:         weights["align"] = 3
        if do_translate:  weights["translate"] = 2
        total_weight = sum(weights.values())

        stages: dict[str, tuple[float, float]] = {}
        cursor = 0.0
        for stage in ["demucs", "whisper", "align", "translate"]:
            if stage in weights:
                w = weights[stage] / total_weight * 0.95
                stages[stage] = (cursor, cursor + w)
                cursor += w
        stages["write"] = (0.95, 1.0)

        def stage_progress(stage: str, p: float, msg: str):
            s, e = stages.get(stage, (0.0, 1.0))
            progress_callback(s + p * (e - s), msg)

        # 暫存人聲檔案路徑
        temp_vocals_path = self._file_service.upload_dir / f"_vocals_temp_{uuid4().hex[:8]}.wav"

        try:
            # === Demucs 人聲分離 ===
            stage_progress("demucs", 0.0, "正在分離人聲...")

            from app.engine.ai.audio.demucs import get_demucs
            demucs = get_demucs()
            separated, sample_rate = demucs.separate(
                audio_path=str(file_info.file_path),
                variant="htdemucs_6s",
                stems=["vocals"],
                on_progress=lambda p, m: stage_progress("demucs", p, m),
            )

            # 儲存人聲為暫存 WAV
            vocals_tensor = separated.get("vocals")
            if vocals_tensor is None:
                raise RuntimeError("Demucs failed to separate vocals")
            audio_data = vocals_tensor.numpy().T
            sf.write(str(temp_vocals_path), audio_data, sample_rate)

            stage_progress("demucs", 1.0, "人聲分離完成")

            # === GPU 排隊管線 ===
            from app.init.container import get_container
            manager = get_container().model_manager()

            with manager.gpu_session():
                # === Whisper 語音辨識 ===
                from app.engine.ai.audio.whisper import get_whisper
                whisper = get_whisper()

                result = whisper.transcribe(
                    audio_path=str(temp_vocals_path),
                    model_size=whisper_size,
                    on_progress=lambda p, m: stage_progress("whisper", p, m),
                    word_timestamps=align,
                )

                detected_lang = result.language
                stage_progress("whisper", 1.0, "語音辨識完成")

                # === Wav2Vec2 精準對齊 ===
                if align and detected_lang:
                    from app.engine.ai.audio.wav2vec2 import get_alignment_engine
                    aligner = get_alignment_engine()
                    if aligner.is_language_supported(detected_lang):
                        stage_progress("align", 0.0, "精準對齊中...")
                        result.segments = aligner.align(
                            audio_path=str(temp_vocals_path),
                            segments=result.segments,
                            language=detected_lang,
                            on_progress=lambda p, m: stage_progress("align", p, m),
                        )
                        stage_progress("align", 1.0, "對齊完成")

                # === 翻譯 ===
                from app.engine.ai.audio.whisper import TranscribeSegment

                original_segments = list(result.segments)

                if do_translate and target_lang:
                    stage_progress("translate", 0.0, "準備翻譯歌詞...")

                    translate_remote = params.get("translate_remote", False)

                    if translate_remote:
                        # 雲端翻譯（批次）
                        from app.utils.translate import get_cloud_provider, translate_srt_cloud

                        provider = params.get("translate_provider", "")
                        conn_id = params.get("translate_conn_id")
                        remote_model = params.get("translate_remote_model", "")
                        prov = get_cloud_provider(provider, conn_id, remote_model)

                        seg_dicts = [{"start": s.start, "end": s.end, "text": s.text} for s in result.segments]
                        translated_all = translate_srt_cloud(
                            seg_dicts, detected_lang, target_lang, prov, remote_model,
                            on_progress=lambda p, m: stage_progress("translate", p, m),
                        )

                        result.segments = [
                            TranscribeSegment(s["start"], s["end"], s["text"])
                            for s in translated_all
                        ]
                    else:
                        # 本地翻譯
                        from app.engine.ai.runtime.llama_server import LlamaServerRuntime
                        from app.engine.ai.registry import SLOT_LLM

                        translate_model_type = params.get("translate_model_type", "translategemma")
                        translate_model_size = params.get("translate_model_size", "4b")
                        translate_quantization = params.get("translate_quantization")

                        from app.utils.translate import translate_srt_local

                        seg_dicts = [
                            {"start": s.start, "end": s.end, "text": s.text}
                            for s in result.segments
                        ]

                        variant = f"{translate_model_size}:{translate_quantization}" if translate_quantization else translate_model_size
                        src = WHISPER_TO_BCP47.get(detected_lang, detected_lang)
                        runtime = LlamaServerRuntime(SLOT_LLM)

                        stage_progress("translate", 0.0, "載入翻譯模型...")

                        with runtime.acquire(translate_model_type, variant, lambda p, m: stage_progress("translate", p * 0.05, m)):
                            stage_progress("translate", 0.05, "開始翻譯歌詞...")
                            translated_all = translate_srt_local(
                                seg_dicts, src, target_lang, runtime,
                                on_progress=lambda p, m: stage_progress("translate", 0.05 + p * 0.95, m),
                                model_id=translate_model_type,
                            )

                        stage_progress("translate", 1.0, "歌詞翻譯完成")

                        result.segments = [
                            TranscribeSegment(s["start"], s["end"], s["text"])
                            for s in translated_all
                        ]

            # === 階段 4: 寫入輸出檔案 (0.95 ~ 1.0) ===
            stage_progress("write", 0.0, "正在寫入歌詞檔...")

            output_files = []

            if do_translate and target_lang:
                # 有翻譯：輸出兩個檔案
                # 1. 原始語言歌詞
                source_filename = f"{base_name}.{detected_lang}.{output_format}"
                source_path = output_dir_path / source_filename
                self._write_output(original_segments, source_path, output_format)

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

                # 2. 翻譯後歌詞
                target_filename = f"{base_name}.{target_lang}.{output_format}"
                target_path = output_dir_path / target_filename
                self._write_output(result.segments, target_path, output_format)

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
                self._write_output(result.segments, output_path, output_format)

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

            progress_callback(1.0, "歌詞提取完成")

            # Read lyrics content for preview
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
            }

        finally:
            # 清理暫存人聲檔案
            if temp_vocals_path.exists():
                try:
                    temp_vocals_path.unlink()
                except OSError:
                    logger.warning(f"Failed to delete temp vocals: {temp_vocals_path}")

    @staticmethod
    def _write_output(segments, output_path: Path, output_format: str) -> None:
        """根據格式寫入歌詞檔"""
        with open(output_path, "w", encoding="utf-8") as f:
            if output_format == "lrc":
                for seg in segments:
                    timestamp = _format_lrc_time(seg.start)
                    f.write(f"[{timestamp}]{seg.text.strip()}\n")
            else:
                # txt: 純文字，一行一段
                for seg in segments:
                    f.write(seg.text.strip() + "\n")
