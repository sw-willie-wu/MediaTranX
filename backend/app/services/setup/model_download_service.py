"""
模型下載服務
負責各種格式模型的下載：Whisper (BIN)、GGUF、VLM、PTH。
"""
import logging
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Callable

from app.engine.paths import get_models_dir

logger = logging.getLogger(__name__)


# ─── 公開介面 ────────────────────────────────────────────────────────────────

def handle_model_download(params: dict, progress_callback: Callable) -> dict:
    """
    模型/工具下載任務處理器（同步）
    由 TaskManager 的 Executor 呼叫。
    """
    item_id = params.get("id", "")
    logger.info(f"Starting model download: {item_id}")
    progress_callback(0.05, f"準備下載 {item_id}...")

    try:
        from huggingface_hub import hf_hub_download, snapshot_download
    except ImportError:
        raise RuntimeError("huggingface_hub 未安裝，請先安裝基礎環境")

    if item_id.startswith("whisper-"):
        size = item_id[len("whisper-"):]
        _download_whisper(size, progress_callback, snapshot_download)

    elif item_id.startswith("translategemma-"):
        parts = item_id.split("-", 2)
        size, quant = parts[1], parts[2]
        _download_translate("translategemma", size, quant, progress_callback)

    elif item_id.startswith("qwen3-"):
        parts = item_id.split("-", 2)
        size, quant = parts[1], parts[2]
        _download_translate("qwen3", size, quant, progress_callback)

    elif item_id.startswith(("qwen3vl-", "internvl2.5-", "gemma3-")):
        parts = item_id.rsplit("-", 1)
        quant = parts[1]
        family_size = parts[0]
        size_parts = family_size.rsplit("-", 1)
        model_family = size_parts[0]
        size = size_parts[1]
        _download_vlm(model_family, size, quant, progress_callback)

    else:
        _download_pth_model(item_id, progress_callback)

    progress_callback(1.0, "下載完成")
    return {"status": "ok", "id": item_id}


# ─── 通用下載工具 ─────────────────────────────────────────────────────────────

def _download_from_url(
    url: str,
    target_path: Path,
    progress_callback: Callable,
    base_progress: float = 0.1,
    end_progress: float = 0.95,
) -> None:
    """從直接 URL 下載檔案（支援 GitHub releases 等）"""
    import requests

    target_path.parent.mkdir(parents=True, exist_ok=True)

    response = requests.get(url, stream=True, allow_redirects=True, timeout=60)
    response.raise_for_status()

    total = int(response.headers.get("content-length", 0))
    downloaded = 0
    chunk_size = 4 * 1024 * 1024

    with open(target_path, "wb") as f:
        for chunk in response.iter_content(chunk_size=chunk_size):
            if chunk:
                f.write(chunk)
                downloaded += len(chunk)
                if total > 0:
                    frac = downloaded / total
                    prog = base_progress + frac * (end_progress - base_progress)
                    mb_done = downloaded / 1024 / 1024
                    mb_total = total / 1024 / 1024
                    progress_callback(prog, f"下載中... {mb_done:.0f} / {mb_total:.0f} MB")

    if target_path.exists():
        size_mb = target_path.stat().st_size / 1024 / 1024
        progress_callback(end_progress, f"下載完成 ({size_mb:.1f} MB)")


def _stream_download(
    repo_id: str,
    filename: str,
    target_path: Path,
    progress_callback: Callable,
    base_progress: float = 0.1,
    end_progress: float = 0.95,
) -> None:
    """透過 HuggingFace Hub 下載單一檔案，支援即時進度回報"""
    from huggingface_hub import hf_hub_url

    try:
        url = hf_hub_url(repo_id=repo_id, filename=filename)
        logger.info(f"Resolved HF URL for {filename}: {url}")
        _download_from_url(
            url=url,
            target_path=target_path,
            progress_callback=progress_callback,
            base_progress=base_progress,
            end_progress=end_progress,
        )
    except Exception as e:
        logger.error(f"Streaming download failed for {filename}: {e}")
        raise RuntimeError(f"下載失敗 ({filename}): {str(e)}")


# ─── 各格式下載器 ─────────────────────────────────────────────────────────────

def _download_whisper(size: str, progress_callback: Callable, snapshot_download) -> None:
    from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_BIN

    whisper_config = MODELS_REGISTRY.get(FORMAT_BIN, {}).get("whisper", {})
    variants = whisper_config.get("variants", {})
    variant_spec = variants.get(size)

    if not variant_spec:
        raise ValueError(f"未知的 Whisper 模型大小: {size}")

    repo_id = variant_spec["repo_id"]
    local_dir = get_models_dir("whisper") / size
    local_dir.mkdir(parents=True, exist_ok=True)

    model_bin = local_dir / "model.bin"
    if not model_bin.exists():
        progress_callback(0.1, f"下載 Whisper {size} 模型中...")
        _stream_download(repo_id, "model.bin", model_bin, progress_callback, 0.1, 0.9)

    progress_callback(0.9, "下載設定檔與分詞器...")
    snapshot_download(
        repo_id=repo_id,
        local_dir=str(local_dir),
        ignore_patterns=["*.md", "model.bin", "model.safetensors"],
    )
    progress_callback(0.98, "模型檔案檢驗完成")


def _download_vlm(model_family: str, size: str, quant: str, progress_callback: Callable) -> None:
    """下載 VLM 模型（主模型 + mmproj）"""
    from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_VLM

    config = MODELS_REGISTRY.get(FORMAT_VLM, {}).get(model_family, {})
    specs = config.get("specs", {})
    variant = specs.get(size, {}).get("variants", {}).get(quant)

    if not variant:
        raise ValueError(f"未知的 VLM 模型變體: {model_family}-{size}-{quant}")

    slot = config.get("slot", "vlm")
    target_dir = get_models_dir() / slot
    target_dir.mkdir(parents=True, exist_ok=True)

    progress_callback(0.05, f"下載 {model_family} {size} {quant} 主模型...")
    _stream_download(
        repo_id=variant["repo_id"],
        filename=variant["filename"],
        target_path=target_dir / variant["filename"],
        progress_callback=progress_callback,
        base_progress=0.05,
        end_progress=0.65,
    )

    if "mmproj_filename" in variant:
        progress_callback(0.65, f"下載 mmproj（視覺編碼器）...")
        _stream_download(
            repo_id=variant.get("mmproj_repo_id", variant["repo_id"]),
            filename=variant["mmproj_filename"],
            target_path=target_dir / variant["mmproj_filename"],
            progress_callback=progress_callback,
            base_progress=0.65,
            end_progress=0.95,
        )

    progress_callback(0.95, "VLM 模型下載完成")


def _download_translate(model_type: str, size: str, quant: str, progress_callback: Callable) -> None:
    from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_GGUF

    model_config = MODELS_REGISTRY.get(FORMAT_GGUF, {}).get(model_type, {})
    specs = model_config.get("specs", {})
    variant = specs.get(size, {}).get("variants", {}).get(quant)

    if not variant:
        raise ValueError(f"未知的模型變體: {model_type}-{size}-{quant}")

    target_dir = get_models_dir(model_type)
    target_dir.mkdir(parents=True, exist_ok=True)

    progress_callback(0.1, f"下載 {model_type} {size} {quant} 中...")
    _stream_download(
        repo_id=variant["repo_id"],
        filename=variant["filename"],
        target_path=target_dir / variant["filename"],
        progress_callback=progress_callback,
        base_progress=0.1,
        end_progress=0.95,
    )
    progress_callback(0.95, "模型下載完成")


def _download_pth_model(model_id: str, progress_callback: Callable) -> None:
    """下載 PTH 模型（upscale / face_restore）"""
    from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_PTH

    pth_models = MODELS_REGISTRY.get(FORMAT_PTH, {})

    # 智能分解 ID: 嘗試匹配所有 family（處理 real-cugan 這種多連字符的情況）
    family = None
    variant = None

    matched_families = [
        (family_name, model_id[len(family_name) + 1:])
        for family_name in pth_models.keys()
        if model_id.startswith(family_name + "-")
    ]

    if matched_families:
        family, variant = max(matched_families, key=lambda x: len(x[0]))

    if not family or not variant:
        raise ValueError(f"無效的模型 ID 格式: {model_id}，無法匹配任何已知模型家族")

    model_config = pth_models.get(family)

    if not model_config:
        raise ValueError(f"未知的模型家族: {family}")

    variant_spec = model_config.get("variants", {}).get(variant)
    if not variant_spec:
        raise ValueError(f"未知的模型變體: {family}-{variant}")

    slot = model_config.get("slot", "")
    if not slot:
        raise ValueError(f"模型 {family} 缺少 slot 配置")

    target_dir = get_models_dir() / slot
    target_dir.mkdir(parents=True, exist_ok=True)

    filename = variant_spec["filename"]
    target_path = target_dir / filename

    needs_unzip = variant_spec.get("unzip", False)
    archive_path = variant_spec.get("archive_path", None)

    if "url" in variant_spec:
        url = variant_spec["url"]
        progress_callback(0.1, f"下載 {family} {variant} 中...")

        if needs_unzip:
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_archive = Path(temp_dir) / "archive.zip"
                _download_from_url(url, temp_archive, progress_callback, 0.1, 0.85)

                progress_callback(0.85, "解壓縮中...")

                with zipfile.ZipFile(temp_archive, 'r') as zip_ref:
                    if archive_path:
                        all_files = zip_ref.namelist()

                        matching_files = []
                        if archive_path in all_files:
                            matching_files = [archive_path]
                        else:
                            matching_files = [
                                name for name in all_files
                                if name.endswith(archive_path) or name.endswith('/' + archive_path)
                            ]
                            if not matching_files:
                                target_basename = Path(archive_path).name
                                matching_files = [
                                    name for name in all_files
                                    if Path(name).name == target_basename
                                ]

                        if not matching_files:
                            files_list = "\n  ".join(all_files[:10])
                            raise ValueError(
                                f"壓縮檔中找不到 {archive_path}\n"
                                f"壓縮檔包含 {len(all_files)} 個文件，前幾個：\n  {files_list}"
                            )

                        source_file = matching_files[0]
                        temp_extract = Path(temp_dir) / "extracted"
                        zip_ref.extract(source_file, temp_extract)
                        extracted_file = temp_extract / source_file
                        shutil.copy2(extracted_file, target_path)
                    else:
                        zip_ref.extractall(target_dir)

                progress_callback(0.95, "解壓縮完成")
        else:
            _download_from_url(url, target_path, progress_callback, 0.1, 0.95)
    elif "repo_id" in variant_spec:
        repo_id = variant_spec["repo_id"]
        progress_callback(0.1, f"下載 {family} {variant} 中...")
        _stream_download(
            repo_id=repo_id,
            filename=filename,
            target_path=target_path,
            progress_callback=progress_callback,
            base_progress=0.1,
            end_progress=0.95,
        )
    else:
        raise ValueError(f"模型 {family}-{variant} 缺少 url 或 repo_id 配置")

    progress_callback(0.95, "模型下載完成")
