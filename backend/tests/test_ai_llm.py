"""Integration tests for LLM/VLM inference via llama-server.

Requires: llama-server binary + downloaded GGUF/VLM model.
Run: pytest -m ai
"""
import pytest

pytestmark = pytest.mark.ai


def _model_exists(model_id: str, variant: str) -> bool:
    """Check if a local GGUF model is downloaded."""
    try:
        from app.init.container import init_container
        mm = init_container().model_manager()
        return mm.get_model_path(model_id, variant) is not None
    except Exception:
        return False


def _llama_ready() -> bool:
    try:
        from app.init.container import init_container
        mm = init_container().model_manager()
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
    """LLM slot is shared ('llm'); mm.acquire is a context manager.

    Use the locally-downloaded model (Qwen3 8B Q4_K_M) — adjust the constant
    below if a different model is preferred for CI.
    """
    MODEL_ID = "qwen3"
    VARIANT = "8b:Q4_K_M"

    def test_simple_chat(self):
        if not _llama_ready():
            pytest.skip("llama-server not available")
        if not _model_exists(self.MODEL_ID, self.VARIANT):
            pytest.skip(f"{self.MODEL_ID} {self.VARIANT} model not downloaded")

        from app.init.container import init_container
        mm = init_container().model_manager()

        with mm.acquire(slot="llm", model_id=self.MODEL_ID, variant=self.VARIANT) as runtime:
            response = runtime.chat(
                messages=[{"role": "user", "content": "Say hello in one word."}],
                max_tokens=10,
                temperature=0.0,
            )
        assert isinstance(response, str)
        assert len(response) > 0


class TestVLMInference:
    """VLM uses the same 'llm' slot (only one loaded at a time). Use locally-
    downloaded Qwen3-VL 8B Q4_K_M."""
    MODEL_ID = "qwen3vl"
    VARIANT = "8b:Q4_K_M"

    def test_vlm_describe_image(self):
        if not _llama_ready():
            pytest.skip("llama-server not available")
        if not _model_exists(self.MODEL_ID, self.VARIANT):
            pytest.skip(f"{self.MODEL_ID} {self.VARIANT} model not downloaded")

        from PIL import Image
        from app.init.container import init_container
        import base64
        import io

        mm = init_container().model_manager()
        with mm.acquire(slot="llm", model_id=self.MODEL_ID, variant=self.VARIANT) as runtime:
            # Create a simple red test image
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
