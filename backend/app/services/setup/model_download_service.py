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

from app.init.configs import get_settings

logger = logging.getLogger(__name__)


def _models_dir(category: str = "") -> Path:
    """Get models directory with optional category subdirectory, ensuring it exists."""
    d = Path(get_settings().path.models)
    if category:
        d = d / category
    d.mkdir(parents=True, exist_ok=True)
    return d


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

    elif item_id.startswith("demucs-"):
        variant = item_id[len("demucs-"):]
        _download_demucs(variant, progress_callback)

    elif item_id.startswith("alignment-"):
        lang_code = item_id[len("alignment-"):]
        _download_alignment(lang_code, progress_callback)

    elif item_id.startswith("rife-"):
        variant = item_id[len("rife-"):]
        _download_rife(variant, progress_callback)

    elif item_id == "basic-pitch":
        _download_basic_pitch(progress_callback)

    elif item_id == "fluidsynth":
        _download_fluidsynth(progress_callback)

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
    from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_PKG

    whisper_config = MODELS_REGISTRY.get(FORMAT_PKG, {}).get("whisper", {})
    variants = whisper_config.get("variants", {})
    variant_spec = variants.get(size)

    if not variant_spec:
        raise ValueError(f"未知的 Whisper 模型大小: {size}")

    repo_id = variant_spec["repo_id"]
    local_dir = _models_dir("whisper") / size
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
    target_dir = _models_dir() / slot
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

    target_dir = _models_dir(model_type)
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


def _download_demucs(variant: str, progress_callback: Callable) -> None:
    """下載 Demucs 模型 checkpoint（直接從 Facebook 下載，避免 demucs 套件路徑問題）"""
    from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_PKG, SLOT_DEMUCS

    family = MODELS_REGISTRY.get(FORMAT_PKG, {}).get("demucs")
    if not family:
        raise ValueError("demucs 未在 registry 中註冊")

    variant_spec = family["variants"].get(variant)
    if not variant_spec:
        raise ValueError(f"未知的 demucs 變體: {variant}")

    model_name = variant_spec.get("model_name", variant)
    progress_callback(0.1, f"正在下載 {model_name}...")

    # 模型 hash → checkpoint 檔名對照（從 demucs/remote/*.yaml + files.txt）
    DEMUCS_MODELS = {
        "htdemucs": ("hybrid_transformer", "955717e8-8726e21a.th"),
        "htdemucs_6s": ("hybrid_transformer", "5c90dfd2-34c22ccb.th"),
    }

    if model_name not in DEMUCS_MODELS:
        raise ValueError(f"不支援的 demucs 模型: {model_name}")

    folder, filename = DEMUCS_MODELS[model_name]
    url = f"https://dl.fbaipublicfiles.com/demucs/{folder}/{filename}"

    checkpoints_dir = _models_dir() / SLOT_DEMUCS / "checkpoints"
    target_path = checkpoints_dir / filename

    if target_path.exists():
        progress_callback(0.95, "模型已存在")
        return

    progress_callback(0.15, f"下載 {model_name} checkpoint...")
    _download_from_url(url, target_path, progress_callback, 0.15, 0.95)
    progress_callback(0.95, "模型下載完成")


def _download_rife(variant: str, progress_callback: Callable) -> None:
    """Download RIFE model checkpoint (extracts flownet.pkl from zip)"""
    import io
    import zipfile
    from app.engine.ai.registry import MODELS_REGISTRY, FORMAT_PKG, SLOT_RIFE

    family = MODELS_REGISTRY.get(FORMAT_PKG, {}).get("rife")
    if not family:
        raise ValueError("rife not registered")

    variant_spec = family["variants"].get(variant)
    if not variant_spec:
        raise ValueError(f"Unknown RIFE variant: {variant}")

    url = variant_spec["url"]
    filename = variant_spec["filename"]
    zip_entry = variant_spec.get("zip_entry", "")

    target_dir = _models_dir() / SLOT_RIFE
    target_path = target_dir / filename

    if target_path.exists():
        progress_callback(0.95, "模型已存在")
        return

    import tempfile
    progress_callback(0.1, f"下載 RIFE {variant}...")

    # Download zip to temp, extract flownet.pkl
    tmp_zip = Path(tempfile.mktemp(suffix=".zip"))
    try:
        _download_from_url(url, tmp_zip, progress_callback, 0.1, 0.80)
        progress_callback(0.85, "解壓模型...")

        target_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(tmp_zip, "r") as zf:
            # Find flownet.pkl in zip
            pkl_name = zip_entry or next(
                (n for n in zf.namelist() if n.endswith("flownet.pkl")), None
            )
            if not pkl_name:
                raise RuntimeError("flownet.pkl not found in zip")
            data = zf.read(pkl_name)
            target_path.write_bytes(data)
            logger.info(f"Extracted {pkl_name} → {target_path} ({len(data)} bytes)")
    finally:
        tmp_zip.unlink(missing_ok=True)

    progress_callback(0.95, "模型下載完成")


def _download_alignment(lang_code: str, progress_callback: Callable) -> None:
    """下載 Wav2Vec2 alignment 模型（透過 transformers 從 HuggingFace 下載）"""
    from app.engine.ai.audio.wav2vec2 import LANG_MODELS

    if lang_code not in LANG_MODELS:
        raise ValueError(f"不支援的語言: {lang_code}")

    repo_id = LANG_MODELS[lang_code]
    cache_dir = str(_models_dir("alignment"))
    progress_callback(0.1, f"下載 {repo_id}...")

    try:
        from huggingface_hub import list_repo_files, hf_hub_download

        # 列出 repo 中的檔案
        all_files = list_repo_files(repo_id)
        download_files = [
            f for f in all_files
            if not f.endswith((".md", ".txt", ".gitattributes"))
        ]

        if not download_files:
            raise RuntimeError(f"Repo {repo_id} 中沒有可下載的檔案")

        total = len(download_files)
        for i, filename in enumerate(download_files):
            prog = 0.1 + (i / total) * 0.85  # 0.1 ~ 0.95
            progress_callback(prog, f"下載 {filename}（{i + 1}/{total}）...")
            hf_hub_download(
                repo_id=repo_id,
                filename=filename,
                cache_dir=cache_dir,
            )

    except Exception as e:
        raise RuntimeError(f"Alignment 模型下載失敗: {e}")

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

    target_dir = _models_dir() / slot
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


def _download_basic_pitch(progress_callback: Callable) -> None:
    """Trigger basic-pitch model download by running a dummy inference."""
    progress_callback(0.1, "Downloading Basic Pitch model...")

    import numpy as np
    import tempfile

    # Create a tiny silent audio file to trigger model auto-download
    try:
        import soundfile as sf

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            tmp_path = f.name
            sf.write(tmp_path, np.zeros(44100, dtype=np.float32), 44100)

        progress_callback(0.3, "Loading Basic Pitch model...")
        from basic_pitch.inference import predict

        try:
            predict(tmp_path)
        except Exception:
            pass  # May fail on silent audio, but model is now cached

        import os

        os.unlink(tmp_path)
    except Exception as e:
        logger.warning(f"Basic Pitch download trigger failed: {e}")
        raise

    progress_callback(0.95, "Basic Pitch model ready")


def _download_fluidsynth(progress_callback: Callable) -> None:
    """Download FluidSynth DLL + FluidR3 GM SoundFont."""
    dest = Path(get_settings().path.fluidsynth)
    dest.mkdir(parents=True, exist_ok=True)

    # Step 1: Download FluidSynth Windows release (zip with all DLLs)
    progress_callback(0.1, "Downloading FluidSynth...")
    dll_url = "https://github.com/FluidSynth/fluidsynth/releases/download/v2.5.2/fluidsynth-v2.5.2-win10-x64-glib.zip"

    import io
    import zipfile
    import requests

    response = requests.get(dll_url, stream=True, timeout=120, allow_redirects=True)
    response.raise_for_status()
    buf = io.BytesIO(response.content)

    progress_callback(0.3, "Extracting FluidSynth DLLs...")
    with zipfile.ZipFile(buf) as zf:
        for name in zf.namelist():
            if name.endswith(".dll") and "/bin/" in name:
                dll_data = zf.read(name)
                dll_filename = name.rsplit("/", 1)[-1]
                (dest / dll_filename).write_bytes(dll_data)
                logger.info(f"Extracted {dll_filename} to {dest}")

    # Step 2: Download SoundFont (FluidR3 GM, SF2 stereo ~141MB)
    progress_callback(0.4, "Downloading SoundFont (FluidR3 GM)...")
    sf2_url = "https://musical-artifacts.com/artifacts/738/FluidR3_GM.sf2"
    _download_from_url(sf2_url, dest / "FluidR3_GM.sf2", progress_callback, 0.4, 0.95)

    progress_callback(0.95, "FluidSynth + SoundFont ready")
