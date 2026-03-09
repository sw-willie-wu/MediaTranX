"""
統一路徑解析模組 (REFACTOR V4)
偵測 sys.frozen 決定 dev 或 packaged 模式，提供各目錄路徑。
支援透過 MEDIATRANX_HOME 環境變數自定義數據目錄。
"""
import sys
import os
import json
from pathlib import Path


def _is_frozen() -> bool:
    """是否為編譯後的執行檔 (Nuitka 或 PyInstaller)"""
    # 1. 檢查標準打包標記
    if getattr(sys, 'frozen', False) or hasattr(sys, "nuitka_binary"):
        return True
    # 2. 檢查 Nuitka 全域變數
    if "__compiled__" in globals():
        return True
    # 3. 強制檢查執行檔檔名與路徑位置 (針對 Windows 打包環境)
    exe_path = sys.executable.lower()
    if exe_path.endswith('core.exe') or ('resources' in exe_path and 'python.exe' not in exe_path):
        return True
    return False


def _get_internal_dir() -> Path:
    """編譯模式下取得內部資源路徑 (sys._MEIPASS 或執行檔所在目錄)"""
    # Nuitka onefile 模式也會設置 sys._MEIPASS
    return Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))


def get_base_data_dir() -> Path:
    """
    取得基礎數據目錄 (預設為 %APPDATA%/MediaTranX)
    支援透過環境變數 MEDIATRANX_HOME 自定義。
    """
    custom_home = os.environ.get('MEDIATRANX_HOME')
    if custom_home:
        path = Path(custom_home)
    elif _is_frozen():
        appdata = os.environ.get('APPDATA', str(Path.home() / 'AppData' / 'Roaming'))
        path = Path(appdata) / 'MediaTranX'
    else:
        path = _get_app_root()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _get_app_root() -> Path:
    """
    取得應用程式安裝根目錄 (MediaTranX/)
    """
    if _is_frozen():
        # core.exe 位於 resources/core_service/core.exe
        return Path(sys.executable).parent.parent.parent
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
        # ffmpeg 位於與 core_service 同層的 resources/ 下
        return Path(sys.executable).parent.parent.parent / "ffmpeg"
    else:
        return _get_app_root() / "bin" / "ffmpeg"


def get_app_config() -> dict:
    """讀取應用程式設定 (%APPDATA%/MediaTranX/config.json)"""
    config_path = get_base_data_dir() / "config.json"
    try:
        if config_path.exists():
            return json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def save_app_config(config: dict) -> None:
    """寫入應用程式設定"""
    config_path = get_base_data_dir() / "config.json"
    config_path.write_text(
        json.dumps(config, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def get_models_dir(category: str = "") -> Path:
    """
    模型倉庫目錄
    優先使用 config.json 中的 models_dir，否則預設 %APPDATA%/MediaTranX/models/
    """
    config = get_app_config()
    custom = config.get("models_dir", "").strip()
    d = Path(custom) if custom else get_base_data_dir() / "models"
    if category:
        d = d / category
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_venv_dir() -> Path:
    """AI 推理環境目錄 (%APPDATA%/MediaTranX/.venv)"""
    return get_base_data_dir() / ".venv"


def get_temp_dir() -> Path:
    """暫存目錄，優先使用 config.json 中的 temp_dir，否則預設 %APPDATA%/MediaTranX/temp/"""
    config = get_app_config()
    custom = config.get("temp_dir", "").strip()
    d = Path(custom) if custom else get_base_data_dir() / "temp"
    d.mkdir(parents=True, exist_ok=True)
    return d


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
        d = get_base_data_dir() / "output"
        d.mkdir(parents=True, exist_ok=True)
        return d


def get_static_dir() -> Path:
    """
    前端靜態檔目錄
    Packaged: core_service/backend/static/
    Dev:      src/backend/static/
    """
    if _is_frozen():
        return Path(sys.executable).parent / "backend" / "static"
    else:
        return Path(__file__).parent.parent / "static"


# --- Deprecated (即將移除) ---
def get_waifu2x_dir() -> Path:
    """[DEPRECATED] 改用純 Python 推理"""
    return _get_app_root() / "bin" / "waifu2x"

def get_realesrgan_dir() -> Path:
    """[DEPRECATED] 改用純 Python 推理"""
    return _get_app_root() / "bin" / "realesrgan"

def get_cuda_dir() -> Path:
    """[DEPRECATED] CUDA 現在由 uv 管理在 .venv 內"""
    return get_base_data_dir() / "cuda"
