import os
import sys
from pathlib import Path

# 將 pip 安裝的 NVIDIA CUDA DLL 加入 PATH（Windows，僅 dev 模式）
# frozen 模式下 CUDA 由使用者系統環境提供，不需要 site-packages 路徑
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
