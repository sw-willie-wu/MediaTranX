"""
Model metadata service.
Enumerates all model statuses (download state, size, category, etc.) for the route layer.
Routes should not import adapters.ai.registry / adapters.ai.model_manager directly.
"""
import logging
from pathlib import Path

from app.adapters.ai.model_manager import ModelManager

logger = logging.getLogger(__name__)

# --- Category definitions (dynamically generated for frontend tabs) ---

MODEL_CATEGORIES = [
    {"key": "image", "label": "models.category.image", "order": 0},
    {"key": "video", "label": "models.category.video", "order": 1},
    {"key": "audio", "label": "models.category.audio", "order": 2},
    {"key": "llm", "label": "models.category.llm", "order": 3},
]

# Legacy category -> new category mapping
_CATEGORY_MAP = {
    "upscale": "image",
    "face_restore": "image",
    "segment": "image",
    "stt": "audio",
    "separate": "audio",
    "alignment": "audio",
    "midi": "audio",
    "gguf": "llm",
    "interpolate": "video",
    "video_enhance": "video",
}

# --- Display constants ---

_SIZE_DESC = {
    "qwen3": {
        "1.7b": "models.size.ultra_light",
        "4b": "models.size.light_fast",
        "8b": "models.size.balanced",
        "14b": "models.size.high_precision",
    },
    "qwen3vl": {
        "2b": "models.size.ultra_light_ocr",
        "4b": "models.size.light_ocr_recommended",
        "8b": "models.size.high_precision_ocr",
    },
    "internvl2.5": {
        "1b": "models.size.ultra_light_ocr",
        "4b": "models.size.light_ocr_recommended",
    },
    "gemma3": {
        "4b": "models.size.light_ocr_recommended",
        "12b": "models.size.high_precision_ocr",
    },
    "qwen3.5": {
        "4b": "models.size.light_fast",
        "9b": "models.size.balanced",
        "27b": "models.size.highest",
    },
}

_QUANT_DESC = {
    "Q8_0": "models.quant.q8",
    "Q4_K_M": "models.quant.q4km",
    "Q4_K_S": "models.quant.q4ks",
    "Q3_K_L": "models.quant.q3kl",
    "Q3_K_M": "models.quant.q3km",
    "Q3_K_S": "models.quant.q3ks",
}


_LANG_NAMES = {
    "en": "English", "zh": "中文", "ja": "日本語", "ko": "한국어",
    "fr": "Français", "de": "Deutsch", "es": "Español", "pt": "Português",
    "it": "Italiano", "nl": "Nederlands", "pl": "Polski", "ru": "Русский",
    "ar": "العربية", "fi": "Suomi", "hu": "Magyar", "el": "Ελληνικά",
}


def _soundfont_downloaded() -> bool:
    """soundfont 已下載 = .version 存在且 tag 相符（比 info.exists 嚴謹）。"""
    import json
    from app.adapters.ai.registry import SOUNDFONT_VERSION_TAG
    from app.init.configs import SETTINGS

    vfile = SETTINGS.path.soundfonts / ".version"
    if not vfile.exists():
        return False
    try:
        return json.loads(vfile.read_text("utf-8")).get("tag") == SOUNDFONT_VERSION_TAG
    except Exception:
        return False


class ModelMetadataService:
    """Model metadata enumeration and download status query service."""

    def __init__(self, model_manager: ModelManager):
        self._model_manager = model_manager
        logger.info("ModelMetadataService initialized")

    def list_all(self) -> dict:
        """
        Enumerate all model statuses.

        Returns:
            {"categories": [...], "models": [...]}
        """
        all_models = []

        all_models.extend(self._enumerate_pth_models())
        all_models.extend(self._enumerate_ncnn_models())
        all_models.extend(self._enumerate_whisper_models())
        all_models.extend(self._enumerate_demucs_models())
        all_models.extend(self._enumerate_gguf_models())
        all_models.extend(self._enumerate_alignment_models())
        all_models.extend(self._enumerate_rife_models())
        all_models.extend(self._enumerate_midi_models())

        # Generate composite label from family_label + variant_label
        for m in all_models:
            fl = m.get("family_label", "")
            vl = m.get("variant_label", "")
            if not m.get("label"):
                m["label"] = f"{fl} {vl}".strip() if vl else fl

        # Keep original category as subcategory (for frontend model filtering), map to parent category (for tab classification)
        for m in all_models:
            m["subcategory"] = m["category"]
            m["category"] = _CATEGORY_MAP.get(m["category"], m["category"])

        return {"categories": MODEL_CATEGORIES, "models": all_models}

    def _enumerate_pth_models(self) -> list[dict]:
        """Enumerate PyTorch models (super-resolution, face restoration, segmentation).

        realesrgan/waifu2x were migrated to FORMAT_NCNN and their PTH entries
        deleted in T11, so the old PTH-shadow guard (skip families also in the
        NCNN tree) is no longer needed — no PTH family is dual-listed.
        """
        from app.adapters.ai.registry import MODELS_REGISTRY, FORMAT_PTH

        manager = self._model_manager
        items = []
        pth_models = MODELS_REGISTRY.get(FORMAT_PTH, {})

        for model_family, config in pth_models.items():
            family_label = config.get("label", model_family)
            family_category = config.get("category", "upscale")
            family_desc = config.get("description", "")

            variants = config.get("variants", {})
            for variant_name, variant_spec in variants.items():
                model_path = manager.get_model_path(model_family, variant_name)
                downloaded = model_path is not None and model_path.exists()

                variant_label = variant_spec.get("label", variant_name)

                items.append({
                    "id": f"{model_family}-{variant_name}",
                    "family": model_family,
                    "family_label": family_label,
                    "variant": variant_name,
                    "variant_label": variant_label,
                    "category": variant_spec.get("subcategory", family_category),
                    "description": family_desc,
                    "downloaded": downloaded,
                    "size_mb": variant_spec.get("size_mb", 0),
                    "vram_mb": variant_spec.get("vram_mb", 0),
                    "max_scale": variant_spec.get("scale", 4),
                })
        return items

    def _enumerate_ncnn_models(self) -> list[dict]:
        """Enumerate ncnn-vulkan SR models (FORMAT_NCNN).

        Emits the SAME item shape as `_enumerate_pth_models` (label/subcategory
        are synthesized later in `list_all`) for the SR families migrated to NCNN
        (realesrgan/waifu2x). `downloaded` is a
        direct filesystem check that every file of the .param+.bin pair exists
        under its on-disk dir (ncnn_variant_dir, nested under cli_model_subdir
        for waifu2x) — NOT via `get_model_path` (which the wrapper owns).
        """
        from app.adapters.ai.registry import (
            MODELS_REGISTRY, FORMAT_NCNN, ncnn_variant_dir,
        )
        from app.init.configs import SETTINGS

        items = []
        ncnn_models = MODELS_REGISTRY.get(FORMAT_NCNN, {})
        models_dir = SETTINGS.path.models

        for model_family, config in ncnn_models.items():
            family_label = config.get("label", model_family)
            family_category = config.get("category", "upscale")
            family_desc = config.get("description", "")
            slot = config.get("slot", "")

            for variant_name, variant_spec in config.get("variants", {}).items():
                variant_label = variant_spec.get("label", variant_name)
                files = variant_spec.get("files", [])
                vdir = ncnn_variant_dir(models_dir, slot, variant_spec)
                downloaded = bool(files) and all((vdir / f).exists() for f in files)

                items.append({
                    "id": f"{model_family}-{variant_name}",
                    "family": model_family,
                    "family_label": family_label,
                    "variant": variant_name,
                    "variant_label": variant_label,
                    "category": variant_spec.get("subcategory", family_category),
                    "description": family_desc,
                    "downloaded": downloaded,
                    "size_mb": variant_spec.get("size_mb", 0),
                    "vram_mb": variant_spec.get("vram_mb", 0),
                    "max_scale": variant_spec.get("scale", 4),
                })
        return items

    def _enumerate_whisper_models(self) -> list[dict]:
        """Enumerate Whisper STT models."""
        from app.adapters.ai.registry import MODELS_REGISTRY, FORMAT_PKG
        from app.init.configs import SETTINGS

        whisper_config = MODELS_REGISTRY.get(FORMAT_PKG, {}).get("whisper", {})
        family_label = whisper_config.get("label", "Whisper")
        family_category = whisper_config.get("category", "stt")
        family_desc = whisper_config.get("description", "")
        whisper_variants = whisper_config.get("variants", {})
        whisper_dir = SETTINGS.path.models / "whisper"
        items = []

        for size, spec in whisper_variants.items():
            model_dir = whisper_dir / size
            has_vocab = (model_dir / "vocabulary.txt").exists() or (model_dir / "vocabulary.json").exists()
            downloaded = model_dir.exists() and (model_dir / "model.bin").exists() and has_vocab

            variant_label = spec.get("label", size)

            items.append({
                "id": f"whisper-{size}",
                "family": "whisper",
                "family_label": family_label,
                "variant": size,
                "variant_label": variant_label,
                "category": family_category,
                "description": spec.get("description", family_desc),
                "downloaded": downloaded,
                "size_mb": spec.get("size_mb", 0),
                "vram_mb": spec.get("vram_mb", 0),
            })
        return items

    def _enumerate_demucs_models(self) -> list[dict]:
        """Enumerate Demucs audio source separation models."""
        from app.adapters.ai.registry import MODELS_REGISTRY, FORMAT_PKG
        from app.init.configs import SETTINGS

        demucs_config = MODELS_REGISTRY.get(FORMAT_PKG, {}).get("demucs", {})
        family_label = demucs_config.get("label", "Demucs")
        family_category = demucs_config.get("category", "separate")
        family_desc = demucs_config.get("description", "")
        demucs_variants = demucs_config.get("variants", {})
        items = []

        for variant_name, variant_spec in demucs_variants.items():
            variant_label = variant_spec.get("label", variant_name)

            checkpoints_dir = SETTINGS.path.models / "demucs" / "checkpoints"
            downloaded = (
                checkpoints_dir.exists()
                and any(f.suffix == ".th" for f in checkpoints_dir.iterdir())
            )

            items.append({
                "id": f"demucs-{variant_name}",
                "family": "demucs",
                "family_label": family_label,
                "variant": variant_name,
                "variant_label": variant_label,
                "category": family_category,
                "description": family_desc,
                "downloaded": downloaded,
                "size_mb": variant_spec.get("size_mb", 0),
                "vram_mb": variant_spec.get("vram_mb", 0),
            })
        return items

    def _enumerate_gguf_models(self) -> list[dict]:
        """Dynamically enumerate all GGUF models (text + vision) from registry."""
        from app.adapters.ai.registry import MODELS_REGISTRY, FORMAT_GGUF
        from app.init.configs import SETTINGS

        items = []
        gguf_models = MODELS_REGISTRY.get(FORMAT_GGUF, {})

        for model_family, config in gguf_models.items():
            family_label = config.get("label", model_family)
            capabilities = config.get("capabilities", ["text"])
            target_dir = SETTINGS.path.models / model_family
            specs = config.get("specs", {})

            for size, size_spec in specs.items():
                variants = size_spec.get("variants", {})
                for quant, quant_spec in variants.items():
                    # Check download status
                    main_path = target_dir / quant_spec["filename"]
                    has_mmproj = "mmproj_filename" in quant_spec
                    if has_mmproj:
                        mmproj_path = target_dir / quant_spec["mmproj_filename"]
                        downloaded = main_path.exists() and mmproj_path.exists()
                    else:
                        downloaded = main_path.exists()

                    total_mb = quant_spec.get("size_mb", 0) + quant_spec.get("mmproj_size_mb", 0)
                    size_desc = _SIZE_DESC.get(model_family, {}).get(size, "")
                    quant_desc = _QUANT_DESC.get(quant, "")
                    description = f"{size_desc}||{quant_desc}" if size_desc and quant_desc else (size_desc or quant_desc)

                    items.append({
                        "id": f"{model_family}-{size}-{quant}",
                        "family": model_family,
                        "family_label": family_label,
                        "variant": f"{size}:{quant}",
                        "variant_label": f"{size.upper()} {quant}",
                        "description": description,
                        "category": "gguf",
                        "capabilities": capabilities,
                        "downloaded": downloaded,
                        "size_mb": total_mb,
                        "vram_mb": total_mb + size_spec.get("vram_overhead_mb", 0),
                        "n_ctx_default": size_spec.get("n_ctx_default", 4096),
                        "n_ctx_min": size_spec.get("n_ctx_min", 2048),
                        "n_ctx_max": size_spec.get("n_ctx_max", 8192),
                    })
        return items

    def _enumerate_alignment_models(self) -> list[dict]:
        """Enumerate Wav2Vec2 speech alignment models."""
        from app.adapters.ai.wrapper.wav2vec2 import LANG_MODELS
        from app.init.configs import SETTINGS

        align_dir = SETTINGS.path.models / "alignment"
        items = []

        for lang_code, repo_id in LANG_MODELS.items():
            model_name = repo_id.replace("/", "--")
            model_cache = align_dir / f"models--{model_name}"
            downloaded = model_cache.exists() and (model_cache / "snapshots").exists()

            lang_name = _LANG_NAMES.get(lang_code, lang_code)
            items.append({
                "id": f"alignment-{lang_code}",
                "family": "alignment",
                "family_label": "Wav2Vec2",
                "variant": lang_code,
                "variant_label": lang_name,
                "category": "alignment",
                "description": f"models.alignment||{lang_code}",
                "downloaded": downloaded,
                "size_mb": 1200,
                "vram_mb": 1000,
            })
        return items


    def _enumerate_rife_models(self) -> list[dict]:
        """Enumerate RIFE interpolation models"""
        from app.adapters.ai.registry import MODELS_REGISTRY, FORMAT_PKG, SLOT_RIFE
        from app.init.configs import SETTINGS

        rife_config = MODELS_REGISTRY.get(FORMAT_PKG, {}).get("rife", {})
        family_label = rife_config.get("label", "RIFE")
        family_category = rife_config.get("category", "interpolate")
        family_desc = rife_config.get("description", "")
        rife_variants = rife_config.get("variants", {})
        items = []

        for variant_name, variant_spec in rife_variants.items():
            variant_label = variant_spec.get("label", variant_name)

            model_dir = SETTINGS.path.models / SLOT_RIFE
            filename = variant_spec.get("filename", "")
            downloaded = (model_dir / filename).exists()

            items.append({
                "id": f"rife-{variant_name}",
                "family": "rife",
                "family_label": family_label,
                "variant": variant_name,
                "variant_label": variant_label,
                "category": family_category,
                "description": family_desc,
                "downloaded": downloaded,
                "size_mb": variant_spec.get("size_mb", 0),
                "vram_mb": variant_spec.get("vram_mb", 0),
            })
        return items

    def _enumerate_midi_models(self) -> list[dict]:
        """Enumerate the MusyngKite soundfont as a manageable audio model.

        soundfont 從 Electron 啟動下載改為後端管理；basic-pitch 仍內建、不列舉。
        """
        from app.adapters.ai.registry import SOUNDFONT_ID, SOUNDFONT_LABEL, SOUNDFONT_SIZE_MB

        return [{
            "id": SOUNDFONT_ID,
            "family": "soundfont",
            "family_label": SOUNDFONT_LABEL,
            "variant": "musyngkite",
            "variant_label": "",
            "category": "midi",
            "description": "models.soundfont",
            "downloaded": _soundfont_downloaded(),
            "size_mb": SOUNDFONT_SIZE_MB,
            "vram_mb": 0,
        }]
