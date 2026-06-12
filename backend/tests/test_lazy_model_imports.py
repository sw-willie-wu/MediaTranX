"""
Regression guard: startup-eager modules must NOT import heavy model libraries
at module-import time.

Root cause of the v1.5.0 production crash: `init_container()` eagerly instantiates
all AI wrappers, which imported their module; `basic_pitch.py` did a top-level
`from basic_pitch import ICASSP_2022_MODEL_PATH`, and the basic-pitch package's
own __init__ hard-crashes (NameError) when onnxruntime can't load (missing/old
msvcp140.dll). One optional feature's broken dependency killed the whole backend.

These tests assert that importing each startup-eager module does NOT pull in its
heavy model library. The library must only load lazily, inside the method that
actually uses it, so a missing/broken dependency degrades a single feature instead
of crashing backend startup.

Why subprocess: the full backend test run (incl. real-AI tests) imports
faster_whisper / transformers / soundfile into the parent process's sys.modules.
An in-process `lib in sys.modules` check would be silently skipped (vacuous pass)
once any prior test loaded the lib. A clean child interpreter is the only reliable
way to prove the wrapper module itself doesn't trigger the import.
"""
import subprocess
import sys
from pathlib import Path

import pytest

# backend/ root: this file is backend/tests/test_lazy_model_imports.py
_BACKEND_ROOT = Path(__file__).resolve().parents[1]

# (module that is eager-imported at startup, heavy model lib that must NOT be
#  pulled in transitively when that module is imported)
_CASES = [
    ("app.adapters.ai.wrapper.basic_pitch", "basic_pitch"),
    ("app.adapters.ai.wrapper.whisper", "faster_whisper"),
    ("app.adapters.ai.wrapper.wav2vec2", "transformers"),
    ("app.adapters.ai.wrapper.wav2vec2", "soundfile"),
    ("app.services.setup.model_download_service", "soundfile"),
    ("app.adapters.ai.wrapper.base", "onnxruntime"),
]


@pytest.mark.parametrize("module, heavy_lib", _CASES)
def test_module_does_not_eager_import_heavy_lib(module, heavy_lib):
    """Importing `module` in a clean interpreter must not import `heavy_lib`."""
    code = (
        f"import sys\n"
        f"import {module}\n"
        f"assert {heavy_lib!r} not in sys.modules, "
        f"{f'{module} eager-imports {heavy_lib}'!r}\n"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        cwd=str(_BACKEND_ROOT),  # `-c` puts cwd on sys.path so `import app...` resolves
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"{module} should not eager-import {heavy_lib}.\n"
        f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
