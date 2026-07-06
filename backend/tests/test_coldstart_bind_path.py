"""AC-V1 regression guard: importing app.main (= the bind-blocking startup path:
bootstrap() + init_container(), main.py lines 6 & 10) must NOT load the heavy AI
libraries. They belong in the post-bind background warmup / first model load.

This locks in the cold-start win (compat deferral + lazy llm + no eager wrapper
loop). A subprocess is required because the full test run loads torch etc. into
the parent process — an in-process check would be a vacuous pass.
"""
import subprocess
import sys
import textwrap
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_import_app_main_does_not_load_heavy_modules_on_bind_path():
    r = subprocess.run(
        [sys.executable, "-c", textwrap.dedent("""
            import sys
            import app.main  # runs bootstrap() + init_container() at module import
            heavy = [m for m in ("torch", "torchvision", "scipy.signal", "scipy.stats")
                     if m in sys.modules]
            print(",".join(heavy))
        """)],
        capture_output=True, text=True, cwd=str(_BACKEND_ROOT), timeout=120,
    )
    assert r.returncode == 0, r.stderr
    assert r.stdout.strip() == "", f"bind path pulled heavy modules: {r.stdout.strip()}"
