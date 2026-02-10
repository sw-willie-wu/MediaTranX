"""
功能安裝 API 路由
讓使用者一鍵安裝可選功能所需的 Python 套件
"""
import logging
import subprocess
import sys
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from backend.core.device import has_nvidia_gpu
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
