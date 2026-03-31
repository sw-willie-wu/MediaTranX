"""
模型 Metadata 服務
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
負責列舉所有模型的狀態（下載狀態、大小、分類等），提供給 Route 層使用。
Route 不應直接 import engine.ai.registry / engine.ai.model_manager。
"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ─── 分類定義（前端 tab 動態產生）────────────────────────────────────────────

MODEL_CATEGORIES = [
    {"key": "image", "label": "影像處理", "order": 0},
    {"key": "audio", "label": "語音處理", "order": 1},
    {"key": "llm", "label": "大語言模型", "order": 2},
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
    "translate": "llm",
    "vlm": "llm",
}

# ─── 顯示用常數 ──────────────────────────────────────────────────────────────

_WHISPER_DISPLAY = [
    ("tiny", "Whisper Tiny", "極速語音辨識"),
    ("base", "Whisper Base", "快速語音辨識"),
    ("small", "Whisper Small", "輕量語音辨識"),
    ("medium", "Whisper Medium", "平衡精度與速度"),
    ("large-v3", "Whisper Large-v3", "最高精度語音辨識"),
]

_SIZE_DESC = {
    "translategemma": {
        "4b": "輕量，速度快",
        "12b": "平衡精度與速度",
        "27b": "最高翻譯精度",
    },
    "qwen3": {
        "1.7b": "超輕量，速度極快",
        "4b": "輕量，速度快",
        "8b": "平衡精度與速度",
        "14b": "高精度翻譯",
    },
    "qwen3vl": {
        "2b": "超輕量 OCR",
        "4b": "輕量 OCR（推薦）",
        "8b": "高精度 OCR",
    },
    "internvl2.5": {
        "1b": "超輕量 OCR",
        "4b": "輕量 OCR（推薦）",
    },
    "gemma3": {
        "4b": "輕量 OCR（推薦）",
        "12b": "高精度 OCR",
    },
}

_QUANT_DESC = {
    "Q8_0": "高精度量化",
    "Q4_K_M": "標準量化",
    "Q4_K_S": "標準量化，略省 VRAM",
    "Q3_K_L": "輕量量化",
    "Q3_K_M": "輕量量化，省 VRAM",
    "Q3_K_S": "輕量量化，最省 VRAM",
}

_VLM_FAMILY_LABELS = {
    "qwen3vl": "Qwen3-VL",
    "internvl2.5": "InternVL2.5",
    "gemma3": "Gemma 3",
}

_UPSCALE_LABELS = {
    "realesrgan": {"label": "Real-ESRGAN", "description": "通用超解析（寫實）"},
    "swinir": {"label": "SwinIR", "description": "Transformer 超解析"},
    "bsrgan": {"label": "BSRGAN", "description": "盲超解析"},
    "real-cugan": {"label": "Real-CUGAN", "description": "動漫風格超解析"},
    "waifu2x": {"label": "Waifu2x", "description": "經典動漫超解析"},
}

_FACE_RESTORE_LABELS = {
    "codeformer": {"label": "CodeFormer", "description": "VQ-GAN 人臉修復"},
    "gfpgan": {"label": "GFPGAN", "description": "GAN 人臉修復"},
}

_SEGMENT_LABELS = {
    "mobilesam": {"label": "MobileSAM", "description": "輕量物件分割（AI 移除用）"},
}

_SEPARATE_LABELS = {
    "demucs": {"label": "HTDemucs", "description": "音源分離（人聲/鼓/貝斯/吉他/鋼琴/其他）"},
}

_VARIANT_DESC = {
    "x2plus": "2x",
    "x4plus": "4x",
    "x4plus-anime": "4x - anime",
    "lightweight-x4": "4x - lightweight",
    "classical-x4": "4x - classical",
    "realworld-x4": "4x - realworld",
    "default": "標準",
    "up2x-conservative": "2x - conservative",
    "up3x-conservative": "3x - conservative",
    "up4x-conservative": "4x - conservative",
    "cunet": "CUnet 變體",
    "v1.4": "v1.4",
    "htdemucs_6s": "6-Stem",
}

_LANG_NAMES = {
    "en": "English", "zh": "中文", "ja": "日本語", "ko": "한국어",
    "fr": "Français", "de": "Deutsch", "es": "Español", "pt": "Português",
    "it": "Italiano", "nl": "Nederlands", "pl": "Polski", "ru": "Русский",
    "ar": "العربية", "fi": "Suomi", "hu": "Magyar", "el": "Ελληνικά",
}


class ModelMetadataService:
    """模型 Metadata 查詢服務（單例）"""

    _instance: Optional["ModelMetadataService"] = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._initialized = True
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
        all_models.extend(self._enumerate_translate_models())
        all_models.extend(self._enumerate_vlm_models())
        all_models.extend(self._enumerate_alignment_models())
        all_models.extend(self._enumerate_midi_models())

        # 保留原始分類作為 subcategory（前端模型篩選用），映射到大類作為 category（tab 分類用）
        for m in all_models:
            m["subcategory"] = m["category"]
            m["category"] = _CATEGORY_MAP.get(m["category"], m["category"])

        return {"categories": MODEL_CATEGORIES, "models": all_models}

    def _enumerate_pth_models(self) -> list[dict]:
        """列舉 PyTorch 模型（超解析、人臉修復、分割）"""
        from app.engine.ai.model_manager import get_model_manager
        from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_PTH

        manager = get_model_manager()
        items = []
        pth_models = MODELS_REGISTRY.get(FORMAT_PTH, {})

        for model_family, config in pth_models.items():
            if model_family in _UPSCALE_LABELS:
                category = "upscale"
                family_meta = _UPSCALE_LABELS[model_family]
            elif model_family in _FACE_RESTORE_LABELS:
                category = "face_restore"
                family_meta = _FACE_RESTORE_LABELS[model_family]
            elif model_family in _SEGMENT_LABELS:
                category = "segment"
                family_meta = _SEGMENT_LABELS[model_family]
            elif model_family in _SEPARATE_LABELS:
                category = "separate"
                family_meta = _SEPARATE_LABELS[model_family]
            else:
                continue

            variants = config.get("variants", {})
            for variant_name, variant_spec in variants.items():
                model_path = manager.get_model_path(model_family, variant_name)
                downloaded = model_path is not None and model_path.exists()

                variant_desc = _VARIANT_DESC.get(variant_name, variant_name)
                label = f"{family_meta['label']} - {variant_desc}" if len(variants) > 1 else family_meta['label']

                items.append({
                    "id": f"{model_family}-{variant_name}",
                    "family": model_family,
                    "variant": variant_name,
                    "category": category,
                    "label": label,
                    "description": family_meta["description"],
                    "downloaded": downloaded,
                    "size_mb": variant_spec.get("size_mb", 0),
                    "vram_mb": variant_spec.get("vram_mb", 0),
                    "max_scale": variant_spec.get("scale", 4),
                })
        return items

    def _enumerate_whisper_models(self) -> list[dict]:
        """列舉 Whisper STT 模型"""
        from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_PKG
        from app.engine.paths import get_models_dir

        whisper_variants = MODELS_REGISTRY.get(FORMAT_PKG, {}).get("whisper", {}).get("variants", {})
        whisper_dir = get_models_dir("whisper")
        items = []

        for size, label, description in _WHISPER_DISPLAY:
            model_dir = whisper_dir / size
            has_vocab = (model_dir / "vocabulary.txt").exists() or (model_dir / "vocabulary.json").exists()
            downloaded = model_dir.exists() and (model_dir / "model.bin").exists() and has_vocab
            spec = whisper_variants.get(size, {})
            items.append({
                "id": f"whisper-{size}",
                "family": "whisper",
                "variant": size,
                "category": "stt",
                "label": label,
                "description": description,
                "downloaded": downloaded,
                "size_mb": spec.get("size_mb", 0),
                "vram_mb": spec.get("vram_mb", 0),
            })
        return items

    def _enumerate_demucs_models(self) -> list[dict]:
        """列舉 Demucs 音源分離模型"""
        from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_PKG
        from app.engine.paths import get_models_dir

        demucs_config = MODELS_REGISTRY.get(FORMAT_PKG, {}).get("demucs", {})
        demucs_variants = demucs_config.get("variants", {})
        items = []

        for variant_name, variant_spec in demucs_variants.items():
            family_meta = _SEPARATE_LABELS.get("demucs", {"label": "Demucs", "description": ""})
            variant_desc = _VARIANT_DESC.get(variant_name, variant_name)
            label = f"{family_meta['label']} - {variant_desc}" if len(demucs_variants) > 1 else family_meta['label']

            checkpoints_dir = get_models_dir() / "demucs" / "checkpoints"
            downloaded = (
                checkpoints_dir.exists()
                and any(f.suffix == ".th" for f in checkpoints_dir.iterdir())
            )

            items.append({
                "id": f"demucs-{variant_name}",
                "family": "demucs",
                "variant": variant_name,
                "category": "separate",
                "label": label,
                "description": family_meta["description"],
                "downloaded": downloaded,
                "size_mb": variant_spec.get("size_mb", 0),
                "vram_mb": variant_spec.get("vram_mb", 0),
            })
        return items

    def _enumerate_translate_models(self) -> list[dict]:
        """從 registry 動態枚舉所有翻譯模型"""
        from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_GGUF
        from app.engine.paths import get_models_dir

        items = []
        gguf_models = MODELS_REGISTRY.get(FORMAT_GGUF, {})

        for model_family, config in gguf_models.items():
            if model_family not in ["translategemma", "qwen3"]:
                continue

            name_prefix = "TranslateGemma" if model_family == "translategemma" else "Qwen3"
            target_dir = get_models_dir(model_family)
            specs = config.get("specs", {})

            for size, size_spec in specs.items():
                variants = size_spec.get("variants", {})
                for quant, quant_spec in variants.items():
                    model_path = target_dir / quant_spec["filename"]

                    size_desc = _SIZE_DESC.get(model_family, {}).get(size, "")
                    quant_desc = _QUANT_DESC.get(quant, "")
                    description = f"{size_desc} · {quant_desc}" if size_desc and quant_desc else (size_desc or quant_desc)

                    items.append({
                        "id": f"{model_family}-{size}-{quant}",
                        "family": model_family,
                        "variant": f"{size}-{quant}",
                        "label": f"{name_prefix} {size.upper()} {quant}",
                        "description": description,
                        "category": "translate",
                        "downloaded": model_path.exists(),
                        "size_mb": quant_spec.get("size_mb", 0),
                        "vram_mb": quant_spec.get("size_mb", 0) + size_spec.get("vram_overhead_mb", 0),
                    })
        return items

    def _enumerate_vlm_models(self) -> list[dict]:
        """從 registry 動態枚舉所有 VLM OCR 模型"""
        from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_VLM
        from app.engine.paths import get_models_dir

        items = []
        vlm_models = MODELS_REGISTRY.get(FORMAT_VLM, {})

        for model_family, config in vlm_models.items():
            slot = config.get("slot", "vlm")
            target_dir = get_models_dir() / slot
            specs = config.get("specs", {})
            family_label = _VLM_FAMILY_LABELS.get(model_family, model_family)

            for size, size_spec in specs.items():
                variants = size_spec.get("variants", {})
                for quant, quant_spec in variants.items():
                    main_path = target_dir / quant_spec["filename"]
                    mmproj_path = target_dir / quant_spec.get("mmproj_filename", "")
                    downloaded = main_path.exists() and (
                        not quant_spec.get("mmproj_filename") or mmproj_path.exists()
                    )
                    total_mb = quant_spec.get("size_mb", 0) + quant_spec.get("mmproj_size_mb", 0)
                    quant_desc = _QUANT_DESC.get(quant, quant)
                    items.append({
                        "id": f"{model_family}-{size}-{quant}",
                        "family": model_family,
                        "variant": f"{size}:{quant}",
                        "label": f"{family_label} {size.upper()} {quant}",
                        "description": f"{_SIZE_DESC.get(model_family, {}).get(size, '')} · {quant_desc}",
                        "category": "vlm",
                        "downloaded": downloaded,
                        "size_mb": total_mb,
                        "vram_mb": total_mb + size_spec.get("vram_overhead_mb", 0),
                    })
        return items

    def _enumerate_alignment_models(self) -> list[dict]:
        """列舉 Wav2Vec2 語音對齊模型"""
        from app.engine.ai.audio.wav2vec2 import LANG_MODELS
        from app.engine.paths import get_models_dir

        align_dir = get_models_dir("alignment")
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


    def _enumerate_midi_models(self) -> list[dict]:
        """列舉 MIDI 相關模型（FluidSynth SoundFont）"""
        items = []

        # FluidSynth + SoundFont（basic-pitch 模型內建於套件，不需管理）
        import sys
        import shutil
        from app.engine.paths import get_fluidsynth_dir
        fs_dir = get_fluidsynth_dir()
        sf2_ok = (fs_dir / "FluidR3_GM.sf2").exists()
        if sys.platform == "win32":
            dll_ok = (fs_dir / "libfluidsynth-3.dll").exists() and (fs_dir / "libglib-2.0-0.dll").exists()
        else:
            dll_ok = shutil.which("fluidsynth") is not None

        items.append({
            "id": "fluidsynth",
            "family": "fluidsynth",
            "variant": "default",
            "category": "midi",
            "label": "FluidR3 GM SoundFont",
            "description": "MIDI 音色合成引擎 + GM 音色庫（匯出 WAV/MP3 用）",
            "downloaded": sf2_ok and dll_ok,
            "size_mb": 142,
            "vram_mb": 0,
        })

        return items


_model_metadata_service: Optional[ModelMetadataService] = None


def get_model_metadata_service() -> ModelMetadataService:
    """取得 ModelMetadataService 單例"""
    global _model_metadata_service
    if _model_metadata_service is None:
        _model_metadata_service = ModelMetadataService()
    return _model_metadata_service
