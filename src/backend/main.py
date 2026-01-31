import os
import sys
from pathlib import Path

# 將 pip 安裝的 NVIDIA CUDA DLL 加入 PATH（Windows）
if sys.platform == "win32":
    _site_packages = Path(sys.prefix) / "Lib" / "site-packages"
    _nvidia_dirs = [str(p) for p in _site_packages.glob("nvidia/*/bin") if p.is_dir()]
    if _nvidia_dirs:
        os.environ["PATH"] = os.pathsep.join(_nvidia_dirs) + os.pathsep + os.environ.get("PATH", "")

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from backend.api import build_router


# 靜態檔案目錄
static_dir = Path(__file__).parent / 'static'

# 建立 FastAPI 應用
app: FastAPI = FastAPI(docs_url=None)
app = build_router(app)

# 掛載靜態檔案（生產模式用）
if static_dir.exists():
    app.mount("/static", StaticFiles(directory=static_dir, html=True), name="static")
