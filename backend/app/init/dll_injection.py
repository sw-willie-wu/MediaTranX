"""
DLL and sys.path injection for frozen mode.
"""
import os
import sys
from pathlib import Path


def inject_paths(settings) -> None:
    """Inject sys.path and DLL search paths (Windows frozen mode only)."""
    if settings.platform != "win32":
        return

    if not settings.is_frozen:
        return

    venv_site = str(Path(settings.path.venv) / "Lib" / "site-packages")
    if venv_site not in sys.path:
        sys.path.append(venv_site)

    if not hasattr(os, 'add_dll_directory'):
        return

    venv_base = settings.path.venv
    dll_dirs = [
        os.path.join(venv_base, 'Scripts'),
        os.path.join(venv_site, 'torch', 'lib'),
        os.path.join(venv_site, 'ctranslate2'),
        os.path.join(venv_site, 'tokenizers'),
    ]
    for d in dll_dirs:
        if os.path.isdir(d):
            try:
                os.add_dll_directory(d)
            except Exception:
                pass

    # Scan .libs directories (delvewheel convention)
    if os.path.isdir(venv_site):
        try:
            for entry in os.scandir(venv_site):
                if entry.is_dir() and entry.name.endswith('.libs'):
                    try:
                        os.add_dll_directory(entry.path)
                    except Exception:
                        pass
        except Exception:
            pass

    # Base Python home from pyvenv.cfg
    pyvenv_cfg = os.path.join(venv_base, 'pyvenv.cfg')
    if os.path.isfile(pyvenv_cfg):
        try:
            with open(pyvenv_cfg, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.lower().startswith('home'):
                        py_home = line.split('=', 1)[1].strip()
                        if os.path.isdir(py_home):
                            try:
                                os.add_dll_directory(py_home)
                            except Exception:
                                pass
                        break
        except Exception:
            pass

    # CUDA DLL path
    cuda_dir = os.path.join(settings.path.data, 'cuda')
    if os.path.isdir(cuda_dir):
        os.environ["PATH"] = cuda_dir + os.pathsep + os.environ.get("PATH", "")
        try:
            os.add_dll_directory(cuda_dir)
        except Exception:
            pass
