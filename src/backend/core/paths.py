"""
統一路徑解析模組
偵測 sys.frozen 決定 dev 或 packaged 模式，提供各目錄路徑
"""
import sys
from pathlib import Path


def _is_frozen() -> bool:
    return getattr(sys, 'frozen', False)


def _get_internal_dir() -> Path:
    """PyInstaller onedir 模式下 datas 解壓到 _internal/ (即 sys._MEIPASS)"""
    return Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))


def _get_app_root() -> Path:
    """
    取得應用程式根目錄

    Packaged: backend.exe 位於 resources/backend/，安裝根目錄在上兩層
              即 MediaTranX/resources/backend/backend.exe → MediaTranX/
    Dev:      src/backend/core/paths.py → 往上 4 層到專案根目錄
    """
    if _is_frozen():
        # sys.executable = .../MediaTranX/resources/backend/backend.exe
        return Path(sys.executable).parent.parent.parent
    else:
        return Path(__file__).parent.parent.parent.parent


def get_ffmpeg_dir() -> Path:
    """
    FFmpeg 二進位目錄

    Packaged: resources/ffmpeg/
    Dev:      bin/ffmpeg/
    """
    if _is_frozen():
        return Path(sys.executable).parent.parent / "ffmpeg"
    else:
        return _get_app_root() / "bin" / "ffmpeg"


def get_models_dir(name: str) -> Path:
    """
    模型下載目錄（可寫入）

    Packaged & Dev: {app_root}/models/{name}/
    """
    d = _get_app_root() / "models" / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_static_dir() -> Path:
    """
    前端靜態檔目錄

    Packaged: _internal/static/ (sys._MEIPASS/static/)
    Dev:      src/backend/static/
    """
    if _is_frozen():
        return _get_internal_dir() / "static"
    else:
        return Path(__file__).parent.parent / "static"


def get_temp_dir() -> Path:
    """暫存目錄"""
    d = _get_app_root() / "temp"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_waifu2x_dir() -> Path:
    """
    waifu2x-ncnn-vulkan 二進位目錄

    Packaged: resources/waifu2x/
    Dev:      bin/waifu2x/
    """
    if _is_frozen():
        return Path(sys.executable).parent.parent / "waifu2x"
    else:
        return _get_app_root() / "bin" / "waifu2x"


def get_realesrgan_dir() -> Path:
    """
    Real-ESRGAN ncnn-vulkan 二進位目錄

    Packaged: resources/realesrgan/
    Dev:      bin/realesrgan/
    """
    if _is_frozen():
        return Path(sys.executable).parent.parent / "realesrgan"
    else:
        return _get_app_root() / "bin" / "realesrgan"


def get_cuda_dir() -> Path:
    """
    CUDA DLL 目錄（使用者資料，跨版本保存）

    %APPDATA%/MediaTranX/cuda/
    此目錄在應用程式更新後仍然保留，不需要重複下載。
    """
    import os
    appdata = os.environ.get('APPDATA', str(Path.home() / 'AppData' / 'Roaming'))
    return Path(appdata) / 'MediaTranX' / 'cuda'


def get_output_dir() -> Path:
    """輸出目錄"""
    d = _get_app_root() / "output"
    d.mkdir(parents=True, exist_ok=True)
    return d
