"""
Document OCR service.
PDF: render each page then recognize with VLM; images: recognize directly.
"""
import logging
from pathlib import Path
from typing import Callable, Optional

from app.engine.ai.model_manager import ModelManager
from app.utils.prompts import DEFAULT_VLM_MODEL
from app.services.files.file_service import FileService
from app.services.llm.language_service import LanguageService
from app.services.setup.remote_service import RemoteService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_DOCUMENT_OCR = "document.ocr"
TASK_TYPE_DOCUMENT_OCR_REMOTE = "document.ocr.remote"

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}


class DocumentOcrService:
    """Document OCR service for PDF and images using VLM (local or remote)."""

    def __init__(self, file_service: FileService, task_manager: TaskManager,
                 model_manager: ModelManager, llama_runtime,
                 language_service: LanguageService, remote_service: RemoteService):
        self._file_service = file_service
        self._task_manager = task_manager
        self._model_manager = model_manager
        self._llama_runtime = llama_runtime
        self._language_service = language_service
        self._remote_service = remote_service
        self._task_manager.register_handler(
            TASK_TYPE_DOCUMENT_OCR, self._handle_task,
            output_policy="results",
        )
        self._task_manager.register_handler(
            TASK_TYPE_DOCUMENT_OCR_REMOTE, self._handle_remote_task,
            output_policy="results",
        )
        logger.info("DocumentOcrService initialized")

    def get_status(self, model_family: str = DEFAULT_VLM_MODEL, size: str = "4b",
                   quantization: Optional[str] = None) -> dict:
        return self._language_service.get_vlm_status(model_family=model_family, size=size, quantization=quantization)

    async def submit(
        self,
        file_id: str,
        model_family: str = DEFAULT_VLM_MODEL,
        size: str = "4b",
        quantization: Optional[str] = None,
        format: str = "md",
    ) -> str:
        file_info = self._file_service.require_file(file_id)
        params = {
            "file_id": file_id, "model_family": model_family,
            "size": size, "quantization": quantization,
            "format": format,
        }
        task_id = await self._task_manager.submit(TASK_TYPE_DOCUMENT_OCR, params)
        logger.info(f"Document OCR task submitted: {task_id}")
        return task_id

    async def submit_remote(
        self,
        file_id: str,
        provider: str,
        conn_id: Optional[int] = None,
        remote_model: str = "",
        format: str = "md",
    ) -> str:
        """Submit a remote OCR task."""
        file_info = self._file_service.require_file(file_id)
        params = {
            "file_id": file_id, "provider": provider,
            "conn_id": conn_id, "remote_model": remote_model,
            "format": format,
        }
        task_id = await self._task_manager.submit(TASK_TYPE_DOCUMENT_OCR_REMOTE, params)
        logger.info(f"Remote OCR task submitted: {task_id} (provider={provider}, model={remote_model})")
        return task_id

    def _handle_remote_task(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        """Handle remote OCR task."""
        import base64

        file_id = params["file_id"]
        file_info = self._file_service.require_file(file_id)

        provider = params["provider"]
        conn_id = params.get("conn_id")
        remote_model = params["remote_model"]
        fmt = params.get("format", "md")
        ext = "md" if fmt == "md" else "txt"
        src_ext = Path(file_info.original_filename).suffix.lower()

        progress_callback(0.05, f"task.progress.doc_ocr_connecting|{provider}")

        prov = self._remote_service.get_provider_for_connection(conn_id, provider)
        if prov is None:
            raise RuntimeError(f"Provider not available: {provider}")

        if src_ext == ".pdf":
            # PDF: render each page to image then OCR
            final_text = self._ocr_pdf_remote(
                file_info.file_path, prov, remote_model, fmt, progress_callback,
                provider_name=provider,
            )
        elif src_ext in _IMAGE_EXTS:
            progress_callback(0.1, "task.progress.doc_ocr_prepare")
            final_text = self._recognize_remote(
                str(file_info.file_path), prov, remote_model, fmt,
                provider_name=provider,
            )
            progress_callback(0.95, "task.progress.doc_ocr_recognition_complete")
        else:
            raise ValueError("Unsupported file format; please upload a PDF or image")

        if not final_text.strip():
            final_text = "(No text detected)"

        output_file_id, output_path = self._file_service.create_output_path(
            original_filename=file_info.original_filename,
            suffix="_ocr",
            ext=f".{ext}",
        )

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(final_text)

        output_info = self._file_service.register_output(
            file_id=output_file_id, file_path=output_path, original_filename=output_path.name,
        )

        progress_callback(1.0, "task.progress.doc_ocr_complete")
        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
            "text_content": final_text,
            "text_file_id": output_file_id,
            "char_count": len(final_text),
        }

    def _recognize_remote(self, image_path: str, prov, model: str, fmt: str,
                          provider_name: str = "") -> str:
        """Recognize text in a single image using remote VLM.

        Uses the shared vision-message helpers (resize + compress + per-provider
        message shape). Fixes prior issues where PDF-page images could exceed
        4MB and where ollama/gemini providers received the wrong message shape.
        """
        from app.utils.vision_messages import (
            prepare_image_for_remote_vlm,
            build_vision_chat_messages,
            OCR_SYSTEM_MD, OCR_SYSTEM_TXT, OCR_USER_MD, OCR_USER_TXT,
        )
        from app.utils.inference import get_remote_inference_config

        image_b64, mime = prepare_image_for_remote_vlm(image_path)

        sys_prompt = OCR_SYSTEM_MD if fmt == "md" else OCR_SYSTEM_TXT
        user_prompt = OCR_USER_MD if fmt == "md" else OCR_USER_TXT

        # Fuse the system role into the user prompt so the helper (which emits
        # a single user message per provider) can carry it across all providers.
        combined_prompt = f"{sys_prompt}\n\n{user_prompt}"
        messages = build_vision_chat_messages(provider_name, combined_prompt, image_b64, mime)

        remote_config = get_remote_inference_config("ocr")
        return prov.chat(
            model=model, messages=messages,
            max_tokens=remote_config["max_tokens"],
            temperature=remote_config["temperature"],
        )

    def _ocr_pdf_remote(self, pdf_path: str, prov, model: str, fmt: str,
                        progress_callback: Callable[[float, str], None],
                        provider_name: str = "") -> str:
        """Remote OCR: render PDF pages then send to remote VLM."""
        from app.pipeline.ocr import ocr_pdf_pages

        texts = ocr_pdf_pages(
            pdf_path,
            lambda img: self._recognize_remote(img, prov, model, fmt, provider_name=provider_name),
            on_progress=lambda p, m: progress_callback(0.05 + p * 0.90, m),
        )
        return "\n\n---\n\n".join(texts)

    def _recognize(self, image_path: str, model_family: str, variant: str, fmt: str,
                   on_progress: Optional[Callable[[float, str], None]] = None) -> str:
        """Recognize text in a single image using local VLM."""
        from app.pipeline.ocr import recognize_image_local

        runtime = self._llama_runtime
        with runtime.acquire(model_family, variant, on_progress):
            return recognize_image_local(image_path, model_family, variant, fmt, runtime, on_progress)

    def _handle_task(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        file_id = params["file_id"]
        file_info = self._file_service.require_file(file_id)

        if not self._model_manager.is_llama_ready():
            raise RuntimeError("llama-server not installed; please install AI core environment in settings")

        model_family = params.get("model_family", DEFAULT_VLM_MODEL)
        size = params.get("size", "4b")
        quantization = params.get("quantization")
        fmt = params.get("format", "md")
        ext = "md" if fmt == "md" else "txt"
        src_ext = Path(file_info.original_filename).suffix.lower()

        variant = f"{size}:{quantization}" if quantization else size

        progress_callback(0.05, "task.progress.ocr_prepare")

        # === GPU queue pipeline ===
        with self._model_manager.gpu_session():
            if src_ext == ".pdf":
                final_text = self._ocr_pdf(
                    file_info.file_path, model_family, variant, fmt, progress_callback,
                )
            elif src_ext in _IMAGE_EXTS:
                final_text = self._recognize(
                    image_path=str(file_info.file_path),
                    model_family=model_family, variant=variant, fmt=fmt,
                    on_progress=lambda p, m: progress_callback(0.1 + p * 0.85, m),
                )
            else:
                raise ValueError("Unsupported file format; please upload a PDF or image")

        if not final_text.strip():
            final_text = "(No text detected)"

        output_file_id, output_path = self._file_service.create_output_path(
            original_filename=file_info.original_filename,
            suffix="_ocr",
            ext=f".{ext}",
        )
        output_path.write_text(final_text, encoding="utf-8")

        output_info = self._file_service.register_output(
            file_id=output_file_id, file_path=output_path,
            original_filename=output_path.name,
        )
        progress_callback(1.0, "task.progress.doc_ocr_complete")
        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
            "char_count": len(final_text),
        }

    def _ocr_pdf(self, src_path: Path, model_family, variant, fmt, progress_callback) -> str:
        from app.pipeline.ocr import ocr_pdf_pages

        page_results = ocr_pdf_pages(
            src_path,
            lambda img: self._recognize(
                image_path=img,
                model_family=model_family, variant=variant, fmt=fmt,
                on_progress=lambda p, m: None,
            ),
            on_progress=lambda p, m: progress_callback(0.1 + p * 0.85, m),
        )

        total = len(page_results)
        if fmt == "md":
            parts = []
            for i, text in enumerate(page_results):
                header = f"## Page {i+1}\n\n" if total > 1 else ""
                parts.append(f"{header}{text}")
            return "\n\n---\n\n".join(parts)
        return "\n\n".join(page_results)
