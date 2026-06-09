from app.adapters import compute_policy as cp
from app.adapters import device as dev
from app.utils import task_notices as tn


def _bind_sink():
    sink: list = []
    tn._current_task_notices.set(sink)
    return sink


def test_resolve_cuda_vram_ok_keeps_cuda(monkeypatch):
    sink = _bind_sink()
    monkeypatch.setattr(dev, "get_device", lambda: "cuda")
    monkeypatch.setattr(dev, "is_cpu_fallback_allowed", lambda: True)
    monkeypatch.setattr(dev, "fits_in_vram", lambda req: True)
    assert cp.resolve_device_for_task(3000, model_id="whisper-medium") == "cuda"
    assert sink == []


def test_resolve_cuda_vram_insufficient_downgrades_and_notifies(monkeypatch):
    sink = _bind_sink()
    monkeypatch.setattr(dev, "get_device", lambda: "cuda")
    monkeypatch.setattr(dev, "is_cpu_fallback_allowed", lambda: True)
    monkeypatch.setattr(dev, "fits_in_vram", lambda req: False)
    assert cp.resolve_device_for_task(3000, model_id="whisper-medium") == "cpu"
    assert sink == [{"code": "vram_insufficient", "params": {"model": "whisper-medium"}}]


def test_resolve_global_downgrade_notifies_once(monkeypatch):
    sink = _bind_sink()
    monkeypatch.setattr(dev, "get_device", lambda: "cpu")
    monkeypatch.setattr(dev, "get_global_downgrade_reason", lambda: "gpu_unsupported")
    reported = {"v": False}
    monkeypatch.setattr(dev, "is_global_downgrade_reported", lambda: reported["v"])
    monkeypatch.setattr(dev, "mark_global_downgrade_reported", lambda: reported.__setitem__("v", True))
    assert cp.resolve_device_for_task(3000, model_id="whisper-medium") == "cpu"
    assert sink == [{"code": "gpu_unsupported", "params": {}}]
    assert cp.resolve_device_for_task(0) == "cpu"
    assert len(sink) == 1


def test_resolve_off_no_vram_check(monkeypatch):
    sink = _bind_sink()
    monkeypatch.setattr(dev, "get_device", lambda: "cuda")
    monkeypatch.setattr(dev, "is_cpu_fallback_allowed", lambda: False)
    monkeypatch.setattr(dev, "fits_in_vram", lambda req: (_ for _ in ()).throw(AssertionError("called")))
    assert cp.resolve_device_for_task(99999, model_id="x") == "cuda"
    assert sink == []


def test_classify_gpu_error():
    assert cp.classify_gpu_error(RuntimeError("CUDA error: no kernel image is available")) == "gpu_unsupported"
    assert cp.classify_gpu_error(RuntimeError("CUDA out of memory. Tried to allocate")) == "vram_insufficient"
    assert cp.classify_gpu_error(ValueError("something else")) is None


def test_classify_gpu_error_llama_hard_crash():
    from app.adapters.binary.llama_server import LlamaServerCrashError
    hard = LlamaServerCrashError(code=3221225477, reason="ACCESS_VIOLATION (0xC0000005)",
                                 is_hard_crash=True)
    assert cp.classify_gpu_error(hard) == "gpu_unsupported"

    # graceful (non-hard) llama exit must NOT be classified as gpu_unsupported
    soft = LlamaServerCrashError(code=1, reason="exit code 1", is_hard_crash=False)
    assert cp.classify_gpu_error(soft) is None

    # survives wrapping: hard crash as __cause__ of a generic RuntimeError
    wrapped = RuntimeError("load failed")
    wrapped.__cause__ = hard
    assert cp.classify_gpu_error(wrapped) == "gpu_unsupported"
