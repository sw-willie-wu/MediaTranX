"""
FastAPI 應用程式與服務進入點
整合環境注入、App 定義與 Uvicorn 啟動邏輯。
"""
import os
import sys
import logging
from pathlib import Path

# --- 0. 偵測編譯模式 ---
IS_FROZEN = getattr(sys, 'frozen', False) or "__compiled__" in globals() or hasattr(sys, "nuitka_binary")

# --- 1. 修正編譯後的導入路徑 ---
if IS_FROZEN:
    # 打包後，讓程式能找到同目錄下的模組
    _internal_path = os.path.dirname(sys.executable)
    if _internal_path not in sys.path:
        sys.path.insert(0, _internal_path)

# --- 相容層：torchvision >= 0.16 移除了 functional_tensor 模組 ---
import types as _types
try:
    import torchvision.transforms.functional_tensor  # noqa: F401
except ImportError:
    import torchvision.transforms.functional as _tvf
    _compat = _types.ModuleType("torchvision.transforms.functional_tensor")
    for _attr in dir(_tvf):
        setattr(_compat, _attr, getattr(_tvf, _attr))
    sys.modules["torchvision.transforms.functional_tensor"] = _compat

from fastapi import FastAPI

# --- 2. 環境與環境路徑注入 (BUILD_STRATEGY.md) ---
_appdata = os.environ.get('APPDATA', str(Path.home() / 'AppData' / 'Roaming'))
if _appdata:
    # 注入外部 .venv site-packages（即使目錄尚不存在也先加入，安裝後即可 import）
    _venv_site = os.path.join(_appdata, 'MediaTranX', '.venv', 'Lib', 'site-packages')
    if _venv_site not in sys.path:
        sys.path.append(_venv_site)

    # 處理 Python 套件 DLL（需目錄存在才能 add_dll_directory）
    # python.exe 啟動時會自動把自己的目錄加入 DLL 搜尋，core.exe 不會，需手動補齊
    if hasattr(os, 'add_dll_directory'):
        _venv_base = os.path.join(_appdata, 'MediaTranX', '.venv')
        _dll_dirs = [
            os.path.join(_venv_base, 'Scripts'),           # python312.dll 等
            os.path.join(_venv_site, 'torch', 'lib'),      # torch CUDA DLL
            os.path.join(_venv_site, 'ctranslate2'),        # ctranslate2 DLL（faster-whisper 底層）
            os.path.join(_venv_site, 'tokenizers'),         # tokenizers .pyd 同層 DLL
            os.path.join(_venv_site, 'llama_cpp'),          # 部分 wheel DLL 在此
            os.path.join(_venv_site, 'llama_cpp', 'lib'),  # 官方 wheel DLL 在此
        ]
        for _d in _dll_dirs:
            if os.path.isdir(_d):
                try: os.add_dll_directory(_d)
                except Exception: pass

        # 動態掃描 site-packages 下所有 .libs 目錄（delvewheel 打包慣例）
        # av.libs, numpy.libs, scipy.libs, llvmlite.libs ... 等均需加入
        if os.path.isdir(_venv_site):
            try:
                for _entry in os.scandir(_venv_site):
                    if _entry.is_dir() and _entry.name.endswith('.libs'):
                        try: os.add_dll_directory(_entry.path)
                        except Exception: pass
            except Exception: pass

        # 從 pyvenv.cfg 讀取 base Python 安裝目錄（uv 管理，含 vcruntime140.dll）
        # 外部 .pyd 連結 vcruntime140.dll 時，這個目錄必須在搜尋路徑中
        _pyvenv_cfg = os.path.join(_venv_base, 'pyvenv.cfg')
        if os.path.isfile(_pyvenv_cfg):
            try:
                with open(_pyvenv_cfg, 'r', encoding='utf-8') as _f:
                    for _line in _f:
                        if _line.lower().startswith('home'):
                            _py_home = _line.split('=', 1)[1].strip()
                            if os.path.isdir(_py_home):
                                try: os.add_dll_directory(_py_home)
                                except Exception: pass
                            break
            except Exception: pass

# CUDA DLL 路徑注入 (Windows)
if sys.platform == "win32" and _appdata:
    _cuda_dir = os.path.join(_appdata, 'MediaTranX', 'cuda')
    if os.path.isdir(_cuda_dir):
        os.environ["PATH"] = _cuda_dir + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, 'add_dll_directory'):
            try: os.add_dll_directory(_cuda_dir)
            except Exception: pass

# --- 2. 日誌配置 ---
if not getattr(sys, 'frozen', False):
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    )
if IS_FROZEN:
    log_dir = Path(_appdata) / 'MediaTranX'
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / 'backend_internal.log'
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
        handlers=[
            logging.FileHandler(str(log_path), encoding='utf-8'),
            logging.StreamHandler(),
        ],
    )
    logging.info(f"Backend started in frozen mode. Log: {log_path}")

# --- 3. 啟動診斷 (Diagnostic) ---
if IS_FROZEN:
    try:
        import llama_cpp
        logging.info("Startup Diagnostic: llama-cpp-python imported successfully.")
    except Exception as e:
        logging.error(f"Startup Diagnostic: llama-cpp-python import failed: {e}")
        # 嘗試印出環境變數
        logging.info(f"Startup Diagnostic: PATH={os.environ.get('PATH', '')}")

from backend.api import build_router

app: FastAPI = FastAPI(title="MediaTranX API")
app = build_router(app)

# --- 4. 服務啟動邏輯 ---
if __name__ == "__main__":
    import uvicorn
    import argparse

    parser = argparse.ArgumentParser(description="MediaTranX Backend")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host to listen on")
    parser.add_argument("--port", type=int, default=8001, help="Port to listen on")
    args = parser.parse_args()

    # 執行後端服務
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")
