"""suppress_results：pipeline 中間產物不進 Results drawer（本 session 與重啟後）。

參數化 guard：22 條 route（21 白名單工具 + video.download source）的 request model
都必須有 suppress_results 欄位——任一 route 漏加，Pydantic 會靜默丟棄旗標 → 中間檔洩漏。
"""
import asyncio
import importlib

import pytest
from pydantic import BaseModel

from app.workers.progress_tracker import ProgressTracker
from app.workers.task_manager import TaskManager

# (module, request model 判別欄位) — file_id 型工具 + url 型 source
_ROUTE_MODULES = [
    "app.api.routes.audio.transcode",
    "app.api.routes.audio.lyrics",
    "app.api.routes.audio.separate",
    "app.api.routes.audio.transcribe",
    "app.api.routes.audio.volume",
    "app.api.routes.video.transcode",
    "app.api.routes.video.enhance",
    "app.api.routes.video.interpolate",
    "app.api.routes.video.summary",
    "app.api.routes.video.download",
    "app.api.routes.image.compress",
    "app.api.routes.image.convert",
    "app.api.routes.image.filter",
    "app.api.routes.image.ocr",
    "app.api.routes.image.remove_bg",
    "app.api.routes.image.upscale",
    "app.api.routes.document.ocr",
    "app.api.routes.document.pdf_convert",
    "app.api.routes.document.split",
    "app.api.routes.document.translate",
]


def _submit_request_models(module_name: str) -> list[type[BaseModel]]:
    """route 模組內的提交型 request model（有 file_id 或 url 欄位者）。"""
    mod = importlib.import_module(module_name)
    found = []
    for obj in vars(mod).values():
        if (isinstance(obj, type) and issubclass(obj, BaseModel)
                and obj is not BaseModel
                and ("file_id" in obj.model_fields or "url" in obj.model_fields)
                and "task_id" not in obj.model_fields):
            found.append(obj)
    return found


@pytest.mark.parametrize("module_name", _ROUTE_MODULES)
def test_route_request_models_carry_suppress_results(module_name):
    models = _submit_request_models(module_name)
    assert models, f"{module_name}: no submit request model found"
    for m in models:
        assert "suppress_results" in m.model_fields, (
            f"{module_name}.{m.__name__} missing suppress_results — "
            f"Pydantic will silently drop the pipeline flag (M1 leak)"
        )
        assert m.model_fields["suppress_results"].default is False


class _FakeFd:
    def __init__(self, filename):
        self.filename = filename
        self.metadata = None


class _FakeFs:
    def __init__(self):
        self.files = {}
        self.sidecars = []

    def get_file(self, fid):
        return self.files.get(fid)

    def write_sidecar(self, fid):
        self.sidecars.append(fid)


def _run_task(suppress: bool, policy: str = "results"):
    fs = _FakeFs()
    fs.files["out1"] = _FakeFd("out.gif")
    tm = TaskManager(progress_tracker=ProgressTracker(), file_service=fs)
    tm.register_handler("test.tool", lambda p, cb: {"output_file_id": "out1"}, output_policy=policy)

    async def run():
        tid = await tm.submit("test.tool", {"file_id": "in1"}, suppress_results=suppress)
        for _ in range(100):
            await asyncio.sleep(0.02)
            t = tm.get_task(tid)
            if t and t.status.value in ("completed", "failed"):
                return t
        raise AssertionError("task did not finish")

    task = asyncio.run(run())
    assert task.status.value == "completed"
    return fs


def test_suppressed_output_gets_explicit_false_sidecar():
    fs = _run_task(suppress=True, policy="results")
    assert fs.files["out1"].metadata["show_in_results"] is False
    assert "out1" in fs.sidecars  # 一律寫 sidecar，重啟路徑靠顯式 false


def test_suppressed_history_policy_also_writes_sidecar():
    fs = _run_task(suppress=True, policy="history")
    assert fs.files["out1"].metadata["show_in_results"] is False
    assert "out1" in fs.sidecars  # history policy 本來不寫 sidecar，suppress 必須強制寫


def test_unsuppressed_behavior_unchanged():
    fs = _run_task(suppress=False, policy="results")
    assert fs.files["out1"].metadata["show_in_results"] is True
    assert "out1" in fs.sidecars
