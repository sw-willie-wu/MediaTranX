from pathlib import Path

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
