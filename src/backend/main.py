"""
FastAPI 應用程式定義
建立 FastAPI app 實例並掛載所有路由。
開發模式由 Electron 主進程透過 uvicorn 啟動；打包模式由 run_server.py 作為進入點。
"""
import os
import sys
from pathlib import Path

# 將 %APPDATA%/MediaTranX/cuda/ 加入 DLL 搜尋路徑（Windows，dev + frozen）
# CUDA DLL 由設定頁面「硬體加速」功能下載後存放於此，下載後不需重啟即可生效
if sys.platform == "win32":
    _appdata = os.environ.get('APPDATA', '')
    if _appdata:
        _cuda_dir = os.path.join(_appdata, 'MediaTranX', 'cuda')
        # 1. PATH（舊方式，相容性用）
        os.environ["PATH"] = _cuda_dir + os.pathsep + os.environ.get("PATH", "")
        # 2. AddDllDirectory（Windows 現代 API，比 PATH 更可靠，frozen 環境也有效）
        if os.path.isdir(_cuda_dir):
            try:
                os.add_dll_directory(_cuda_dir)
            except (AttributeError, OSError):
                pass

# 將 pip 安裝的 NVIDIA CUDA DLL 加入 PATH（Windows，僅 dev 模式）
if sys.platform == "win32" and not getattr(sys, 'frozen', False):
    _site_packages = Path(sys.prefix) / "Lib" / "site-packages"
    _nvidia_dirs = [str(p) for p in _site_packages.glob("nvidia/*/bin") if p.is_dir()]
    if _nvidia_dirs:
        os.environ["PATH"] = os.pathsep.join(_nvidia_dirs) + os.pathsep + os.environ.get("PATH", "")

from fastapi import FastAPI

from backend.api import build_router


# 建立 FastAPI 應用
app: FastAPI = FastAPI()
app = build_router(app)
