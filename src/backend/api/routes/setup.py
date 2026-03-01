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
    ("small",    "Whisper Small",    500,  "輕量語音辨識，速度快"),
    ("medium",   "Whisper Medium",   1500, "平衡精度與速度"),
    ("large-v3", "Whisper Large-v3", 3000, "最高精度語音辨識"),
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
    """從 MODEL_VARIANTS 動態枚舉所有翻譯模型，並確認檔案是否已下載"""
    from backend.core.ai.translate.gemma import MODEL_VARIANTS as TG_VARIANTS
    from backend.core.ai.translate.qwen3 import MODEL_VARIANTS as Q3_VARIANTS

    items = []
    for model_type, variants, name_prefix in [
        ("translategemma", TG_VARIANTS, "TranslateGemma"),
        ("qwen3",          Q3_VARIANTS, "Qwen3"),
    ]:
        target_dir = get_models_dir(model_type)
        for size, quants in variants.items():
            for quant, info in quants.items():
                model_path = target_dir / info["filename"]
                size_desc  = _SIZE_DESC.get(model_type, {}).get(size, "")
                quant_desc = _QUANT_DESC.get(quant, "")
                description = f"{size_desc} · {quant_desc}" if size_desc and quant_desc else (size_desc or quant_desc)
                items.append({
                    "id":          f"{model_type}-{size}-{quant}",
                    "label":       f"{name_prefix} {size.upper()} {quant}",
                    "description": description,
                    "category":    "translate",
                    "downloaded":  model_path.exists(),
                    "size_mb":     info.get("size_mb", 0),
                })
    return items


@router.get("/models")
async def get_models_status():
    """取得所有工具/模型的安裝/下載狀態"""
    from backend.core.ai.model_manager import get_model_manager, MODELS_REGISTRY

    manager = get_model_manager()

    # ── 超解析模型（PyTorch 權重）──
    TOOL_LABELS = {
        "realesrgan-x4plus": {"label": "Real-ESRGAN x4+",  "description": "通用超解析（寫實）"},
        "hat-l-x4":          {"label": "HAT-L x4",          "description": "高品質超解析（寫實）"},
    }
    tools = []
    for model_id, config in MODELS_REGISTRY.get("upscale", {}).items():
        meta = TOOL_LABELS.get(model_id, {})
        tools.append({
            "id":          model_id,
            "label":       meta.get("label", model_id),
            "description": meta.get("description", config.get("description", "")),
            "installed":   manager.get_model_path("upscale", model_id) is not None,
            "size_mb":     config.get("size_mb", 0),
        })

    # ── Whisper STT 模型 ──
    whisper_dir = get_models_dir("whisper")
    stt_models = []
    for size, label, size_mb, description in _WHISPER_DISPLAY:
        model_dir = whisper_dir / size
        has_vocab = (model_dir / "vocabulary.txt").exists() or (model_dir / "vocabulary.json").exists()
        downloaded = model_dir.exists() and (model_dir / "model.bin").exists() and has_vocab
        stt_models.append({
            "id":          f"whisper-{size}",
            "label":       label,
            "description": description,
            "category":    "stt",
            "downloaded":  downloaded,
            "size_mb":     size_mb,
        })

    # ── 翻譯模型 (GGUF)：從 MODEL_VARIANTS 動態枚舉 ──
    translate_models = _enumerate_translate_models()

    return {
        "tools":  tools,
        "models": stt_models + translate_models,
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
