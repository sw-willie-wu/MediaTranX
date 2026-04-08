"""
模型 Metadata 服務
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
負責列舉所有模型的狀態（下載狀態、大小、分類等），提供給 Route 層使用。
Route 不應直接 import engine.ai.registry / engine.ai.model_manager。
"""
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ─── 分類定義（前端 tab 動態產生）────────────────────────────────────────────

MODEL_CATEGORIES = [
    {"key": "image", "label": "圖像處理", "order": 0},
    {"key": "video", "label": "影片處理", "order": 1},
    {"key": "audio", "label": "語音處理", "order": 2},
    {"key": "llm", "label": "大語言模型", "order": 3},
]

# 舊分類 → 新分類的映射
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

# ─── 顯示用常數 ──────────────────────────────────────────────────────────────

_SIZE_DESC = {
    "translategemma": {
        "4b": "models.size.light_fast",
        "12b": "models.size.balanced",
        "27b": "models.size.highest",
    },
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

_GGUF_FAMILY_LABELS = {
    "translategemma": "TranslateGemma",
    "qwen3": "Qwen3",
    "qwen3vl": "Qwen3-VL",
    "internvl2.5": "InternVL2.5",
    "gemma3": "Gemma 3",
    "qwen3.5": "Qwen3.5",
}


_LANG_NAMES = {
    "en": "English", "zh": "中文", "ja": "日本語", "ko": "한국어",
    "fr": "Français", "de": "Deutsch", "es": "Español", "pt": "Português",
    "it": "Italiano", "nl": "Nederlands", "pl": "Polski", "ru": "Русский",
    "ar": "العربية", "fi": "Suomi", "hu": "Magyar", "el": "Ελληνικά",
}


class ModelMetadataService:
    """模型 Metadata 查詢服務"""

    def __init__(self):
        logger.info("ModelMetadataService initialized")

    def list_all(self) -> dict:
        """
        列舉所有模型的狀態

        Returns:
            {"categories": [...], "models": [...]}
        """
        all_models = []

        all_models.extend(self._enumerate_pth_models())
        all_models.extend(self._enumerate_whisper_models())
        all_models.extend(self._enumerate_demucs_models())
        all_models.extend(self._enumerate_gguf_models())
        all_models.extend(self._enumerate_alignment_models())
        all_models.extend(self._enumerate_rife_models())
        all_models.extend(self._enumerate_midi_models())

        # 保留原始分類作為 subcategory（前端模型篩選用），映射到大類作為 category（tab 分類用）
        for m in all_models:
            m["subcategory"] = m["category"]
            m["category"] = _CATEGORY_MAP.get(m["category"], m["category"])

        return {"categories": MODEL_CATEGORIES, "models": all_models}

    def _enumerate_pth_models(self) -> list[dict]:
        """列舉 PyTorch 模型（超解析、人臉修復、分割）"""
        from app.init.container import get_container
        from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_PTH

        manager = get_container().model_manager()
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
                label = f"{family_label} - {variant_label}" if len(variants) > 1 else family_label

                items.append({
                    "id": f"{model_family}-{variant_name}",
                    "family": model_family,
                    "variant": variant_name,
                    "category": variant_spec.get("subcategory", family_category),
                    "label": label,
                    "description": family_desc,
                    "downloaded": downloaded,
                    "size_mb": variant_spec.get("size_mb", 0),
                    "vram_mb": variant_spec.get("vram_mb", 0),
                    "max_scale": variant_spec.get("scale", 4),
                })
        return items

    def _enumerate_whisper_models(self) -> list[dict]:
        """列舉 Whisper STT 模型"""
        from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_PKG
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
            label = f"{family_label} - {variant_label}" if len(whisper_variants) > 1 else family_label

            items.append({
                "id": f"whisper-{size}",
                "family": "whisper",
                "variant": size,
                "category": family_category,
                "label": label,
                "description": spec.get("description", family_desc),
                "downloaded": downloaded,
                "size_mb": spec.get("size_mb", 0),
                "vram_mb": spec.get("vram_mb", 0),
            })
        return items

    def _enumerate_demucs_models(self) -> list[dict]:
        """列舉 Demucs 音源分離模型"""
        from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_PKG
        from app.init.configs import SETTINGS

        demucs_config = MODELS_REGISTRY.get(FORMAT_PKG, {}).get("demucs", {})
        family_label = demucs_config.get("label", "Demucs")
        family_category = demucs_config.get("category", "separate")
        family_desc = demucs_config.get("description", "")
        demucs_variants = demucs_config.get("variants", {})
        items = []

        for variant_name, variant_spec in demucs_variants.items():
            variant_label = variant_spec.get("label", variant_name)
            label = f"{family_label} - {variant_label}" if len(demucs_variants) > 1 else family_label

            checkpoints_dir = SETTINGS.path.models / "demucs" / "checkpoints"
            downloaded = (
                checkpoints_dir.exists()
                and any(f.suffix == ".th" for f in checkpoints_dir.iterdir())
            )

            items.append({
                "id": f"demucs-{variant_name}",
                "family": "demucs",
                "variant": variant_name,
                "category": family_category,
                "label": label,
                "description": family_desc,
                "downloaded": downloaded,
                "size_mb": variant_spec.get("size_mb", 0),
                "vram_mb": variant_spec.get("vram_mb", 0),
            })
        return items

    def _enumerate_gguf_models(self) -> list[dict]:
        """從 registry 動態枚舉所有 GGUF 模型（文字 + 視覺）"""
        from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_GGUF
        from app.init.configs import SETTINGS

        items = []
        gguf_models = MODELS_REGISTRY.get(FORMAT_GGUF, {})

        for model_family, config in gguf_models.items():
            family_label = _GGUF_FAMILY_LABELS.get(model_family, model_family)
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
                        "variant": f"{size}:{quant}",
                        "label": f"{family_label} {size.upper()} {quant}",
                        "description": description,
                        "category": "gguf",
                        "capabilities": capabilities,
                        "downloaded": downloaded,
                        "size_mb": total_mb,
                        "vram_mb": total_mb + size_spec.get("vram_overhead_mb", 0),
                    })
        return items

    def _enumerate_alignment_models(self) -> list[dict]:
        """列舉 Wav2Vec2 語音對齊模型"""
        from app.engine.ai.audio.wav2vec2 import LANG_MODELS
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
                "variant": lang_code,
                "category": "alignment",
                "label": f"Wav2Vec2 - {lang_name}",
                "description": f"Forced Alignment ({lang_code})",
                "downloaded": downloaded,
                "size_mb": 1200,
                "vram_mb": 1000,
            })
        return items


    def _enumerate_rife_models(self) -> list[dict]:
        """Enumerate RIFE interpolation models"""
        from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_PKG, SLOT_RIFE
        from app.init.configs import SETTINGS

        rife_config = MODELS_REGISTRY.get(FORMAT_PKG, {}).get("rife", {})
        family_label = rife_config.get("label", "RIFE")
        family_category = rife_config.get("category", "interpolate")
        family_desc = rife_config.get("description", "")
        rife_variants = rife_config.get("variants", {})
        items = []

        for variant_name, variant_spec in rife_variants.items():
            variant_label = variant_spec.get("label", variant_name)
            label = f"{family_label} - {variant_label}" if len(rife_variants) > 1 else family_label

            model_dir = SETTINGS.path.models / SLOT_RIFE
            filename = variant_spec.get("filename", "")
            downloaded = (model_dir / filename).exists()

            items.append({
                "id": f"rife-{variant_name}",
                "family": "rife",
                "variant": variant_name,
                "category": family_category,
                "label": label,
                "description": family_desc,
                "downloaded": downloaded,
                "size_mb": variant_spec.get("size_mb", 0),
                "vram_mb": variant_spec.get("vram_mb", 0),
            })
        return items

    def _enumerate_midi_models(self) -> list[dict]:
        """列舉 MIDI 相關模型。
        FluidSynth + SoundFont 已由 Electron 啟動時下載，不列入模型管理。
        basic-pitch 模型內建於套件，不需管理。"""
        return []
