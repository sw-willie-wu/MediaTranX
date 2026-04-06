"""
Runtime environment setup for production mode.

Two phases:
1. inject_paths() — called at import time, before any third-party import.
   Adds .venv/site-packages to sys.path so pydantic etc. are importable.
2. register_dlls(settings) — called at bootstrap, after settings are loaded.
   Registers DLL search directories for Windows frozen mode.
"""
import glob
import os
import sys


# ---------------------------------------------------------------------------
# Phase 1: sys.path injection (stdlib only, called before pydantic)
# ---------------------------------------------------------------------------

def inject_paths():
    """Add .venv/site-packages to sys.path if MEDIATRANX_PATH__VENV is set."""
    venv = os.environ.get('MEDIATRANX_PATH__VENV')
    if not venv:
        return

    if sys.platform == 'win32':
        site_packages = os.path.join(venv, 'Lib', 'site-packages')
        exe_dir = os.path.dirname(sys.executable)
        # Register DLL search dirs BEFORE any .pyd import
        os.environ['PATH'] = exe_dir + os.pathsep + site_packages + os.pathsep + os.environ.get('PATH', '')
        if hasattr(os, 'add_dll_directory'):
            for d in [exe_dir, site_packages, os.path.join(venv, 'Scripts')]:
                if os.path.isdir(d):
                    os.add_dll_directory(d)
            # Original Python home (where .pyd files were compiled against)
            pyvenv_cfg = os.path.join(venv, 'pyvenv.cfg')
            if os.path.isfile(pyvenv_cfg):
                with open(pyvenv_cfg, encoding='utf-8') as f:
                    for line in f:
                        if line.lower().startswith('home'):
                            py_home = line.split('=', 1)[1].strip()
                            if os.path.isdir(py_home):
                                os.add_dll_directory(py_home)
                            break
            # Scan *.libs dirs (delvewheel convention)
            try:
                for entry in os.scandir(site_packages):
                    if entry.is_dir() and entry.name.endswith('.libs'):
                        os.add_dll_directory(entry.path)
            except Exception:
                pass
    else:
        matches = glob.glob(os.path.join(venv, 'lib', 'python3.*', 'site-packages'))
        site_packages = matches[0] if matches else os.path.join(venv, 'lib', 'python3.12', 'site-packages')

    if site_packages not in sys.path:
        sys.path.insert(0, site_packages)


# ---------------------------------------------------------------------------
# Phase 2: DLL registration (Windows frozen mode, needs settings)
# ---------------------------------------------------------------------------

def register_dlls(settings) -> None:
    """Register DLL search directories for Windows frozen mode."""
    if not settings.is_frozen:
        return
    if sys.platform != 'win32':
        return
    if not hasattr(os, 'add_dll_directory'):
        return

    # Exe directory (python312.dll, vcruntime, etc.)
    exe_dir = os.path.dirname(sys.executable)
    site_packages = str(settings.path.venv / 'Lib' / 'site-packages')

    dll_dirs = [
        exe_dir,
        site_packages,
        os.path.join(site_packages, 'torch', 'lib'),
        os.path.join(site_packages, 'ctranslate2'),
    ]

    # delvewheel convention: *.libs directories
    try:
        for entry in os.scandir(site_packages):
            if entry.is_dir() and entry.name.endswith('.libs'):
                dll_dirs.append(entry.path)
    except Exception:
        pass

    # CUDA DLL path (downloaded by Electron)
    cuda_dir = settings.path.data / 'cuda'
    if cuda_dir.is_dir():
        os.environ['PATH'] = str(cuda_dir) + os.pathsep + os.environ.get('PATH', '')
        dll_dirs.append(str(cuda_dir))

    for d in dll_dirs:
        if os.path.isdir(d):
            try:
                os.add_dll_directory(d)
            except Exception:
                pass
