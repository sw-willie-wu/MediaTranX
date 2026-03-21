"""
模型管理路由（列表、下載、移除）
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.services.setup import get_setup_service
from app.workers.task_manager import get_task_manager
from app.engine.paths import get_models_dir

router = APIRouter()


# ─── 分類定義（前端 tab 動態產生）────────────────────────────────────────────

MODEL_CATEGORIES = [
    {"key": "upscale",      "label": "超解析",  "order": 0},
    {"key": "face_restore", "label": "人臉修復", "order": 1},
    {"key": "stt",          "label": "語音辨識", "order": 2},
    {"key": "translate",    "label": "翻譯",    "order": 3},
    {"key": "vlm",          "label": "OCR",     "order": 4},
    {"key": "segment",      "label": "分割",    "order": 5},
]

# ─── 顯示用常數 ──────────────────────────────────────────────────────────────

_WHISPER_DISPLAY = [
    ("tiny",     "Whisper Tiny",     "極速語音辨識"),
    ("base",     "Whisper Base",     "快速語音辨識"),
    ("small",    "Whisper Small",    "輕量語音辨識"),
    ("medium",   "Whisper Medium",   "平衡精度與速度"),
    ("large-v3", "Whisper Large-v3", "最高精度語音辨識"),
]

_SIZE_DESC = {
    "translategemma": {
        "4b":  "輕量，速度快",
        "12b": "平衡精度與速度",
        "27b": "最高翻譯精度",
    },
    "qwen3": {
        "1.7b": "超輕量，速度極快",
        "4b":   "輕量，速度快",
        "8b":   "平衡精度與速度",
        "14b":  "高精度翻譯",
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
        "4b":  "輕量 OCR（推薦）",
        "12b": "高精度 OCR",
    },
}

_QUANT_DESC = {
    "Q8_0":   "高精度量化",
    "Q4_K_M": "標準量化",
    "Q4_K_S": "標準量化，略省 VRAM",
    "Q3_K_L": "輕量量化",
    "Q3_K_M": "輕量量化，省 VRAM",
    "Q3_K_S": "輕量量化，最省 VRAM",
}

_VLM_FAMILY_LABELS = {
    "qwen3vl":     "Qwen3-VL",
    "internvl2.5": "InternVL2.5",
    "gemma3":      "Gemma 3",
}


# ─── 列舉輔助 ────────────────────────────────────────────────────────────────

def _enumerate_translate_models() -> list[dict]:
    """從 registry 動態枚舉所有翻譯模型"""
    from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_GGUF

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

                size_desc  = _SIZE_DESC.get(model_family, {}).get(size, "")
                quant_desc = _QUANT_DESC.get(quant, "")
                description = f"{size_desc} · {quant_desc}" if size_desc and quant_desc else (size_desc or quant_desc)

                items.append({
                    "id":          f"{model_family}-{size}-{quant}",
                    "family":      model_family,
                    "variant":     f"{size}-{quant}",
                    "label":       f"{name_prefix} {size.upper()} {quant}",
                    "description": description,
                    "category":    "translate",
                    "downloaded":  model_path.exists(),
                    "size_mb":     quant_spec.get("size_mb", 0),
                    "vram_mb":     quant_spec.get("size_mb", 0) + size_spec.get("vram_overhead_mb", 0),
                })
    return items


def _enumerate_vlm_models() -> list[dict]:
    """從 registry 動態枚舉所有 VLM OCR 模型"""
    from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_VLM

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
                    "id":          f"{model_family}-{size}-{quant}",
                    "family":      model_family,
                    "variant":     f"{size}:{quant}",
                    "label":       f"{family_label} {size.upper()} {quant}",
                    "description": f"{_SIZE_DESC.get(model_family, {}).get(size, '')} · {quant_desc}",
                    "category":    "vlm",
                    "downloaded":  downloaded,
                    "size_mb":     total_mb,
                    "vram_mb":     total_mb + size_spec.get("vram_overhead_mb", 0),
                })
    return items


# ─── 端點 ────────────────────────────────────────────────────────────────────

@router.get("/models")
async def get_models_status():
    """取得所有工具/模型的安裝/下載狀態"""
    from app.engine.ai.model_manager import get_model_manager
    from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_PTH

    manager = get_model_manager()
    all_models = []

    # ── PyTorch 模型（超解析 & 人臉修復） ──
    UPSCALE_LABELS = {
        "realesrgan": {"label": "Real-ESRGAN",  "description": "通用超解析（寫實）"},
        "swinir":     {"label": "SwinIR",       "description": "Transformer 超解析"},
        "bsrgan":     {"label": "BSRGAN",       "description": "盲超解析"},
        "real-cugan": {"label": "Real-CUGAN",   "description": "動漫風格超解析"},
        "waifu2x":    {"label": "Waifu2x",      "description": "經典動漫超解析"},
    }

    FACE_RESTORE_LABELS = {
        "codeformer": {"label": "CodeFormer",   "description": "VQ-GAN 人臉修復"},
        "gfpgan":     {"label": "GFPGAN",       "description": "GAN 人臉修復"},
    }

    SEGMENT_LABELS = {
        "mobilesam": {"label": "MobileSAM", "description": "輕量物件分割（AI 移除用）"},
    }

    VARIANT_DESC = {
        "x2plus": "2x",
        "x4plus": "4x",
        "x4plus-anime": "4x - anime",
        "lightweight-x4": "4x - lightweight",
        "classical-x4": "4x - classical",
        "realworld-x4": "4x - realworld",
        "default": "標準",
        "up2x-conservative": "2x - conservative",
        # "up2x-denoise3x": "2x - 強力降噪",
        # "up2x-no-denoise": "2x 無降噪",
        "up3x-conservative": "3x - conservative",
        # "up3x-no-denoise": "3x 無降噪",
        "up4x-conservative": "4x - conservative",
        # "up4x-no-denoise": "4x 無降噪",
        "cunet": "CUnet 變體",
        "v1.4": "v1.4",
    }

    pth_models = MODELS_REGISTRY.get(FORMAT_PTH, {})
    for model_family, config in pth_models.items():
        if model_family in UPSCALE_LABELS:
            category = "upscale"
            family_meta = UPSCALE_LABELS[model_family]
        elif model_family in FACE_RESTORE_LABELS:
            category = "face_restore"
            family_meta = FACE_RESTORE_LABELS[model_family]
        elif model_family in SEGMENT_LABELS:
            category = "segment"
            family_meta = SEGMENT_LABELS[model_family]
        else:
            continue

        variants = config.get("variants", {})
        for variant_name, variant_spec in variants.items():
            model_path = manager.get_model_path(model_family, variant_name)
            downloaded = model_path is not None and model_path.exists()

            variant_desc = VARIANT_DESC.get(variant_name, variant_name)
            label = f"{family_meta['label']} - {variant_desc}" if len(variants) > 1 else family_meta['label']

            all_models.append({
                "id":          f"{model_family}-{variant_name}",
                "family":      model_family,
                "variant":     variant_name,
                "category":    category,
                "label":       label,
                "description": family_meta["description"],
                "downloaded":  downloaded,
                "size_mb":     variant_spec.get("size_mb", 0),
                "vram_mb":     variant_spec.get("vram_mb", 0),
                "max_scale":   variant_spec.get("scale", 4),
            })

    # ── Whisper STT ──
    from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_BIN
    whisper_variants = MODELS_REGISTRY.get(FORMAT_BIN, {}).get("whisper", {}).get("variants", {})
    whisper_dir = get_models_dir("whisper")
    for size, label, description in _WHISPER_DISPLAY:
        model_dir = whisper_dir / size
        has_vocab = (model_dir / "vocabulary.txt").exists() or (model_dir / "vocabulary.json").exists()
        downloaded = model_dir.exists() and (model_dir / "model.bin").exists() and has_vocab
        spec = whisper_variants.get(size, {})
        all_models.append({
            "id":          f"whisper-{size}",
            "family":      "whisper",
            "variant":     size,
            "category":    "stt",
            "label":       label,
            "description": description,
            "downloaded":  downloaded,
            "size_mb":     spec.get("size_mb", 0),
            "vram_mb":     spec.get("vram_mb", 0),
        })

    # ── 翻譯模型 (GGUF) ──
    all_models.extend(_enumerate_translate_models())

    # ── VLM 模型（OCR） ──
    all_models.extend(_enumerate_vlm_models())

    return {"categories": MODEL_CATEGORIES, "models": all_models}


class DownloadRequest(BaseModel):
    id: str


@router.post("/models/remove")
async def remove_model_item(request: DownloadRequest):
    """刪除已下載的工具/模型檔案"""
    if not request.id:
        raise HTTPException(status_code=400, detail="Missing id")
    service = get_setup_service()
    service.remove_model(request.id)
    return {"ok": True}


@router.post("/models/download")
async def download_model_item(request: DownloadRequest):
    """提交工具/模型下載任務"""
    if not request.id:
        raise HTTPException(status_code=400, detail="Missing id")

    task_manager = get_task_manager()
    task_id = await task_manager.submit("setup.model_download", {"id": request.id})
    return {"task_id": task_id}
