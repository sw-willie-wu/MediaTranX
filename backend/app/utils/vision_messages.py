"""VLM vision message assembly (image → base64 → chat message payload).

Handles PIL / base64 / MIME detection. PIL is lazy-imported inside
`build_ocr_messages` so module-level `from app.utils.vision_messages import ...`
does not trigger PIL during cold start (§3 audit constraint).
"""
from __future__ import annotations
import base64
import io
from pathlib import Path


# OCR prompt -- ignore visual elements
_IGNORE_VISUAL = (
    "Ignore QR codes, barcodes, logos, icons, and any purely visual/graphical elements — "
    "extract only human-readable text."
)

# OCR prompt -- plain text mode
OCR_SYSTEM_TXT = (
    "You are an OCR assistant. Extract all text from the image exactly as it appears. "
    "Output only the extracted text, preserving line breaks and layout as much as possible. "
    f"{_IGNORE_VISUAL} "
    "Do not add explanations, commentary, or any formatting markers."
)

OCR_USER_TXT = (
    "Please extract all human-readable text from this image. "
    "Output only the plain text content, nothing else."
)

# OCR prompt -- Markdown mode
OCR_SYSTEM_MD = (
    "You are an OCR assistant. Extract all text from the image and format the output in Markdown. "
    f"{_IGNORE_VISUAL} "
    "Rules:\n"
    "- If the image contains a table, represent it as a Markdown table (| col | col | with --- separator row).\n"
    "- Use # headings for titles or section headers you can identify.\n"
    "- Preserve paragraph breaks with blank lines.\n"
    "- Output only the extracted content in Markdown format, no explanations or commentary."
)

OCR_USER_MD = (
    "Please extract all human-readable text from this image and format it in Markdown. "
    "Represent any tables as Markdown tables. Output only the Markdown content."
)


_MIME_BY_EXT = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".bmp": "image/bmp",
}

# Most remote providers cap request payload around 20MB; stay well under to
# survive base64 inflation (~33%) plus prompt overhead.
_DEFAULT_MAX_BYTES = 4 * 1024 * 1024   # 4MB
_DEFAULT_MAX_DIM = 2048                 # px


def prepare_image_for_remote_vlm(
    image_path: str,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    max_dim: int = _DEFAULT_MAX_DIM,
) -> tuple[str, str]:
    """Read + optionally downscale/recompress an image for remote VLM requests.

    - Resizes (LANCZOS thumbnail) when larger than `max_dim` on the longest side.
    - Re-encodes as JPEG quality 85 when either oversized or in a lossy-incompatible
      format (PNG/BMP/TIFF); otherwise keeps the source container.
    - Returns `(base64_str, mime_type)` ready to drop into a chat message.
    """
    import base64
    from PIL import Image

    path = Path(image_path)
    img = Image.open(path)
    original_size = path.stat().st_size

    if max(img.size) > max_dim:
        img.thumbnail((max_dim, max_dim), Image.LANCZOS)

    buf = io.BytesIO()
    ext = path.suffix.lower()
    needs_recompress = original_size > max_bytes or ext in (".png", ".bmp", ".tiff", ".tif")

    if needs_recompress:
        img_rgb = img.convert("RGB") if img.mode != "RGB" else img
        img_rgb.save(buf, format="JPEG", quality=85, optimize=True)
        mime_type = "image/jpeg"
    else:
        img.save(buf, format=img.format or "JPEG")
        mime_type = _MIME_BY_EXT.get(ext, "image/jpeg")

    image_bytes = buf.getvalue()
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    return image_b64, mime_type


def read_image_raw_b64(path: str) -> tuple[str, str]:
    """Raw base64 of file bytes — no PIL roundtrip, no recompress.

    For providers (Ollama) that expect the source bytes verbatim and
    handle their own preprocessing server-side. MIME is inferred from
    file extension only (see spec §7.10 known limitation).
    """
    p = Path(path)
    suffix = p.suffix.lower()
    mime = _MIME_BY_EXT.get(suffix, "image/png")
    b64 = base64.b64encode(p.read_bytes()).decode("ascii")
    return b64, mime


def build_vision_chat_messages(
    provider: str,
    prompt: str,
    parts: list[tuple[str, str]],
) -> list[dict]:
    """Build a multi-image remote VLM chat message, dispatching per provider.

    Args:
        provider: "ollama" | "gemini" | "openai" (and unknown → openai shape).
        prompt: User prompt text (single text part).
        parts: List of (base64_str, mime_type) tuples — one per image.

    Returns:
        Messages list (single-user-message wrapping prompt + all images).

    Each remote provider expects a different shape:
    - ollama: content is a plain string; images carried as sibling 'images' list of raw b64.
    - gemini: content is a list with type='image' entries (provider's chat() converts
      to inline_data on the wire).
    - openai-compatible (default): content is a list with image_url + data: URI entries.
    """
    if provider == "ollama":
        return [{
            "role": "user",
            "content": prompt,
            "images": [b for b, _ in parts],
        }]
    if provider == "gemini":
        return [{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                *(
                    {"type": "image", "mime_type": m, "data": b}
                    for b, m in parts
                ),
            ],
        }]
    # openai-compatible (default)
    return [{
        "role": "user",
        "content": [
            {"type": "text", "text": prompt},
            *(
                {"type": "image_url",
                 "image_url": {"url": f"data:{m};base64,{b}"}}
                for b, m in parts
            ),
        ],
    }]


def build_ocr_messages(image_path: str, format: str = "md") -> list[dict]:
    """Build VLM OCR messages array (including base64 image).

    Args:
        image_path: Path to the image file
        format: "md" (Markdown) or "txt" (plain text)

    Returns:
        Messages list ready to pass to runtime.chat()
    """
    # Read image; llama-server (stb_image) does not support webp, convert to PNG
    image_bytes = Path(image_path).read_bytes()
    ext = Path(image_path).suffix.lower().lstrip(".")

    if ext == "webp":
        from PIL import Image
        img = Image.open(io.BytesIO(image_bytes))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        image_bytes = buf.getvalue()
        mime = "image/png"
    else:
        mime = {
            "jpg": "image/jpeg", "jpeg": "image/jpeg",
            "png": "image/png", "gif": "image/gif",
            "bmp": "image/bmp",
        }.get(ext, "image/jpeg")

    b64 = base64.b64encode(image_bytes).decode("ascii")
    data_url = f"data:{mime};base64,{b64}"

    sys_prompt = OCR_SYSTEM_MD if format == "md" else OCR_SYSTEM_TXT
    user_prompt = OCR_USER_MD if format == "md" else OCR_USER_TXT

    return [
        {"role": "system", "content": sys_prompt},
        {
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": data_url}},
                {"type": "text", "text": user_prompt},
            ],
        },
    ]
