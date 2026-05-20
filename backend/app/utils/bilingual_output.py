"""Bilingual-or-single output writer for translated content.

When a service produces a source file + optional target-language file (translation output),
this helper writes them, calls FileService.register_output for each, and returns the list.

Consumers: audio/transcribe, audio/lyrics, video/subtitle, document/translate.

Design notes
------------
Filename conventions differ across consumers:
  - Transcribe/lyrics/subtitle: ``{base}.{lang}.{ext}``
  - Doc translate:              ``{stem}_{target}{ext}``
So the helper accepts pre-built filenames (``source_filename`` / ``target_filename``)
rather than hard-coding a naming scheme. Callers are expected to build filenames.

Return-dict shape differs too. The helper returns a common base shape
``{file_id, filename, size, language}`` and the caller merges extra metadata
(e.g. ``"type": "source"`` for transcribe services) after the call if needed.
"""
from __future__ import annotations
import logging
from pathlib import Path
from uuid import uuid4

logger = logging.getLogger(__name__)


def write_bilingual_or_single(
    *,
    source_filename: str,
    source_text: str,
    source_lang: str,
    target_filename: str | None,
    target_text: str | None,
    target_lang: str | None,
    output_dir: Path,
    original_filename: str,
    file_service,
) -> list[dict]:
    """Write file(s) and register outputs.

    Pass ``target_filename=None`` and ``target_text=None`` for single-file mode.
    Returns list of dicts with keys: ``file_id, filename, size, language``.
    Order: source first, then target (if bilingual).

    Args:
        source_filename: pre-built filename for the source-language output.
        source_text: file body for the source-language output.
        source_lang: language tag stored in the returned dict.
        target_filename: pre-built filename for the target-language output; None = single mode.
        target_text: file body for the target output; must be None iff ``target_filename`` is None.
        target_lang: language tag for the target output.
        output_dir: directory (created if missing).
        original_filename: the uploaded file's original name (for FileService registration).
        file_service: must expose ``register_output(file_id, file_path, original_filename)``.
    """
    if (target_filename is None) != (target_text is None):
        raise ValueError(
            "target_filename and target_text must both be provided or both be None"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []

    src_id = str(uuid4())
    src_path = output_dir / source_filename
    src_path.write_text(source_text, encoding="utf-8")
    src_info = file_service.register_output(
        file_id=src_id,
        file_path=src_path,
        original_filename=original_filename,
    )
    results.append({
        "file_id": src_id,
        "filename": src_info.filename,
        "size": src_info.file_size,
        "language": source_lang,
    })

    if target_filename is not None:
        tgt_id = str(uuid4())
        tgt_path = output_dir / target_filename
        tgt_path.write_text(target_text, encoding="utf-8")
        tgt_info = file_service.register_output(
            file_id=tgt_id,
            file_path=tgt_path,
            original_filename=original_filename,
        )
        results.append({
            "file_id": tgt_id,
            "filename": tgt_info.filename,
            "size": tgt_info.file_size,
            "language": target_lang,
        })

    return results
