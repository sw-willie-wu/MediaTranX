"""Registry format constants for the de-torch migration (NCNN beside ONNX)."""
from app.adapters.ai import registry


def test_format_constants_present_and_uppercase():
    assert registry.FORMAT_ONNX == "ONNX"   # pre-existing (registry.py:14), reused as-is
    assert registry.FORMAT_NCNN == "NCNN"   # added by this task; uppercase to match siblings
    # FORMAT_NCNN must be distinct from every existing format constant
    assert registry.FORMAT_NCNN not in {
        registry.FORMAT_PTH, registry.FORMAT_GGUF, registry.FORMAT_PKG, registry.FORMAT_ONNX,
    }
