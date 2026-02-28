"""
統一路徑解析模組
偵測 sys.frozen 決定 dev 或 packaged 模式，提供各目錄路徑
"""
import sys
import os
from pathlib import Path


def _is_frozen() -> bool:
    """是否為編譯後的執行檔 (Nuitka 或 PyInstaller)"""
    return getattr(sys, 'frozen', False)


def _get_internal_dir() -> Path:
    """編譯模式下取得內部資源路徑 (sys._MEIPASS 或執行檔所在目錄)"""
    # Nuitka onefile 模式也會設置 sys._MEIPASS
    return Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))


def _get_app_root() -> Path:
    """
    取得應用程式根目錄 (MediaTranX/)

    Packaged (Standalone): 
        core.exe 位於 resources/core_engine/main.dist/core.exe
        安裝根目錄在往上 4 層
    Dev:      
        src/backend/core/paths.py → 往上 4 層到專案根目錄
    """
    if _is_frozen():
        # sys.executable = .../MediaTranX/resources/core_engine/main.dist/core.exe
        return Path(sys.executable).parent.parent.parent.parent
    else:
        # __file__ = .../src/backend/core/paths.py
        return Path(__file__).parent.parent.parent.parent


def get_ffmpeg_dir() -> Path:
    """
    FFmpeg 二進位目錄

    Packaged: resources/ffmpeg/
    Dev:      bin/ffmpeg/
    """
    if _is_frozen():
        # 假設 backend.exe 與 ffmpeg/ 同在 resources/ 下
        return Path(sys.executable).parent / "ffmpeg"
    else:
        return _get_app_root() / "bin" / "ffmpeg"


def get_models_dir(name: str) -> Path:
    """
    模型下載目錄（可寫入，優先使用 APPDATA 以跨版本保留）

    Packaged & Dev: %APPDATA%/MediaTranX/models/{name}/
    """
    appdata = os.environ.get('APPDATA', str(Path.home() / 'AppData' / 'Roaming'))
    d = Path(appdata) / 'MediaTranX' / 'models' / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_static_dir() -> Path:
    """
    前端靜態檔目錄 (打包時編譯進 backend.exe 或放在內部)

    Packaged: _internal/static/
    Dev:      src/backend/static/
    """
    if _is_frozen():
        return _get_internal_dir() / "static"
    else:
        return Path(__file__).parent.parent / "static"


def get_temp_dir() -> Path:
    """暫存目錄 (%APPDATA%/MediaTranX/temp/)"""
    appdata = os.environ.get('APPDATA', str(Path.home() / 'AppData' / 'Roaming'))
    d = Path(appdata) / 'MediaTranX' / 'temp'
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_waifu2x_dir() -> Path:
    """
    waifu2x-ncnn-vulkan 二進位目錄

    Packaged: resources/waifu2x/
    Dev:      bin/waifu2x/
    """
    if _is_frozen():
        return Path(sys.executable).parent / "waifu2x"
    else:
        return _get_app_root() / "bin" / "waifu2x"


def get_realesrgan_dir() -> Path:
    """
    Real-ESRGAN ncnn-vulkan 二進位目錄

    Packaged: resources/realesrgan/
    Dev:      bin/realesrgan/
    """
    if _is_frozen():
        return Path(sys.executable).parent / "realesrgan"
    else:
        return _get_app_root() / "bin" / "realesrgan"


def get_cuda_dir() -> Path:
    """
    CUDA DLL 目錄 (%APPDATA%/MediaTranX/cuda/)
    """
    appdata = os.environ.get('APPDATA', str(Path.home() / 'AppData' / 'Roaming'))
    return Path(appdata) / 'MediaTranX' / 'cuda'


def get_output_dir() -> Path:
    """輸出目錄 (預設為 AppRoot/output，若無權限則回退至 APPDATA)"""
    try:
        d = _get_app_root() / "output"
        d.mkdir(parents=True, exist_ok=True)
        # 測試是否可寫入
        test_file = d / ".test"
        test_file.touch()
        test_file.unlink()
        return d
    except (PermissionError, OSError):
        appdata = os.environ.get('APPDATA', str(Path.home() / 'AppData' / 'Roaming'))
        d = Path(appdata) / 'MediaTranX' / 'output'
        d.mkdir(parents=True, exist_ok=True)
        return d
