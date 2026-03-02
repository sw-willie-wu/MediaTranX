"""
系統安裝與設定路由 (REFACTOR V4)
"""
from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from uuid import uuid4

from backend.services.setup_service import get_setup_service
from backend.workers.task_manager import get_task_manager
from backend.core.paths import get_models_dir, get_temp_dir, get_app_config, save_app_config

router = APIRouter()

# 初始化 SetupService（完成 task handler 的綁定）
get_setup_service()


@router.get("/status")
async def get_status():
    """取得系統環境狀態"""
    service = get_setup_service()
    return await service.get_system_status()


@router.post("/initialize")
async def initialize_env(background_tasks: BackgroundTasks):
    """啟動 AI 環境初始化任務"""
    service = get_setup_service()
    task_id = f"setup-{uuid4().hex[:8]}"

    # 先向 TaskManager 登記，讓 SSE 端點能找到此 task_id
    task_manager = get_task_manager()
    task_manager.register_task(task_id, "ai.setup")

    # 背景執行安裝（async 任務，不走 executor）
    background_tasks.add_task(service.initialize_ai_env, task_id)

    return {"task_id": task_id}


# ─── 模型管理 ──────────────────────────────────────────────────────────────────

# 展示用的 Whisper 模型清單（size → size_mb）
_WHISPER_DISPLAY = [
    ("tiny",     "Whisper Tiny",     500,  "極速語音辨識（150MB）"),
    ("base",     "Whisper Base",     700,  "快速語音辨識（300MB）"),
    ("small",    "Whisper Small",    1500, "輕量語音辨識（500MB）"),
    ("medium",   "Whisper Medium",   3000, "平衡精度與速度（1.5GB）"),
    ("large-v3", "Whisper Large-v3", 5000, "最高精度語音辨識（3GB）"),
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
}

_QUANT_DESC = {
    "Q8_0":   "高精度量化",
    "Q4_K_M": "標準量化",
    "Q4_K_S": "標準量化，略省 VRAM",
    "Q3_K_L": "輕量量化",
    "Q3_K_M": "輕量量化，省 VRAM",
    "Q3_K_S": "輕量量化，最省 VRAM",
}


def _enumerate_translate_models() -> list[dict]:
    """從 registry 動態枚舉所有翻譯模型，並確認檔案是否已下載"""
    from backend.core.ai.registry import MODELS_REGISTRY, FORMAT_GGUF

    items = []
    gguf_models = MODELS_REGISTRY.get(FORMAT_GGUF, {})
    
    for model_family, config in gguf_models.items():
        if model_family not in ["translategemma", "qwen3"]:
            continue
            
        name_prefix = "TranslateGemma" if model_family == "translategemma" else "Qwen3"
        target_dir = get_models_dir(model_family)
        specs = config.get("specs", {})
        
        # 遍歷 size -> variants -> quant
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
                })
    return items


@router.get("/models")
async def get_models_status():
    """取得所有工具/模型的安裝/下載狀態（枚舉所有變體）"""
    from backend.core.ai.model_manager import get_model_manager
    from backend.core.ai.registry import MODELS_REGISTRY, FORMAT_PTH

    manager = get_model_manager()
    all_models = []

    # ── PyTorch 模型（超解析 & 人臉修復）：枚舉所有變體 ──
    UPSCALE_LABELS = {
        "realesrgan": {"label": "Real-ESRGAN",  "description": "通用超解析（寫實）"},
        "swinir":     {"label": "SwinIR",       "description": "Transformer 超解析"},
        "bsrgan":     {"label": "BSRGAN",       "description": "盲超解析"},
        "real-cugan": {"label": "Real-CUGAN",   "description": "動漫風格超解析"},
    }
    
    FACE_RESTORE_LABELS = {
        "codeformer": {"label": "CodeFormer",   "description": "VQ-GAN 人臉修復"},
        "gfpgan":     {"label": "GFPGAN",       "description": "GAN 人臉修復"},
    }
    
    # 變體描述映射
    VARIANT_DESC = {
        "x2plus": "2x 放大",
        "x4plus": "4x 放大",
        "x4plus-anime": "4x 放大（動漫）",
        "lightweight-x4": "輕量 4x",
        "classical-x4": "經典 4x",
        "realworld-x4": "真實世界 4x",
        "default": "標準",
        "up2x-conservative": "2x 保守降噪",
        "up2x-denoise3x": "2x 強力降噪",
        "up2x-no-denoise": "2x 無降噪",
        "up3x-conservative": "3x 保守降噪",
        "up3x-no-denoise": "3x 無降噪",
        "up4x-conservative": "4x 保守降噪",
        "up4x-no-denoise": "4x 無降噪",
        "v1.4": "v1.4",
    }
    
    pth_models = MODELS_REGISTRY.get(FORMAT_PTH, {})
    for model_family, config in pth_models.items():
        # 判斷分類
        if model_family in UPSCALE_LABELS:
            category = "upscale"
            family_meta = UPSCALE_LABELS[model_family]
        elif model_family in FACE_RESTORE_LABELS:
            category = "face_restore"
            family_meta = FACE_RESTORE_LABELS[model_family]
        else:
            continue
        
        # 枚舉所有變體
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
                "size_mb":     variant_spec.get("vram_mb", 0),
            })

    # ── Whisper STT 模型 ──
    whisper_dir = get_models_dir("whisper")
    for size, label, size_mb, description in _WHISPER_DISPLAY:
        model_dir = whisper_dir / size
        has_vocab = (model_dir / "vocabulary.txt").exists() or (model_dir / "vocabulary.json").exists()
        downloaded = model_dir.exists() and (model_dir / "model.bin").exists() and has_vocab
        all_models.append({
            "id":          f"whisper-{size}",
            "family":      "whisper",
            "variant":     size,
            "category":    "stt",
            "label":       label,
            "description": description,
            "downloaded":  downloaded,
            "size_mb":     size_mb,
        })

    # ── 翻譯模型 (GGUF)：從 registry 動態枚舉所有變體 ──
    translate_models = _enumerate_translate_models()
    all_models.extend(translate_models)

    return {
        "models": all_models,
    }


# ─── 應用程式設定 ───────────────────────────────────────────────────────────────

@router.get("/config")
async def get_config():
    """取得應用程式設定"""
    config = get_app_config()
    return {
        "models_dir": config.get("models_dir", ""),
        "effective_models_dir": str(get_models_dir()),
        "temp_dir": config.get("temp_dir", ""),
        "effective_temp_dir": str(get_temp_dir()),
    }


class AppConfigUpdate(BaseModel):
    models_dir: str = ""
    temp_dir: str = ""


@router.post("/config")
async def update_config(data: AppConfigUpdate):
    """更新應用程式設定，重啟後生效"""
    config = get_app_config()
    for key, val in {"models_dir": data.models_dir, "temp_dir": data.temp_dir}.items():
        if val.strip():
            config[key] = val.strip()
        else:
            config.pop(key, None)
    save_app_config(config)
    return {"ok": True, "needs_restart": True}


# ─── 模型下載 ───────────────────────────────────────────────────────────────────

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
