"""
功能安裝 API 路由
讓使用者一鍵安裝可選功能所需的 Python 套件
"""
import logging
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.device import has_nvidia_gpu
from backend.core.paths import get_realesrgan_dir, get_waifu2x_dir, get_cuda_dir
from backend.workers.task_manager import get_task_manager

logger = logging.getLogger(__name__)

router = APIRouter()

# 功能 → 需要安裝的套件（import 名稱）
FEATURE_PACKAGES = {
    "translategemma": {
        "label": "翻譯功能",
        "packages": ["llama_cpp"],
    },
}

# import 名稱 → pip install 名稱（不同時才需要列出）
PIP_NAMES = {
    "llama_cpp": "llama-cpp-python",
}

TASK_TYPE_INSTALL = "setup.install"

# 註冊任務處理器（模組載入時）
_handler_registered = False


def _ensure_handler():
    global _handler_registered
    if _handler_registered:
        return
    manager = get_task_manager()
    manager.register_handler(TASK_TYPE_INSTALL, _handle_install_task)
    _handler_registered = True


class InstallRequest(BaseModel):
    feature: str = Field(..., description="功能名稱 (例如 translategemma)")


class InstallResponse(BaseModel):
    task_id: str
    message: str


class FeatureStatusResponse(BaseModel):
    feature: str
    label: str
    installed: bool
    missing_packages: list[str]


def _check_package(name: str) -> bool:
    """
    檢查套件是否已安裝且適合當前環境

    特殊處理 llama_cpp：如果機器有 NVIDIA GPU 但 llama-cpp-python
    沒有 GPU 支援，視為未安裝（需要升級至 GPU 版）
    """
    try:
        mod = __import__(name)
        if name == "llama_cpp" and has_nvidia_gpu():
            if hasattr(mod, "llama_supports_gpu_offload"):
                if not mod.llama_supports_gpu_offload():
                    logger.info("llama-cpp-python is CPU-only but NVIDIA GPU detected — needs GPU upgrade")
                    return False
        return True
    except ImportError:
        return False


@router.get("/features/{feature}/status", response_model=FeatureStatusResponse)
async def get_feature_status(feature: str):
    """查詢功能的安裝狀態"""
    if feature not in FEATURE_PACKAGES:
        raise HTTPException(status_code=404, detail=f"未知的功能: {feature}")

    info = FEATURE_PACKAGES[feature]
    missing = [pkg for pkg in info["packages"] if not _check_package(pkg)]

    return FeatureStatusResponse(
        feature=feature,
        label=info["label"],
        installed=len(missing) == 0,
        missing_packages=missing,
    )


@router.post("/install", response_model=InstallResponse)
async def install_feature(request: InstallRequest):
    """安裝功能所需的套件"""
    feature = request.feature

    if feature not in FEATURE_PACKAGES:
        raise HTTPException(status_code=404, detail=f"未知的功能: {feature}")

    info = FEATURE_PACKAGES[feature]
    missing = [pkg for pkg in info["packages"] if not _check_package(pkg)]

    if not missing:
        return InstallResponse(task_id="", message=f"{info['label']}已安裝完成")

    _ensure_handler()

    manager = get_task_manager()
    task_id = await manager.submit(TASK_TYPE_INSTALL, {
        "feature": feature,
        "packages": missing,
        "label": info["label"],
    })

    return InstallResponse(
        task_id=task_id,
        message=f"開始安裝{info['label']}...",
    )


def _build_pip_args(pkg: str, has_cuda: bool) -> list[str]:
    """
    根據套件和 GPU 狀態建立 pip install 指令

    llama-cpp-python 在 Windows 上沒有 PyPI 預編譯 wheel，
    需要從社群提供的 wheel 安裝。
    """
    import platform
    python = sys.executable
    pip_name = PIP_NAMES.get(pkg, pkg)
    base = [python, "-m", "pip", "install"]

    if pkg == "llama_cpp":
        is_win = platform.system() == "Windows"

        if is_win and has_cuda:
            # Windows + CUDA: 社群預編譯 wheel (CUDA 12.8 + Gemma 3 支援)
            # 同時安裝 CUDA runtime DLL（Windows 上 pip 安裝的 DLL 不在 PATH 中，
            # translategemma.py 的 _setup_cuda_dll_path() 會處理 PATH）
            wheel_url = (
                "https://huggingface.co/boneylizardwizard/"
                "llama-cpp-python-038-cu128-gemma3-wheel/resolve/main/"
                "llama_cpp_python-0.3.8%2Bcu128.gemma3-cp311-cp311-win_amd64.whl"
            )
            return base + [
                wheel_url,
                "nvidia-cuda-runtime-cu12",
                "nvidia-cublas-cu12",
            ]

        if is_win and not has_cuda:
            # Windows + CPU: 社群預編譯 CPU wheel
            wheel_url = (
                "https://eswarthammana.github.io/llama-cpp-wheels/"
                "llama_cpp_python-0.3.14-cp311-cp311-win_amd64.whl"
            )
            return base + [wheel_url]

        if has_cuda:
            # Linux + CUDA: 官方 wheel index
            return base + [pip_name, "--extra-index-url",
                           "https://abetlen.github.io/llama-cpp-python/whl/cu124"]

    return base + [pip_name]


def _uninstall_package(pip_name: str) -> bool:
    """卸載指定套件（用於 CPU→GPU 升級前）"""
    python = sys.executable
    args = [python, "-m", "pip", "uninstall", pip_name, "-y"]
    logger.info(f"Uninstalling {pip_name}: {' '.join(args)}")
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=120)
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        logger.error(f"Timeout uninstalling {pip_name}")
        return False


def _is_package_installed(name: str) -> bool:
    """檢查套件是否已安裝（不檢查 GPU 支援）"""
    try:
        __import__(name)
        return True
    except ImportError:
        return False


def _handle_install_task(params: dict, progress_callback) -> dict:
    """執行 pip install（在 executor 中執行）"""
    packages = params["packages"]
    label = params["label"]
    total = len(packages)

    progress_callback(0.0, "偵測 GPU 環境...")

    has_cuda = has_nvidia_gpu()
    gpu_msg = "偵測到 NVIDIA GPU，將安裝 GPU 版本" if has_cuda else "未偵測到 NVIDIA GPU，將安裝 CPU 版本"
    logger.info(gpu_msg)
    progress_callback(0.02, gpu_msg)

    installed = []
    failed = []

    for i, pkg in enumerate(packages):
        pip_name = PIP_NAMES.get(pkg, pkg)
        variant = " (GPU)" if pkg == "llama_cpp" and has_cuda else ""
        progress_callback(0.02 + (i / total) * 0.96, f"正在安裝 {pip_name}{variant}...")

        # CPU→GPU 升級：先卸載 CPU 版再安裝 GPU 版
        if has_cuda and _is_package_installed(pkg):
            progress_callback(0.02 + (i / total) * 0.96, f"正在移除 CPU 版 {pip_name}...")
            _uninstall_package(pip_name)

        args = _build_pip_args(pkg, has_cuda)
        logger.info(f"Running: {' '.join(args)}")

        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                timeout=600,  # 10 分鐘超時
            )

            if result.returncode == 0:
                installed.append(pkg)
                logger.info(f"Installed {pip_name}")
            else:
                failed.append(pkg)
                logger.error(f"Failed to install {pip_name}: {result.stderr}")

        except subprocess.TimeoutExpired:
            failed.append(pkg)
            logger.error(f"Timeout installing {pip_name}")

        progress_callback(
            0.02 + ((i + 1) / total) * 0.96,
            f"{pip_name} 安裝完成" if pkg in installed else f"{pip_name} 安裝失敗"
        )

    if failed:
        pip_names = [PIP_NAMES.get(p, p) for p in failed]
        progress_callback(1.0, f"部分套件安裝失敗: {', '.join(pip_names)}")
        raise RuntimeError(f"安裝失敗: {', '.join(pip_names)}")

    progress_callback(1.0, f"{label}安裝完成")

    return {
        "installed": installed,
        "failed": failed,
    }


# ── 模型管理 ──────────────────────────────────────────────────────────────────

TASK_TYPE_DOWNLOAD = "setup.download"

TOOL_URLS = {
    "realesrgan": "https://github.com/xinntao/Real-ESRGAN/releases/download/v0.2.5.0/realesrgan-ncnn-vulkan-20220424-windows.zip",
    "waifu2x": "https://github.com/nihui/waifu2x-ncnn-vulkan/releases/download/20250915/waifu2x-ncnn-vulkan-20250915-windows.zip",
}

TOOL_DIRS = {
    "realesrgan": get_realesrgan_dir,
    "waifu2x": get_waifu2x_dir,
}

# Whisper 要顯示的型號及檔案大小（MB）
WHISPER_MODELS = {
    "tiny": 150,
    "base": 300,
    "small": 500,
    "medium": 1500,
    "large-v3": 3000,
}

_download_handler_registered = False


def _ensure_download_handler():
    global _download_handler_registered
    if _download_handler_registered:
        return
    manager = get_task_manager()
    manager.register_handler(TASK_TYPE_DOWNLOAD, _handle_download_task)
    _download_handler_registered = True


class DownloadRequest(BaseModel):
    id: str = Field(..., description="工具或模型 ID")


class DownloadResponse(BaseModel):
    task_id: str


@router.get("/models")
async def get_models_status():
    """查詢所有工具/模型的下載狀態"""
    from backend.services.image.upscale_service import get_image_upscale_service
    from backend.core.ai.whisper import get_whisper
    from backend.core.ai.translategemma import get_translategemma, MODEL_VARIANTS as GEMMA_VARIANTS, DEFAULT_QUANT as GEMMA_DEFAULT_QUANT
    from backend.core.ai.qwen3 import get_qwen3, MODEL_VARIANTS as QWEN_VARIANTS, DEFAULT_QUANT as QWEN_DEFAULT_QUANT

    svc = get_image_upscale_service()
    whisper = get_whisper()
    gemma = get_translategemma()
    qwen = get_qwen3()

    tools = [
        {
            "id": "realesrgan",
            "label": "Real-ESRGAN",
            "description": "超解析（寫實照片）",
            "installed": svc.is_realesrgan_available(),
            "size_mb": 17,
        },
        {
            "id": "waifu2x",
            "label": "waifu2x",
            "description": "超解析（動漫圖片）",
            "installed": svc.is_waifu2x_available(),
            "size_mb": 7,
        },
    ]

    models = []

    # Whisper 語音辨識模型
    for size, size_mb in WHISPER_MODELS.items():
        models.append({
            "id": f"whisper-{size}",
            "label": f"Whisper {size.replace('-', ' ').title()}",
            "category": "stt",
            "downloaded": whisper._is_model_downloaded(size),
            "size_mb": size_mb,
        })

    # TranslateGemma 翻譯模型（每個大小取預設量化）
    for size, quants in GEMMA_VARIANTS.items():
        quant = GEMMA_DEFAULT_QUANT.get(size, "Q4_K_M")
        variant = quants.get(quant)
        if variant:
            models.append({
                "id": f"translategemma-{size}-{quant}",
                "label": f"TranslateGemma {size.upper()} {quant}",
                "category": "translate",
                "downloaded": gemma._is_model_downloaded(size, quant),
                "size_mb": variant["size_mb"],
            })

    # Qwen3 翻譯模型（每個大小取預設量化）
    for size, quants in QWEN_VARIANTS.items():
        quant = QWEN_DEFAULT_QUANT.get(size, "Q4_K_M")
        variant = quants.get(quant)
        if variant:
            models.append({
                "id": f"qwen3-{size}-{quant}",
                "label": f"Qwen3 {size} {quant}",
                "category": "translate",
                "downloaded": qwen._is_model_downloaded(size, quant),
                "size_mb": variant["size_mb"],
            })

    return {"tools": tools, "models": models}


@router.post("/models/download", response_model=DownloadResponse)
async def download_model(request: DownloadRequest):
    """下載指定工具或模型"""
    item_id = request.id

    _ensure_download_handler()
    manager = get_task_manager()
    task_id = await manager.submit(TASK_TYPE_DOWNLOAD, {"id": item_id})
    return DownloadResponse(task_id=task_id)


def _handle_download_task(params: dict, progress_callback) -> dict:
    """執行下載（在 executor 中執行）"""
    item_id = params["id"]

    # ── 二進位工具（realesrgan / waifu2x）──
    if item_id in TOOL_DIRS:
        url = TOOL_URLS[item_id]
        target_dir = TOOL_DIRS[item_id]()
        _download_and_extract_tool(item_id, url, target_dir, progress_callback)
        return {"id": item_id, "status": "installed"}

    # ── Whisper 語音模型 ──
    if item_id.startswith("whisper-"):
        size = item_id[len("whisper-"):]
        from backend.core.ai.whisper import get_whisper
        get_whisper().download_only(size, progress_callback)
        return {"id": item_id, "status": "downloaded"}

    # ── TranslateGemma 翻譯模型 ──
    if item_id.startswith("translategemma-"):
        rest = item_id[len("translategemma-"):]
        size, quant = rest.split("-", 1)
        from backend.core.ai.translategemma import get_translategemma
        get_translategemma()._download_model(size, quant, progress_callback)
        return {"id": item_id, "status": "downloaded"}

    # ── Qwen3 翻譯模型 ──
    if item_id.startswith("qwen3-"):
        rest = item_id[len("qwen3-"):]
        size, quant = rest.split("-", 1)
        from backend.core.ai.qwen3 import get_qwen3
        get_qwen3()._download_model(size, quant, progress_callback)
        return {"id": item_id, "status": "downloaded"}

    raise ValueError(f"未知的下載 ID: {item_id}")


# ── CUDA DLL 下載 ──────────────────────────────────────────────────────────────

TASK_TYPE_CUDA_DOWNLOAD = "setup.cuda_download"

# 需要下載的 PyPI 套件（包含 CUDA DLL）
# 按下載大小排序：runtime 最小，cublas 最大
CUDA_PACKAGES = [
    "nvidia-cuda-runtime-cu12",   # cudart64_12.dll  ~5 MB
    "nvidia-cublas-cu12",         # cublas64_12.dll + cublasLt64_12.dll  ~650 MB
    "nvidia-cudnn-cu12",          # cudnn DLLs  ~200 MB
]

_cuda_handler_registered = False


def _ensure_cuda_handler():
    global _cuda_handler_registered
    if _cuda_handler_registered:
        return
    manager = get_task_manager()
    manager.register_handler(TASK_TYPE_CUDA_DOWNLOAD, _handle_cuda_download_task)
    _cuda_handler_registered = True


@router.post("/cuda/download", response_model=DownloadResponse)
async def download_cuda():
    """下載 CUDA DLL（從 PyPI 取得，存至 AppData）"""
    _ensure_cuda_handler()
    manager = get_task_manager()
    task_id = await manager.submit(TASK_TYPE_CUDA_DOWNLOAD, {})
    return DownloadResponse(task_id=task_id)


def _handle_cuda_download_task(params: dict, progress_callback) -> dict:
    """從 PyPI 下載 CUDA wheel 並解壓 DLL 到 cuda_dir"""
    import json
    import os

    cuda_dir = get_cuda_dir()
    cuda_dir.mkdir(parents=True, exist_ok=True)

    n = len(CUDA_PACKAGES)

    for i, pkg in enumerate(CUDA_PACKAGES):
        base_pct = i / n
        slot = 1 / n

        progress_callback(base_pct, f"取得 {pkg} 資訊...")

        # 從 PyPI JSON API 取得 wheel 下載 URL
        api_url = f"https://pypi.org/pypi/{pkg}/json"
        try:
            with urllib.request.urlopen(api_url, timeout=15) as resp:
                data = json.loads(resp.read())
        except Exception as e:
            raise RuntimeError(f"無法取得 {pkg} 的 PyPI 資訊: {e}") from e

        # 找到 win_amd64 wheel
        wheel_url = None
        wheel_size = 0
        for file_info in data.get("urls", []):
            if (file_info.get("packagetype") == "bdist_wheel"
                    and "win_amd64" in file_info.get("filename", "")):
                wheel_url = file_info["url"]
                wheel_size = file_info.get("size", 0)
                break

        if not wheel_url:
            raise RuntimeError(f"找不到 {pkg} 的 Windows wheel")

        size_mb = wheel_size // (1024 * 1024)
        tmp_path = Path(tempfile.gettempdir()) / f"mediatranx_cuda_{pkg}.whl"

        def _reporthook(block_num: int, block_size: int, total_size: int):
            if total_size > 0:
                pct = min(block_num * block_size / total_size, 1.0)
                mb_done = (block_num * block_size) // (1024 * 1024)
                progress_callback(
                    base_pct + pct * slot * 0.9,
                    f"下載 {pkg}... {mb_done}/{size_mb} MB",
                )

        try:
            urllib.request.urlretrieve(wheel_url, str(tmp_path), _reporthook)
        except Exception as e:
            tmp_path.unlink(missing_ok=True)
            raise RuntimeError(f"下載 {pkg} 失敗: {e}") from e

        progress_callback(base_pct + slot * 0.9, f"解壓 {pkg} DLL...")

        try:
            with zipfile.ZipFile(tmp_path) as zf:
                for member in zf.namelist():
                    if member.lower().endswith(".dll"):
                        dll_name = Path(member).name
                        target = cuda_dir / dll_name
                        with zf.open(member) as src, open(target, "wb") as dst:
                            shutil.copyfileobj(src, dst)
        except Exception as e:
            raise RuntimeError(f"解壓 {pkg} 失敗: {e}") from e
        finally:
            tmp_path.unlink(missing_ok=True)

        progress_callback(base_pct + slot, f"{pkg} 完成")

    # 確保 cuda_dir 在 DLL 搜尋路徑中（下載後立即生效，不需重啟）
    cuda_dir_str = str(cuda_dir)
    current_path = os.environ.get("PATH", "")
    if cuda_dir_str not in current_path:
        os.environ["PATH"] = cuda_dir_str + os.pathsep + current_path
    try:
        os.add_dll_directory(cuda_dir_str)
    except (AttributeError, OSError):
        pass

    # 清除裝置偵測快取，讓下一次 /api/device 重新偵測 GPU
    from backend.core.device import refresh_device_cache
    refresh_device_cache()

    progress_callback(1.0, "CUDA 加速安裝完成")
    return {"status": "installed"}


def _download_and_extract_tool(
    tool_id: str,
    url: str,
    target_dir: Path,
    progress_callback,
) -> None:
    """下載 zip 並解壓至目標目錄（去除頂層資料夾）"""
    progress_callback(0.0, f"開始下載 {tool_id}...")

    tmp_path = Path(tempfile.gettempdir()) / f"mediatranx_{tool_id}.zip"

    def _reporthook(block_num: int, block_size: int, total_size: int):
        if total_size > 0:
            downloaded = block_num * block_size
            pct = min(downloaded / total_size, 1.0) * 0.8
            mb_done = downloaded // (1024 * 1024)
            mb_total = total_size // (1024 * 1024)
            progress_callback(pct, f"下載中... {mb_done} MB / {mb_total} MB")

    try:
        urllib.request.urlretrieve(url, str(tmp_path), _reporthook)
    except Exception as e:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError(f"下載失敗: {e}") from e

    progress_callback(0.8, "解壓縮中...")

    target_dir.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(tmp_path) as zf:
            members = zf.namelist()
            # 取得頂層資料夾名稱（第一個 member 的第一個路徑段）
            prefix = ""
            if members:
                top = members[0].split("/")[0]
                # 確認這個 prefix 是一個目錄（大多數 zip 都有）
                if top + "/" in members or all(m.startswith(top + "/") for m in members if m):
                    prefix = top + "/"

            for member in members:
                # 去除頂層目錄前綴
                rel = member[len(prefix):] if prefix and member.startswith(prefix) else member
                if not rel:
                    continue
                target_path = target_dir / rel
                if member.endswith("/"):
                    target_path.mkdir(parents=True, exist_ok=True)
                else:
                    target_path.parent.mkdir(parents=True, exist_ok=True)
                    with zf.open(member) as src, open(target_path, "wb") as dst:
                        shutil.copyfileobj(src, dst)
    except Exception as e:
        raise RuntimeError(f"解壓縮失敗: {e}") from e
    finally:
        tmp_path.unlink(missing_ok=True)

    progress_callback(1.0, "安裝完成")
