"""
Image OCR service.
Uses vision-language models (Qwen3-VL / InternVL2.5 / Gemma3) to recognize text in images.
"""
import logging
from pathlib import Path
from typing import Callable, Optional

from PIL import Image as PILImage

from app.adapters.ai.model_manager import ModelManager
from app.utils.prompts import DEFAULT_VLM_MODEL
from app.services.files.file_service import FileService
from app.services.llm.language_service import LanguageService
from app.services.setup.remote_service import RemoteService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_IMAGE_OCR = "image.ocr"
TASK_TYPE_IMAGE_OCR_REMOTE = "image.ocr.remote"


class ImageOcrService:
    """Image OCR using vision-language models (local or remote)."""

    def __init__(self, file_service: FileService, task_manager: TaskManager,
                 model_manager: ModelManager, chat_service,
                 language_service: LanguageService, remote_service: RemoteService):
        self._file_service = file_service
        self._task_manager = task_manager
        self._model_manager = model_manager
        self._chat_service = chat_service
        self._language_service = language_service
        self._remote_service = remote_service
        self._task_manager.register_handler(
            TASK_TYPE_IMAGE_OCR, self._handle_task,
            output_policy="results",
        )
        self._task_manager.register_handler(
            TASK_TYPE_IMAGE_OCR_REMOTE, self._handle_remote_task,
            output_policy="results",
        )
        logger.info("ImageOcrService initialized")

    def get_status(
        self,
        model_family: str = DEFAULT_VLM_MODEL,
        size: str = "4b",
        quantization: Optional[str] = None,
    ) -> dict:
        """Query VLM OCR status."""
        return self._language_service.get_vlm_status(model_family=model_family, size=size, quantization=quantization)

    async def submit_ocr(
        self,
        file_id: str,
        model_family: str = DEFAULT_VLM_MODEL,
        size: str = "4b",
        quantization: Optional[str] = None,
        format: str = "md",
    ) -> str:
        """Submit an OCR task."""
        file_info = self._file_service.require_file(file_id)

        params = {
            "file_id": file_id,
            "model_family": model_family,
            "size": size,
            "quantization": quantization,
            "format": format,
        }
        task_id = await self._task_manager.submit(TASK_TYPE_IMAGE_OCR, params)
        logger.info(f"Image OCR task submitted: {task_id}")
        return task_id

    def _handle_task(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        file_id = params["file_id"]
        file_info = self._file_service.require_file(file_id)

        model_family = params.get("model_family", DEFAULT_VLM_MODEL)
        size = params.get("size", "4b")
        quantization = params.get("quantization")
        fmt = params.get("format", "md")
        ext = "md" if fmt == "md" else "txt"

        progress_callback(0.05, "task.progress.ocr_prepare")

        if not self._model_manager.is_llama_ready():
            raise RuntimeError("llama-server not installed; please install AI core environment in settings")

        # === GPU queue pipeline ===
        with self._model_manager.gpu_session(), self._chat_service.session(
            model_family=model_family,
            model_size=size,
            quantization=quantization,
            on_load_progress=lambda p, m: progress_callback(0.1 + p * 0.05, m),
        ) as session:
            from app.pipeline.ocr import recognize_image_local

            variant = f"{size}:{quantization}" if quantization else size
            final_text = recognize_image_local(
                str(file_info.file_path), model_family, variant, fmt, session,
                on_progress=lambda p, m: progress_callback(0.15 + p * 0.80, m),
            )

        if not final_text.strip():
            final_text = "(No text detected)"

        # Save output file
        progress_callback(0.97, "task.progress.ocr_saving")
        output_file_id, output_path = self._file_service.create_output_path(
            original_filename=file_info.original_filename,
            suffix="_ocr",
            ext=f".{ext}",
        )

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(final_text)

        output_info = self._file_service.register_output(
            file_id=output_file_id,
            file_path=output_path,
            original_filename=output_path.name,
        )

        progress_callback(1.0, "task.progress.ocr_complete")
        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
            "char_count": len(final_text),
        }


    async def submit_ocr_remote(
        self,
        file_id: str,
        provider: str,
        conn_id: Optional[int],
        remote_model: str,
        format: str = "md",
    ) -> str:
        """Submit a remote OCR task."""
        file_info = self._file_service.require_file(file_id)

        params = {
            "file_id": file_id,
            "provider": provider,
            "conn_id": conn_id,
            "remote_model": remote_model,
            "format": format,
        }
        task_id = await self._task_manager.submit(TASK_TYPE_IMAGE_OCR_REMOTE, params)
        logger.info(f"Remote OCR task submitted: {task_id} (provider={provider}, model={remote_model})")
        return task_id

    def _handle_remote_task(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        """Handle remote OCR task."""
        file_id = params["file_id"]
        file_info = self._file_service.require_file(file_id)

        provider = params["provider"]
        conn_id = params.get("conn_id")
        remote_model = params["remote_model"]
        fmt = params.get("format", "md")
        ext = "md" if fmt == "md" else "txt"

        progress_callback(0.05, f"task.progress.connecting_provider|{provider}")

        p = self._remote_service.get_provider_for_connection(conn_id, provider)
        if p is None:
            raise RuntimeError(f"Provider not available: {provider}")

        progress_callback(0.1, "task.progress.prepare_image")
        from app.utils.vision_messages import prepare_image_for_remote_vlm, build_vision_chat_messages
        image_b64, mime_type = prepare_image_for_remote_vlm(str(file_info.file_path))

        if fmt == "md":
            prompt = "Please perform OCR on this image. Extract all text content and format it as clean Markdown. Preserve the document structure (headings, lists, tables, etc.) as much as possible. Output only the extracted text in Markdown format, no explanations."
        else:
            prompt = "Please perform OCR on this image. Extract all text content as plain text. Output only the extracted text, no explanations."

        progress_callback(0.2, "task.progress.recognizing")
        messages = build_vision_chat_messages(provider, prompt, image_b64, mime_type)

        from app.adapters.ai.inference_config import get_remote_inference_config
        remote_config = get_remote_inference_config("ocr")
        final_text = p.chat(
            model=remote_model, messages=messages,
            max_tokens=remote_config["max_tokens"],
            temperature=remote_config["temperature"],
        )

        if not final_text.strip():
            final_text = "(No text detected)"

        # Save result
        progress_callback(0.95, "task.progress.ocr_saving")
        output_file_id, output_path = self._file_service.create_output_path(
            original_filename=file_info.original_filename,
            suffix="_ocr",
            ext=f".{ext}",
        )

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(final_text)

        output_info = self._file_service.register_output(
            file_id=output_file_id,
            file_path=output_path,
            original_filename=output_path.name,
        )

        progress_callback(1.0, "task.progress.ocr_complete")
        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
            "char_count": len(final_text),
        }
