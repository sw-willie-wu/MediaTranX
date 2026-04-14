"""
Image OCR service.
Uses vision-language models (Qwen3-VL / InternVL2.5 / Gemma3) to recognize text in images.
"""
import logging
from pathlib import Path
from typing import Callable, Optional
from uuid import uuid4

from PIL import Image as PILImage

from app.utils.prompts import DEFAULT_VLM_MODEL
from app.services.files.file_service import FileService
from app.workers.task_manager import TaskManager

logger = logging.getLogger(__name__)

TASK_TYPE_IMAGE_OCR = "image.ocr"
TASK_TYPE_IMAGE_OCR_REMOTE = "image.ocr.remote"


class ImageOcrService:
    """Image OCR using vision-language models (local or remote)."""

    def __init__(self, file_service: FileService, task_manager: TaskManager):
        self._file_service = file_service
        self._task_manager = task_manager
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
        from app.init.container import get_container
        return get_container().language_service().get_vlm_status(model_family=model_family, size=size, quantization=quantization)

    async def submit_ocr(
        self,
        file_id: str,
        model_family: str = DEFAULT_VLM_MODEL,
        size: str = "4b",
        quantization: Optional[str] = None,
        format: str = "md",
    ) -> str:
        """Submit an OCR task."""
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

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
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

        model_family = params.get("model_family", DEFAULT_VLM_MODEL)
        size = params.get("size", "4b")
        quantization = params.get("quantization")
        fmt = params.get("format", "md")
        ext = "md" if fmt == "md" else "txt"

        progress_callback(0.05, "task.progress.ocr_prepare")

        from app.init.container import get_container
        if not get_container().model_manager().is_llama_ready():
            raise RuntimeError("llama-server not installed; please install AI core environment in settings")

        # === GPU queue pipeline ===
        manager = get_container().model_manager()

        with manager.gpu_session():
            # Execute VLM OCR
            from app.utils.inference import get_inference_config, calc_max_tokens
            from app.utils.prompts import get_prompt_builder

            variant = f"{size}:{quantization}" if quantization else size
            variant_size = variant.split(":")[0] if ":" in variant else variant
            runtime = get_container().llama_runtime()

            config = get_inference_config(model_family, variant_size, "ocr")
            builder = get_prompt_builder("ocr", config["prompt_builder"], thinking=config.get("thinking", False))
            result = builder(str(file_info.file_path), output_format=fmt, source_lang=None)
            max_tokens = calc_max_tokens(config, config["n_ctx"], 1000)  # ~1000 tokens for image

            from app.utils.inference import fake_progress

            with runtime.acquire(model_family, variant, lambda p, m: progress_callback(0.1 + p * 0.85, m)):
                with fake_progress(progress_callback, 0.95, 1.0, "task.progress.ocr_recognizing", runtime=runtime):
                    final_text = runtime.chat(
                        messages=result["messages"], max_tokens=max_tokens,
                        temperature=config["temperature"],
                        top_k=config.get("top_k", 40), top_p=config.get("top_p", 0.9),
                    )

        if not final_text.strip():
            final_text = "(No text detected)"

        # Save output file
        progress_callback(0.97, "task.progress.ocr_saving")
        output_file_id = str(uuid4())
        original_stem = Path(file_info.original_filename).stem
        final_filename = f"{original_stem}_ocr_{output_file_id[:8]}.{ext}"

        output_dir = self._file_service.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / final_filename

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(final_text)

        output_info = self._file_service.register_output(
            file_id=output_file_id,
            file_path=output_path,
            original_filename=final_filename,
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
        file_info = self._file_service.get_file(file_id)
        if file_info is None:
            raise ValueError(f"File not found: {file_id}")

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

        progress_callback(0.05, f"task.progress.connecting_provider|{provider}")

        # Get connection info
        from app.init.container import get_container
        remote_svc = get_container().remote_service()
        p = remote_svc.get_provider_for_connection(conn_id, provider)
        if p is None:
            raise RuntimeError(f"Provider not available: {provider}")

        # Read image, compress if needed (APIs typically have ~20MB payload limit)
        progress_callback(0.1, "task.progress.prepare_image")
        image_path = Path(file_info.file_path)

        MAX_SIZE_BYTES = 4 * 1024 * 1024  # 4MB (approx 5.3MB after base64 encoding)
        MAX_DIMENSION = 2048

        import io

        img = PILImage.open(image_path)
        original_size = image_path.stat().st_size

        # Resize large images
        if max(img.size) > MAX_DIMENSION:
            img.thumbnail((MAX_DIMENSION, MAX_DIMENSION), PILImage.LANCZOS)
            logger.info(f"Image resized to {img.size} for remote OCR")

        # Convert to JPEG compression (if original is too large or is PNG/BMP)
        buf = io.BytesIO()
        if original_size > MAX_SIZE_BYTES or image_path.suffix.lower() in ('.png', '.bmp', '.tiff'):
            img_rgb = img.convert('RGB') if img.mode != 'RGB' else img
            img_rgb.save(buf, format='JPEG', quality=85, optimize=True)
            mime_type = "image/jpeg"
        else:
            img.save(buf, format=img.format or 'JPEG')
            suffix = image_path.suffix.lower()
            mime_map = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".gif": "image/gif", ".webp": "image/webp"}
            mime_type = mime_map.get(suffix, "image/jpeg")

        image_b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        logger.info(f"Image prepared: {len(buf.getvalue()) / 1024:.0f}KB (base64: {len(image_b64) / 1024:.0f}KB)")

        # Build prompt
        if fmt == "md":
            prompt = "Please perform OCR on this image. Extract all text content and format it as clean Markdown. Preserve the document structure (headings, lists, tables, etc.) as much as possible. Output only the extracted text in Markdown format, no explanations."
        else:
            prompt = "Please perform OCR on this image. Extract all text content as plain text. Output only the extracted text, no explanations."

        progress_callback(0.2, "task.progress.recognizing")

        # Build vision messages per provider (different formats)
        if provider == "ollama":
            # Ollama: images field with base64 (no data: prefix)
            messages = [{"role": "user", "content": prompt, "images": [image_b64]}]
        elif provider == "gemini":
            # Gemini: inline_data format
            messages = [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image", "mime_type": mime_type, "data": image_b64},
            ]}]
        else:
            # OpenAI-compatible: image_url with data URI
            messages = [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}},
            ]}]

        from app.utils.inference import get_remote_inference_config
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
        output_file_id = str(uuid4())
        original_stem = Path(file_info.original_filename).stem
        final_filename = f"{original_stem}_ocr_{output_file_id[:8]}.{ext}"

        output_dir = self._file_service.output_dir
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / final_filename

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(final_text)

        output_info = self._file_service.register_output(
            file_id=output_file_id,
            file_path=output_path,
            original_filename=final_filename,
        )

        progress_callback(1.0, "task.progress.ocr_complete")
        return {
            "output_file_id": output_file_id,
            "output_filename": output_info.filename,
            "char_count": len(final_text),
        }
