"""
FastAPI 應用程式與服務進入點
整合環境注入、App 定義與 Uvicorn 啟動邏輯。
"""
import os
import sys
import logging
from pathlib import Path

# --- 0. 修正編譯後的導入路徑 ---
if getattr(sys, 'frozen', False):
    # 打包後，讓程式能找到同目錄下的模組
    _internal_path = os.path.dirname(sys.executable)
    if _internal_path not in sys.path:
        sys.path.insert(0, _internal_path)

from fastapi import FastAPI

# --- 1. 環境與環境路徑注入 (BUILD_STRATEGY.md) ---
_appdata = os.environ.get('APPDATA', '')
if _appdata:
    # 注入外部 .venv site-packages
    _venv_site = os.path.join(_appdata, 'MediaTranX', '.venv', 'Lib', 'site-packages')
    if os.path.isdir(_venv_site):
        # 使用 append 而非 insert(0)，確保優先使用內建包，避免 ssl 等核心包衝突
        if _venv_site not in sys.path:
            sys.path.append(_venv_site)
        
        # 處理 torch 等 DLL
        _torch_lib = os.path.join(_venv_site, 'torch', 'lib')
        if os.path.isdir(_torch_lib) and hasattr(os, 'add_dll_directory'):
            try: os.add_dll_directory(_torch_lib)
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
if getattr(sys, 'frozen', False):
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

# --- 3. App 定義與路由掛載 ---
from backend.api import build_router

app: FastAPI = FastAPI(title="MediaTranX API")
app = build_router(app)

# --- 4. 服務啟動邏輯 ---
if __name__ == "__main__":
    import uvicorn
    # 打包後 backend.exe 直接執行此處
    # 開發模式下 Electron main.js 也可透過 `python -m backend.main` 啟動
    uvicorn.run(app, host="127.0.0.1", port=8001, log_level="info")
