"""
MediaTranX Unified Build Script

Usage:
  python scripts/build.py                                 # prod, bump minor, all steps
  python scripts/build.py --mode dev --bump patch          # 1.3.1-dev.1
  python scripts/build.py --version 1.3.1                  # direct version
  python scripts/build.py --full                           # include .venv + bin tools
  python scripts/build.py --step vite                      # only run vite build
  python scripts/build.py --step vite,nuitka               # run vite + nuitka only

Must be run from the project root (MediaTranX/).
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────

ROOT = Path(__file__).resolve().parent.parent
ELECTRON_DIR = ROOT / "electron"
FRONTEND_DIR = ROOT / "frontend"
BACKEND_DIR = ROOT / "backend"
BUILD_DIR = ROOT / "build"
DIST_DIR = ROOT / "dist"
RESOURCES_DIR = BUILD_DIR / "resources"

PACKAGE_JSON = ELECTRON_DIR / "package.json"
PYPROJECT_TOML = BACKEND_DIR / "pyproject.toml"


# ── Version helpers ──────────────────────────────────────────────────────────

def read_version() -> str:
    """Read current version from electron/package.json."""
    data = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    return data["version"]


def bump_version(current: str, bump: str) -> str:
    """Bump version: major/minor/patch."""
    parts = current.split("-")[0].split(".")
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    if bump == "major":
        return f"{major + 1}.0.0"
    elif bump == "minor":
        return f"{major}.{minor + 1}.0"
    else:
        return f"{major}.{minor}.{patch + 1}"


def find_next_dev_num(base: str) -> int:
    """Scan dist/ for existing dev builds and return next N."""
    dev_num = 1
    if not DIST_DIR.exists():
        return dev_num
    pattern = re.compile(rf"MediaTranX-Setup-{re.escape(base)}-dev\.(\d+)-win\.exe")
    for f in DIST_DIR.iterdir():
        m = pattern.match(f.name)
        if m:
            candidate = int(m.group(1)) + 1
            if candidate > dev_num:
                dev_num = candidate
    return dev_num


def set_version(version: str, sync_lock: bool = True, build_mode: str = "prod"):
    """Write version to package.json and pyproject.toml; stamp buildMode."""
    # package.json (ignore error if version already matches)
    run(["npm", "version", version, "--no-git-tag-version"], cwd=ELECTRON_DIR, check=False)

    # buildMode stamp (channel for the update checker; repo default is "prod").
    # Must run AFTER npm version, which rewrites package.json.
    pkg_path = ELECTRON_DIR / "package.json"
    pkg = json.loads(pkg_path.read_text(encoding="utf-8"))
    pkg["buildMode"] = build_mode
    pkg_path.write_text(json.dumps(pkg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # pyproject.toml (UTF-8 no BOM)
    text = PYPROJECT_TOML.read_text(encoding="utf-8")
    text = re.sub(r'(?m)^version = ".*"', f'version = "{version}"', text)
    PYPROJECT_TOML.write_text(text, encoding="utf-8")

    if sync_lock:
        run(["uv", "lock"], cwd=BACKEND_DIR)

    print(f"  Version set to {version} (buildMode={build_mode})")


# ── Subprocess helper ────────────────────────────────────────────────────────

def run(cmd: list, cwd: Path = ROOT, check: bool = True, shell: bool | None = None, **kwargs) -> subprocess.CompletedProcess:
    """Run a command and print it. Default shell=True on Windows for .cmd scripts (npm, npx)."""
    if shell is None:
        shell = sys.platform == "win32"
    print(f"  $ {' '.join(str(c) for c in cmd)}")
    return subprocess.run(cmd, cwd=str(cwd), check=check, shell=shell, **kwargs)


# ── Build steps ──────────────────────────────────────────────────────────────

def step_vite():
    """Step 1: Build frontend with Vite."""
    print("\n========================================")
    print("  Step 1: Building Frontend (Vite)")
    print("========================================")

    run(["npm", "install"], cwd=FRONTEND_DIR)
    out_dir = RESOURCES_DIR / "frontend_dist"
    run(["npx", "vite", "build", "--outDir", str(out_dir)], cwd=FRONTEND_DIR)
    print("  Frontend build complete.")


_VC_RUNTIME_DLLS = ("msvcp140.dll", "msvcp140_1.dll")


def _copy_vc_runtime(dest_dir: Path, system_root: str | None = None) -> None:
    """Copy the MSVC C++ runtime DLLs next to core.exe (Windows only).

    onnxruntime's native .pyd depends on msvcp140.dll, which onnxruntime does
    NOT bundle and the uv Python home does NOT ship (it carries only
    vcruntime140*). On a machine without a recent VC++ redistributable the
    import fails, which previously hard-crashed the backend. core.exe's own
    directory is first on the frozen DLL search path (app/init/setup.py), so a
    copy here is found by onnxruntime at load time.

    Sourced from the build machine's System32 (its version must be >= 14.40 /
    VS2022 for onnxruntime 1.17+; this dev machine is 14.44). The DLLs land in
    gitignored build/ and ship only inside the installer (permitted MS runtime
    redistribution) -- never committed.

    CI NOTE: this relies on the *build machine's* System32 being new enough. A
    GitHub Actions / CI runner's System32 version is not guaranteed >= 14.40;
    when moving to CI, source these from a fixed location instead
    (%VCToolsRedistDir%\\x64\\Microsoft.VC143.CRT\\ or by extracting
    vc_redist.x64.exe). See spec 2026-06-02 follow-up.
    """
    if sys.platform != "win32":
        return
    system_root = system_root or os.environ.get("SystemRoot", r"C:\Windows")
    src_dir = Path(system_root) / "System32"
    for name in _VC_RUNTIME_DLLS:
        src = src_dir / name
        if src.is_file():
            shutil.copy2(src, dest_dir / name)
            print(f"  Bundled VC++ runtime: {name}")
        else:
            print(
                f"  WARNING: {src} not found -- installer will ship without {name}. "
                f"onnxruntime (background removal, audio->MIDI) will fail on "
                f"machines lacking a recent VC++ redistributable."
            )


def step_nuitka():
    """Step 2: Compile backend with Nuitka."""
    import importlib.metadata
    import warnings

    print("\n========================================")
    print("  Step 2: Compiling Backend (Nuitka)")
    print("========================================")

    # Stdlib modules to skip (GUI, test, deprecated, built-in, or unnecessary)
    _STDLIB_SKIP = frozenset({
        # GUI / interactive
        '__main__', '__phello__', '_xx', 'xx', 'xxlimited', 'xxlimited_35',
        'xxsubtype', 'antigravity', 'this', 'turtledemo', 'turtle', 'tkinter',
        'idlelib', 'ensurepip', 'venv', 'distutils', 'lib2to3', 'test',
        '_tkinter',
        # Deprecated in 3.12+ (keep aifc/audioop/chunk/sunau/sndhdr for basic-pitch/soundfile)
        'cgi', 'cgitb', 'imghdr', 'mailcap',
        'msilib', 'nntplib', 'pipes', 'telnetlib',
        'uu', 'xdrlib',
        'sre_compile', 'sre_constants', 'sre_parse',
        # Built-in modules (Nuitka ignores them anyway)
        '_abc', '_ast', '_bisect', '_blake2', '_codecs',
        '_codecs_cn', '_codecs_hk', '_codecs_iso2022', '_codecs_jp',
        '_codecs_kr', '_codecs_tw', '_collections', '_contextvars', '_csv',
        '_datetime', '_frozen_importlib', '_frozen_importlib_external',
        '_functools', '_heapq', '_imp', '_io', '_json', '_locale', '_lsprof',
        '_md5', '_multibytecodec', '_opcode', '_operator', '_pickle',
        '_random', '_sha1', '_sha2', '_sha3', '_signal', '_sre', '_stat',
        '_statistics', '_string', '_struct', '_symtable', '_thread',
        '_tokenize', '_tracemalloc', '_typing', '_warnings', '_weakref',
        '_winapi',
        'array', 'atexit', 'binascii', 'builtins', 'cmath', 'errno',
        'faulthandler', 'gc', 'itertools', 'marshal', 'math', 'mmap',
        'msvcrt', 'nt', 'sys', 'time', 'winreg', 'zipimport', 'zlib',
    })

    # Get third-party excludes
    mapping = importlib.metadata.packages_distributions()
    excludes = sorted(k for k in mapping if k != 'app' and not k.startswith('_'))

    # Get importable stdlib modules
    candidates = sys.stdlib_module_names - _STDLIB_SKIP
    stdlib = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        for mod in sorted(candidates):
            try:
                __import__(mod)
                stdlib.append(mod)
            except Exception:
                pass

    icon = str((ELECTRON_DIR / "icon.ico").resolve())

    cmd = [
        # Pin Nuitka — unpinned 'nuitka' drifts to whatever is latest, and a
        # newer Nuitka can demand a newer MinGW toolchain (re-download, version
        # churn). 4.0.8 is the last version verified to build this project; its
        # MinGW (gcc 14.2.0) is already cached.
        "uv", "run", "--with", "nuitka==4.0.8", "--with", "ordered-set",
        "python", "-m", "nuitka",
        "--standalone",
        # Auto-accept Nuitka's MinGW64 download — required for non-interactive
        # (CI / background) builds; otherwise the download prompt defaults to No.
        "--assume-yes-for-downloads",
        "--output-filename=core.exe",
        f"--output-dir={BUILD_DIR / 'temp_nuitka'}",
        "--remove-output",
        "--follow-import-to=app",
    ]

    pkg_includes = [
        "ctypes", "importlib", "email", "http", "xml", "unittest",
        "multiprocessing", "concurrent", "urllib", "logging",
        "asyncio", "json", "html", "collections", "encodings",
        # Lazy-imported by container._lazy() — Nuitka can't discover statically
        "app.services", "app.adapters",
    ]

    for pkg in pkg_includes:
        cmd.append(f"--include-package={pkg}")
    for mod in stdlib:
        if mod not in pkg_includes:
            cmd.append(f"--include-module={mod}")
    for pkg in excludes:
        cmd.append(f"--nofollow-import-to={pkg}")

    cmd.extend([
        f"--windows-icon-from-ico={icon}",
        "--company-name=MediaTranX Team",
        "--product-name=MediaTranX Backend",
        "--file-version=1.0.0.0",
        "--product-version=1.0.0.0",
        "--file-description=MediaTranX Core Engine",
        "--no-deployment-flag=excluded-module-usage",
        "app/main.py",
    ])

    print(f"  Nuitka: excluding {len(excludes)} packages, including {len(stdlib)} stdlib modules")
    # shell=False to avoid Windows cmd.exe 8191 char limit (CreateProcess supports 32768)
    result = subprocess.run(cmd, cwd=str(BACKEND_DIR), check=True, shell=False)
    if result.returncode != 0:
        raise subprocess.CalledProcessError(result.returncode, "nuitka")

    # Organize output
    core_service = RESOURCES_DIR / "core_service"
    if core_service.exists():
        shutil.rmtree(core_service)
    RESOURCES_DIR.mkdir(parents=True, exist_ok=True)

    temp_dist = BUILD_DIR / "temp_nuitka" / "main.dist"
    if temp_dist.exists():
        shutil.move(str(temp_dist), str(core_service))
        print(f"  Moved core engine to {core_service}")
        # Bundle MSVC runtime next to core.exe so onnxruntime loads on clean machines
        _copy_vc_runtime(core_service)

    temp_nuitka = BUILD_DIR / "temp_nuitka"
    if temp_nuitka.exists():
        shutil.rmtree(temp_nuitka)

    # Copy pyproject.toml + uv.lock (use existing, set_version handles sync)
    shutil.copy2(PYPROJECT_TOML, RESOURCES_DIR / "pyproject.toml")
    uv_lock = BACKEND_DIR / "uv.lock"
    if uv_lock.exists():
        shutil.copy2(uv_lock, RESOURCES_DIR / "uv.lock")

    print("  Backend compilation complete.")


def step_electron(full: bool = False):
    """Step 3: Package Electron installer."""
    print("\n========================================")
    print("  Step 3: Packaging Electron Installer")
    print("========================================")

    RESOURCES_DIR.mkdir(parents=True, exist_ok=True)

    # Clean old dirs
    for d in ["wheels", "python"]:
        p = RESOURCES_DIR / d
        if p.exists():
            shutil.rmtree(p)

    # Copy uv.exe
    uv_path = shutil.which("uv")
    if uv_path:
        shutil.copy2(uv_path, RESOURCES_DIR / "uv.exe")

    # Copy config files
    shutil.copy2(PYPROJECT_TOML, RESOURCES_DIR / "pyproject.toml")
    uv_lock = BACKEND_DIR / "uv.lock"
    if uv_lock.exists():
        shutil.copy2(uv_lock, RESOURCES_DIR / "uv.lock")

    # Full build: install .venv + download bin tools
    if full:
        print("\n  [Full] Installing .venv...")
        run(["uv", "sync", "--no-dev", "--inexact"], cwd=BACKEND_DIR)

        venv_dest = RESOURCES_DIR / "venv"
        if venv_dest.exists():
            shutil.rmtree(venv_dest)
        shutil.copytree(BACKEND_DIR / ".venv", venv_dest)

        print("  [Full] Downloading bin tools...")
        node_cmd = (
            "const s=require('./electron/setup.js');"
            "(async()=>{"
            "const log=m=>console.log(m);"
            f"const binDir='{(RESOURCES_DIR / 'bin').as_posix()}';"
            "await s.downloadFFmpeg({binDir,onProgress:log});"
            "await s.downloadFluidSynth({binDir,onProgress:log});"
            "await s.downloadLlamaServer({binDir,onProgress:log,variant:'cu124'})"
            "})()"
        )
        run(["node", "-e", node_cmd], check=False)

    # Run electron-builder
    os.environ["CSC_IDENTITY_AUTO_DISCOVERY"] = "false"
    run(["npm", "install"], cwd=ELECTRON_DIR)

    build_cmd = ["npm", "run", "build:electron"]
    if full:
        build_cmd = [
            "npx", "electron-builder", "--win",
            '--config.extraResources.5.from=../build/resources/venv',
            '--config.extraResources.5.to=.venv',
            '--config.extraResources.6.from=../build/resources/bin',
            '--config.extraResources.6.to=bin',
        ]

    run(build_cmd, cwd=ELECTRON_DIR)

    # Rename full build output
    if full and DIST_DIR.exists():
        for f in DIST_DIR.glob("MediaTranX-Setup-*-win.exe"):
            if "-full-" not in f.name:
                new_name = f.name.replace("-win.exe", "-full-win.exe")
                f.rename(f.parent / new_name)

    print("  Electron packaging complete.")


# ── Main ─────────────────────────────────────────────────────────────────────

ALL_STEPS = ["vite", "nuitka", "electron"]

STEP_FNS = {
    "vite": step_vite,
    "nuitka": step_nuitka,
    # electron handled separately (needs `full` param)
}


def main():
    parser = argparse.ArgumentParser(description="MediaTranX Build System")
    parser.add_argument("--mode", choices=["dev", "prod"], default="prod")
    parser.add_argument("--bump", choices=["major", "minor", "patch"], default="minor")
    parser.add_argument("--version", type=str, default=None, help="Direct version (e.g. 1.3.1)")
    parser.add_argument("--full", action="store_true", help="Include .venv + bin tools")
    parser.add_argument("--step", type=str, default=None, help="Comma-separated steps: vite,nuitka,electron")
    args = parser.parse_args()

    # Determine steps
    steps = args.step.split(",") if args.step else ALL_STEPS
    for s in steps:
        if s not in ALL_STEPS:
            print(f"[ERROR] Unknown step: {s}. Valid: {', '.join(ALL_STEPS)}")
            sys.exit(1)

    # Determine version
    current = read_version()

    if args.version:
        target = args.version
    else:
        target = bump_version(current, args.bump)

    if args.mode == "dev":
        dev_num = find_next_dev_num(target)
        build_ver = f"{target}-dev.{dev_num}"
    else:
        build_ver = target

    print()
    print("========================================")
    print("  MediaTranX Build")
    print(f"  Current version: {current}")
    print(f"  Build version:   {build_ver}")
    print(f"  Mode:            {args.mode}")
    print(f"  Steps:           {', '.join(steps)}")
    print(f"  Full:            {args.full}")
    print("========================================")

    # Set version
    is_dev = args.mode == "dev"
    needs_version = "nuitka" in steps or "electron" in steps
    if needs_version:
        print(f"\n[1] Setting version to {build_ver}...")
        set_version(build_ver, sync_lock=not is_dev, build_mode="dev" if is_dev else "prod")

    # Run steps
    try:
        for s in steps:
            if s == "electron":
                step_electron(full=args.full)
            else:
                STEP_FNS[s]()
    except subprocess.CalledProcessError as e:
        print(f"\n[ERROR] Step failed with exit code {e.returncode}")
        sys.exit(1)
    finally:
        # Dev mode: restore version + sync lock back
        if is_dev and needs_version:
            print(f"\nRestoring version to {current}...")
            set_version(current, sync_lock=True)

    suffix = "-full" if args.full else ""
    print()
    print("========================================")
    print(f"  Build complete!")
    if "electron" in steps:
        print(f"  Installer: dist/MediaTranX-Setup-{build_ver}{suffix}-win.exe")
    print("========================================")


if __name__ == "__main__":
    main()
