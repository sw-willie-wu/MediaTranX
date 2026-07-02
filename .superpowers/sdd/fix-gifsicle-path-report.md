# Fix: gifsicle-path-packaged

## Resolver code (`_resolve_gifsicle`)

```python
def _resolve_gifsicle() -> Optional[str]:
    exe_suffix = sysconfig.get_config_var("EXE") or ""  # ".exe" on Win, "" on posix

    # 1. PATH (works in dev)
    candidate = shutil.which("gifsicle")
    if candidate and os.path.isfile(candidate):
        return candidate

    # 2. Derive from gifsicle_bin.__file__ (packaged-build fallback)
    try:
        import gifsicle_bin
        pkg_init = Path(gifsicle_bin.__file__)      # …/gifsicle_bin/__init__.py
        site_packages = pkg_init.parent.parent       # …/Lib/site-packages
        venv_root = site_packages.parent.parent      # venv root
        for scripts_dir in ("Scripts", "bin"):
            binary = venv_root / scripts_dir / f"gifsicle{exe_suffix}"
            if binary.is_file():
                return str(binary)
    except Exception:
        pass

    # 3. sysconfig best-effort last resort
    try:
        scripts = sysconfig.get_path("scripts")
        if scripts:
            binary = os.path.join(scripts, f"gifsicle{exe_suffix}")
            if os.path.isfile(binary):
                return binary
    except Exception:
        pass

    return None
```

## How the venv Scripts path is derived

`gifsicle_bin.__file__` points at `<venv>/Lib/site-packages/gifsicle_bin/__init__.py`.
Two `parent` steps reach `<venv>/Lib/site-packages` → two more reach the venv root.
The binary lives at `<venv>/Scripts/gifsicle.exe` (Windows) or `<venv>/bin/gifsicle` (posix).
This derivation is reliable under the frozen `core.exe` because the app imports `gifsicle_bin`
from the runtime venv's site-packages, regardless of the frozen process's `sys.prefix`.

## Construction change

`GifsicleWrapper.__init__` no longer raises. `self._path` may be `None`.
`compress()` raises `GifsicleNotFound` at the top if `self._path is None`.
This ensures PNG/JPEG/WebP compress (which never calls gifsicle) is unaffected
when the DI Singleton is constructed at app start.

## pytest output

```
backend/tests/adapters/test_gifsicle_wrapper.py — 8 passed in 0.12s
  test_build_args_lossy_and_optimize          PASSED
  test_optimize_transparency_off_uses_O2      PASSED
  test_coalesce_uses_unoptimize               PASSED
  test_real_compress_shrinks_and_preserves_animation  PASSED
  test_frame_drop_reduces_frame_count         PASSED
  test_construction_never_raises_when_unresolvable    PASSED  ← new
  test_compress_raises_when_unresolvable              PASSED  ← new
  test_resolver_falls_back_to_gifsicle_bin_wheel      PASSED  ← new regression test

backend/tests/services/test_compress_service.py — 6 passed in 0.62s
  test_png_lossy_compress_shrinks             PASSED
  test_png_lossless_compress_shrinks_or_equal PASSED
  test_jpeg_compress_shrinks                  PASSED
  test_webp_lossy_shrinks                     PASSED
  test_webp_lossless_valid                    PASSED
  test_gif_compress_shrinks_and_stays_animated PASSED
```

Total: 14 passed, 0 failed.
