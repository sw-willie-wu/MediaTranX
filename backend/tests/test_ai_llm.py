"""Integration tests for LLM/VLM inference via llama-server.

Requires: llama-server binary + downloaded GGUF/VLM model.
Run: pytest -m ai
"""
import pytest
from pathlib import Path

pytestmark = pytest.mark.ai


def _model_exists(model_id: str, variant: str) -> bool:
    """Check if a local model is downloaded."""
    try:
        from app.init.container import get_container
        mm = get_container().model_manager()
        return mm.get_model_path(model_id, variant) is not None
    except Exception:
        return False


def _llama_ready() -> bool:
    try:
        from app.init.container import get_container
        mm = get_container().model_manager()
        return mm.is_llama_ready()
    except Exception:
        return False


class TestLlamaServerAvailability:
    def test_llama_binary_check(self):
        # Don't go through get_container() — that depends on init_container()
        # having run earlier in the session (test-order coupling). Just spin a
        # fresh ModelManager; is_llama_ready() is a self-contained check.
        from app.adapters.ai.model_manager import ModelManager
        mm = ModelManager()
        assert isinstance(mm.is_llama_ready(), bool)


class TestLLMInference:
    def test_simple_chat(self):
        if not _llama_ready():
            pytest.skip("llama-server not available")
        if not _model_exists("qwen3", "4b:Q4_K_M"):
            pytest.skip("Qwen3 4B model not downloaded")

        from app.init.container import get_container
        mm = get_container().model_manager()

        runtime = mm.acquire("qwen3", "4b:Q4_K_M")
        try:
            response = runtime.chat(
                messages=[{"role": "user", "content": "Say hello in one word."}],
                max_tokens=10,
                temperature=0.0,
            )
            assert isinstance(response, str)
            assert len(response) > 0
        finally:
            mm.release("qwen3")


class TestVLMInference:
    def test_vlm_describe_image(self):
        if not _llama_ready():
            pytest.skip("llama-server not available")
        if not _model_exists("qwen3vl", "4b:Q4_K_M"):
            pytest.skip("Qwen3-VL model not downloaded")

        from PIL import Image
        from app.init.container import get_container
        import base64
        import io

        mm = get_container().model_manager()
        runtime = mm.acquire("qwen3vl", "4b:Q4_K_M")
        try:
            # Create a simple test image
            img = Image.new("RGB", (64, 64), color=(255, 0, 0))
            buf = io.BytesIO()
            img.save(buf, format="PNG")
            img_b64 = base64.b64encode(buf.getvalue()).decode()

            response = runtime.chat(
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{img_b64}"}},
                        {"type": "text", "text": "What color is this image? Answer in one word."},
                    ],
                }],
                max_tokens=10,
                temperature=0.0,
            )
            assert isinstance(response, str)
            assert len(response) > 0
        finally:
            mm.release("qwen3vl")
