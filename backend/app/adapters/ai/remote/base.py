"""
Remote Provider abstract base.
Shared interface for all external API providers (Ollama, OpenAI, Gemini).
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, ClassVar, Literal, Optional

logger = logging.getLogger(__name__)

ImagePrepMode = Literal["raw", "recompress"]


@dataclass
class RemoteModel:
    """Remote model information."""
    id: str
    name: str
    size: Optional[int] = None
    family: Optional[str] = None
    parameter_size: Optional[str] = None
    quantization: Optional[str] = None
    capabilities: list[str] = None

    def __post_init__(self):
        if self.capabilities is None:
            self.capabilities = ["text"]


class RemoteProvider(ABC):
    """
    Remote API Provider abstract interface.

    Subclasses MUST declare both:
    - PROVIDER_NAME: "ollama" | "openai" | "gemini" | ...
        Used by build_vision_chat_messages dispatch in the chat_with_images
        default impl.
    - IMAGE_PREP_MODE: "raw" | "recompress"
        Whether multimodal images go through PIL recompress/downscale
        (recompress) or are sent byte-for-byte (raw). Ollama uses raw to
        preserve the existing wire format; OpenAI / Gemini use recompress
        because their inline payload limits are stricter.

    Enforcement: __init_subclass__ raises TypeError at class-creation
    time if either ClassVar is missing or invalid.

    Inheritance semantics: a deeper subclass that doesn't redeclare a
    ClassVar inherits the parent's value via standard Python attribute
    lookup (`getattr(cls, ...)`). Only re-declare when changing identity.
    """

    PROVIDER_NAME: ClassVar[str]
    IMAGE_PREP_MODE: ClassVar[ImagePrepMode]

    def __init_subclass__(cls, **kw):
        super().__init_subclass__(**kw)
        name = getattr(cls, "PROVIDER_NAME", None)
        if not name or not isinstance(name, str):
            raise TypeError(
                f"{cls.__name__} must declare PROVIDER_NAME ClassVar "
                f"(non-empty str)"
            )
        mode = getattr(cls, "IMAGE_PREP_MODE", None)
        if mode not in ("raw", "recompress"):
            raise TypeError(
                f"{cls.__name__} must declare IMAGE_PREP_MODE ClassVar "
                f"='raw' or 'recompress' (got {mode!r})"
            )

    def __init__(self, endpoint: str, api_key: Optional[str] = None):
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key

    @abstractmethod
    def connect(self) -> bool:
        """Verify connection is working."""
        ...

    @abstractmethod
    def list_models(self) -> list[RemoteModel]:
        """List all available models."""
        ...

    @abstractmethod
    def chat(
        self,
        model: str,
        messages: list[dict],
        *,
        max_tokens: int = 2048,
        temperature: float = 0.1,
        abort_hook: Optional[Callable] = None,
    ) -> str:
        """Text conversation.

        Args:
            model: Model ID.
            messages: list of {"role": "...", "content": ...} dicts.
            max_tokens: Maximum response token count.
            temperature: Temperature.
            abort_hook: Optional callable invoked exactly once with the
                live HTTP response object immediately after the socket is
                opened. Used by RemoteChatSession to stash the response
                for cross-thread close (cancel). If None, the provider
                may use a faster blocking code path.

        Returns:
            Model response text.
        """
        ...

    def chat_with_images(
        self,
        model: str,
        prompt: str,
        images: list[Path | str],
        *,
        max_tokens: int = 4096,
        temperature: float = 0.7,
        abort_hook: Optional[Callable] = None,
    ) -> str:
        """Multimodal chat — default implementation usable by all subclasses.

        Per-provider variation collapsed into IMAGE_PREP_MODE (raw vs PIL
        recompress) + PROVIDER_NAME (message shape via
        build_vision_chat_messages). No subclass overrides this in the
        current phase; if a future provider needs custom handling, prefer
        adding a new IMAGE_PREP_MODE value or a build_vision_chat_messages
        dispatch arm before reaching for an override.
        """
        # Lazy import — avoids forcing utils onto the cold-start path for
        # local-only users who never call chat_with_images.
        from app.utils.vision_messages import (
            prepare_image_for_remote_vlm,
            read_image_raw_b64,
            build_vision_chat_messages,
        )
        parts: list[tuple[str, str]] = []
        for img in images:
            if self.IMAGE_PREP_MODE == "raw":
                b64, mime = read_image_raw_b64(str(img))
            else:
                b64, mime = prepare_image_for_remote_vlm(str(img))
            parts.append((b64, mime))
        messages = build_vision_chat_messages(self.PROVIDER_NAME, prompt, parts)
        return self.chat(
            model=model, messages=messages,
            max_tokens=max_tokens, temperature=temperature,
            abort_hook=abort_hook,
        )

    def is_available(self) -> bool:
        """Check if provider is available (defaults to calling connect)."""
        try:
            return self.connect()
        except Exception:
            return False
