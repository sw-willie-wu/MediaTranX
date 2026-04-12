"""
Document OCR service.
PDF: render each page then recognize with VLM; images: recognize directly.
"""
import logging
import os
import tempfile
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from app.utils.prompts import DEFAULT_VLM_MODEL
from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_DOCUMENT_OCR = "document.ocr"
TASK_TYPE_DOCUMENT_OCR_REMOTE = "document.ocr.remote"

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif"}


class DocumentOcrService:
    """Document OCR service for PDF and images using VLM (local or remote)."""

    def __init__(self, file_service: FileService, task_manager: TaskManager):
        self._file_service = file_service
        self._task_manager = task_manager
        self._task_manager.register_handler(TASK_TYPE_DOCUMENT_OCR, self._handle_task)
        self._task_manager.register_handler(TASK_TYPE_DOCUMENT_OCR_REMOTE, self._handle_remote_task)
        logger.info("DocumentOcrService initialized")

    def get_status(self, model_family: str = DEFAULT_VLM_MODEL, size: str = "4b",
                   quantization: Optional[str] = None) -> dict:
        from app.init.container import get_container
        return get_container().language_service().get_vlm_status(model_family=model_family, size=size, quantization=quantization)

    async def submit(
        self,
        file_id: str,
        model_family: str = DEFAULT_VLM_MODEL,
        size: str = "4b",
        quantization: Optional[str] = None,
        format: str = "md",
        output_dir: Optional[str] = None,
        output_filename: Optional[str] = None,
    ) -> str:
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")
        params = {
            "file_id": file_id, "model_family": model_family,
            "size": size, "quantization": quantization,
            "format": format, "output_dir": output_dir,
            "output_filename": output_filename,
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
        output_dir: Optional[str] = None,
        output_filename: Optional[str] = None,
    ) -> str:
        """Submit a remote OCR task."""
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")
        params = {
            "file_id": file_id, "provider": provider,
            "conn_id": conn_id, "remote_model": remote_model,
            "format": format, "output_dir": output_dir,
            "output_filename": output_filename,
        }
        task_id = await self._task_manager.submit(TASK_TYPE_DOCUMENT_OCR_REMOTE, params)
        logger.info(f"Remote OCR task submitted: {task_id} (provider={provider}, model={remote_model})")
        return task_id

    def _handle_remote_task(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        """Handle remote OCR task."""
        import base64

        file_id = params["file_id"]
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        provider = params["provider"]
        conn_id = params.get("conn_id")
        remote_model = params["remote_model"]
        fmt = params.get("format", "md")
        ext = "md" if fmt == "md" else "txt"
        src_ext = Path(file_info.original_filename).suffix.lower()

        progress_callback(0.05, f"task.progress.doc_ocr_connecting|{provider}")

        from app.init.container import get_container
        remote_svc = get_container().remote_service()
        prov = remote_svc.get_provider_for_connection(conn_id, provider)
        if prov is None:
            raise RuntimeError(f"Provider not available: {provider}")

        if src_ext == ".pdf":
            # PDF: render each page to image then OCR
            final_text = self._ocr_pdf_remote(
                file_info.file_path, prov, remote_model, fmt, progress_callback,
            )
        elif src_ext in _IMAGE_EXTS:
            progress_callback(0.1, "task.progress.doc_ocr_prepare")
            final_text = self._recognize_remote(
                str(file_info.file_path), prov, remote_model, fmt,
            )
            progress_callback(0.95, "task.progress.doc_ocr_recognition_complete")
        else:
            raise ValueError("Unsupported file format; please upload a PDF or image")

        if not final_text.strip():
            final_text = "(No text detected)"

        output_file_id = str(uuid4())
        stem = Path(file_info.original_filename).stem
        custom_filename = params.get("output_filename")
        final_filename = custom_filename if custom_filename else f"{stem}_ocr_{output_file_id[:8]}.{ext}"

        output_dir = Path(params["output_dir"]) if params.get("output_dir") else self._file_service.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / final_filename

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(final_text)

        output_info = self._file_service.register_output(
            file_id=output_file_id, file_path=output_path, original_filename=final_filename,
        )

        progress_callback(1.0, "task.progress.doc_ocr_complete")
        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
            "text_content": final_text,
            "text_file_id": output_file_id,
            "char_count": len(final_text),
        }

    def _recognize_remote(self, image_path: str, prov, model: str, fmt: str) -> str:
        """Recognize text in a single image using remote VLM."""
        import base64
        from app.utils.prompts import OCR_SYSTEM_MD, OCR_SYSTEM_TXT, OCR_USER_MD, OCR_USER_TXT
        from app.utils.inference import get_remote_inference_config

        with open(image_path, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode()

        mime = "image/png" if image_path.lower().endswith(".png") else "image/jpeg"
        sys_prompt = OCR_SYSTEM_MD if fmt == "md" else OCR_SYSTEM_TXT
        user_prompt = OCR_USER_MD if fmt == "md" else OCR_USER_TXT
        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_b64}"}},
                {"type": "text", "text": user_prompt},
            ]},
        ]
        remote_config = get_remote_inference_config("ocr")
        return prov.chat(
            model=model, messages=messages,
            max_tokens=remote_config["max_tokens"],
            temperature=remote_config["temperature"],
        )

    def _ocr_pdf_remote(self, pdf_path: str, prov, model: str, fmt: str,
                        progress_callback: Callable[[float, str], None]) -> str:
        """Remote OCR: render PDF pages then send to remote VLM."""
        import pypdfium2 as pdfium

        pdf = pdfium.PdfDocument(pdf_path)
        total_pages = len(pdf)
        all_texts = []

        with tempfile.TemporaryDirectory(prefix="mediatranx_ocr_") as tmpdir:
            for page_idx in range(total_pages):
                progress_callback(
                    0.05 + (page_idx / total_pages) * 0.90,
                    f"task.progress.doc_ocr_page|{page_idx + 1}|{total_pages}"
                )
                page = pdf[page_idx]
                bitmap = page.render(scale=2)
                pil_image = bitmap.to_pil()
                img_path = os.path.join(tmpdir, f"page_{page_idx}.png")
                pil_image.save(img_path)

                text = self._recognize_remote(img_path, prov, model, fmt)
                all_texts.append(text.strip())

        pdf.close()
        return "\n\n---\n\n".join(all_texts)

    def _recognize(self, image_path: str, model_family: str, variant: str, fmt: str,
                   on_progress: Optional[Callable[[float, str], None]] = None) -> str:
        """Recognize text in a single image using local VLM."""
        from app.init.container import get_container
        from app.utils.inference import get_inference_config, calc_max_tokens, fake_progress
        from app.utils.prompts import get_prompt_builder

        variant_size = variant.split(":")[0] if ":" in variant else variant
        config = get_inference_config(model_family, variant_size, "ocr")
        builder = get_prompt_builder("ocr", config["prompt_builder"], thinking=config.get("thinking", False))
        result = builder(image_path, output_format=fmt, source_lang=None)
        max_tokens = calc_max_tokens(config, config["n_ctx"], 1000)  # ~1000 tokens for image

        runtime = get_container().llama_runtime()

        with runtime.acquire(model_family, variant, on_progress):
            with fake_progress(on_progress, 0.0, 1.0, "task.progress.ocr_recognizing", runtime=runtime):
                return runtime.chat(
                    messages=result["messages"], max_tokens=max_tokens,
                    temperature=config["temperature"],
                    top_k=config.get("top_k", 40), top_p=config.get("top_p", 0.9),
                )

    def _handle_task(self, params: dict, progress_callback: Callable[[float, str], None]) -> dict:
        file_id = params["file_id"]
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        from app.init.container import get_container
        if not get_container().model_manager().is_llama_ready():
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
        manager = get_container().model_manager()

        with manager.gpu_session():
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

        output_file_id = str(uuid4())
        stem = Path(file_info.original_filename).stem
        custom_filename = params.get("output_filename")
        final_filename = custom_filename if custom_filename else f"{stem}_ocr_{output_file_id[:8]}.{ext}"

        output_dir = Path(params["output_dir"]) if params.get("output_dir") else self._file_service.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / final_filename
        output_path.write_text(final_text, encoding="utf-8")

        output_info = self._file_service.register_output(
            file_id=output_file_id, file_path=output_path,
            original_filename=final_filename,
        )
        progress_callback(1.0, "task.progress.doc_ocr_complete")
        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
            "char_count": len(final_text),
        }

    def _ocr_pdf(self, src_path: Path, model_family, variant, fmt, progress_callback) -> str:
        import io as _io
        import pypdfium2
        doc = pypdfium2.PdfDocument(str(src_path))
        total = len(doc)
        page_results = []

        for i, page in enumerate(doc):
            progress_callback(0.1 + i / total * 0.85, f"task.progress.doc_ocr_page|{i+1}|{total}")
            bitmap = page.render(scale=2.0)
            img = bitmap.to_pil()
            img_buf = _io.BytesIO()
            img.save(img_buf, format="PNG")
            img_bytes = img_buf.getvalue()

            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                tmp.write(img_bytes)
                tmp_path = tmp.name
            try:
                text = self._recognize(
                    image_path=tmp_path,
                    model_family=model_family, variant=variant, fmt=fmt,
                    on_progress=lambda p, m: None,
                )
                page_results.append(text.strip())
            finally:
                os.unlink(tmp_path)

        doc.close()

        if fmt == "md":
            parts = []
            for i, text in enumerate(page_results):
                header = f"## Page {i+1}\n\n" if total > 1 else ""
                parts.append(f"{header}{text}")
            return "\n\n---\n\n".join(parts)
        return "\n\n".join(page_results)
