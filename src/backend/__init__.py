import uvicorn
from fastapi import FastAPI

from backend.api import build_router


def start_server(port):
    app: FastAPI = FastAPI(docs_url=None)
    app = build_router(app)
    uvicorn.run(app, host="localhost", port=port)


# app: FastAPI = FastAPI(docs_url=None)
# app = build_router(app)