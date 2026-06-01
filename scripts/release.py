"""
MediaTranX Release Script

Usage:
  python scripts/release.py v1.3.1                   # direct version
  python scripts/release.py --bump patch              # auto from latest tag
  python scripts/release.py --bump minor --full       # with full installer
  python scripts/release.py v1.3.1 --skip-build       # skip build step

Must be run from the project root (MediaTranX/).
Requires: gh CLI (authenticated), git.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# ── Self-copy trick ──────────────────────────────────────────────────────────
# git checkout main will modify/delete files in scripts/.
# Run from a temp copy so the original file is not locked by this process.
if not os.environ.get("_RELEASE_FROM_TEMP"):
    _src = Path(__file__).resolve()
    _root = _src.parent.parent
    _tmp = Path(tempfile.gettempdir()) / f"mediatranx_release_{os.getpid()}.py"
    shutil.copy2(_src, _tmp)
    env = {**os.environ, "_RELEASE_FROM_TEMP": "1", "_RELEASE_ROOT": str(_root)}
    result = subprocess.run([sys.executable, str(_tmp)] + sys.argv[1:], env=env, cwd=str(_root))
    _tmp.unlink(missing_ok=True)
    sys.exit(result.returncode)

ROOT = Path(os.environ.get("_RELEASE_ROOT", Path(__file__).resolve().parent.parent))
DIST_DIR = ROOT / "dist"


# ── Helpers ──────────────────────────────────────────────────────────────────

def run(cmd: list, cwd: Path = ROOT, check: bool = True, capture: bool = False, **kwargs):
    """Run a command, optionally capturing stdout. Uses shell=True on Windows for .cmd scripts."""
    _shell = sys.platform == "win32"
    if not capture:
        print(f"  $ {' '.join(str(c) for c in cmd)}")
        return subprocess.run(cmd, cwd=str(cwd), check=check, shell=_shell, **kwargs)
    # capture mode: shell=False to avoid cmd.exe eating % in format strings
    result = subprocess.run(
        cmd, cwd=str(cwd), check=check, shell=False,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs,
    )
    return (result.stdout or b"").decode("utf-8", errors="replace").strip()


def get_latest_tag() -> str | None:
    """Get the latest git tag."""
    try:
        return run(["git", "describe", "--tags", "--abbrev=0"], capture=True)
    except subprocess.CalledProcessError:
        return None


def bump_version(current: str, bump: str) -> str:
    """Bump version string (without v prefix)."""
    semver = current.lstrip("v")
    parts = semver.split(".")
    major, minor, patch = int(parts[0]), int(parts[1]), int(parts[2])
    if bump == "major":
        return f"{major + 1}.0.0"
    elif bump == "minor":
        return f"{major}.{minor + 1}.0"
    else:
        return f"{major}.{minor}.{patch + 1}"


# ── Pre-flight checks ───────────────────────────────────────────────────────

def preflight(version: str):
    """Validate environment before release."""
    print("\n[0/6] Pre-flight checks...")
    errors = []

    # gh CLI
    try:
        run(["gh", "auth", "status"], capture=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        errors.append("gh CLI not found or not authenticated")

    # Branch check
    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture=True)
    if branch != "dev":
        errors.append(f"Must be on dev, currently: {branch}")

    # Clean working tree
    status = run(["git", "status", "--porcelain"], capture=True)
    if status:
        errors.append("Working tree has uncommitted changes")

    # Fetch
    run(["git", "fetch", "origin"], check=False)

    # Tag not exists
    existing = run(["git", "tag", "-l", version], capture=True)
    if existing:
        errors.append(f"Tag {version} already exists")

    if errors:
        for e in errors:
            print(f"  [ERROR] {e}")
        sys.exit(1)

    print("  [OK] All checks passed.")


# ── Release steps ────────────────────────────────────────────────────────────

def step1_merge():
    """Merge dev → main."""
    print("\n[1/6] Merge dev to main...")
    run(["git", "checkout", "main"])
    run(["git", "reset", "--hard", "origin/main"])
    run(["git", "merge", "dev", "--no-ff", "-m", "Merge branch 'dev' into main"])
    print("  [OK] Merged.")


def step2_bump(semver: str, version: str):
    """Bump version in backend/pyproject.toml (+uv.lock) and electron/package.json."""
    print(f"\n[2/6] Bump version to {semver}...")
    pyproject = ROOT / "backend" / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    text = re.sub(r'(?m)^version = ".*"', f'version = "{semver}"', text)
    pyproject.write_text(text, encoding="utf-8")

    run(["uv", "lock"], cwd=ROOT / "backend")
    run(["npm", "version", semver, "--no-git-tag-version"], cwd=ROOT / "electron")
    run(["git", "add",
         "backend/pyproject.toml", "backend/uv.lock",
         "electron/package.json", "electron/package-lock.json"])
    run(["git", "commit", "-m", f"chore: bump version to {version}"])
    print("  [OK] Version bumped.")


def step3_build(semver: str, skip: bool, full: bool):
    """Build installer."""
    if skip:
        print("\n[3/6] Skipping build.")
        return

    print("\n[3/6] Building installer...")
    # build.py's step_nuitka computes Nuitka's --nofollow-import-to exclusion
    # list from the *running* interpreter's installed packages, so build.py
    # MUST run inside the backend venv. `--project backend` makes uv use that
    # project's venv; without it the exclusion list is wrong and the build
    # breaks. (See docs/RELEASE.md.)
    cmd = ["uv", "run", "--project", str(ROOT / "backend"), "python",
           str(ROOT / "scripts" / "build.py"),
           "--mode", "prod", "--version", semver]
    if full:
        cmd.append("--full")
    run(cmd)


def step4_tag(version: str):
    """Tag the release."""
    print(f"\n[4/6] Tagging {version}...")
    run(["git", "tag", "-a", version, "-m", f"Release {version}"])
    print("  [OK] Tagged.")


def step5_push_release(version: str, semver: str, full: bool):
    """Push and create GitHub release."""
    print("\n[5/6] Pushing and creating release...")

    run(["git", "push", "origin", "main"])
    run(["git", "push", "origin", version])

    # Generate release notes
    prev_tag = None
    try:
        prev_tag = run(
            ["git", "describe", "--tags", "--abbrev=0", f"{version}^"],
            capture=True
        )
    except subprocess.CalledProcessError:
        pass

    if prev_tag:
        notes = run(
            ["git", "log", f"{prev_tag}..{version}", "--pretty=format:- %s", "--no-merges"],
            capture=True
        )
    else:
        notes = run(
            ["git", "log", "--pretty=format:- %s", "--no-merges", "-20"],
            capture=True
        )

    suffix = "-full" if full else ""
    installer = DIST_DIR / f"MediaTranX-Setup-{semver}{suffix}-win.exe"
    if not installer.exists():
        print(f"  [ERROR] Installer not found: {installer}")
        if DIST_DIR.exists():
            for f in DIST_DIR.glob("*.exe"):
                print(f"    Found: {f.name}")
        sys.exit(1)

    notes_file = ROOT / "release_notes.tmp"
    notes_file.write_text(notes, encoding="utf-8")

    run([
        "gh", "release", "create", version, str(installer),
        "--repo", "sw-willie-wu/MediaTranX",
        "--title", f"MediaTranX {version}",
        "--notes-file", str(notes_file),
    ])

    notes_file.unlink(missing_ok=True)
    print("  [OK] Release created.")


def step6_sync(version: str):
    """Sync main back to dev."""
    print("\n[6/6] Syncing main back to dev...")
    run(["git", "checkout", "dev"])
    run(["git", "merge", "main", "--no-edit"])
    print("  [OK] Synced.")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="MediaTranX Release")
    parser.add_argument("version", nargs="?", default=None, help="Version (e.g. v1.3.1)")
    parser.add_argument("--bump", choices=["major", "minor", "patch"], default=None)
    parser.add_argument("--skip-build", action="store_true", help="Skip build step")
    parser.add_argument("--full", action="store_true", help="Build full installer")
    args = parser.parse_args()

    # Determine version
    if args.version:
        version = args.version
    elif args.bump:
        latest = get_latest_tag()
        if not latest:
            print("[ERROR] No existing tag found. Provide version directly.")
            sys.exit(1)
        semver = bump_version(latest, args.bump)
        version = f"v{semver}"
        print(f"  Latest tag: {latest} -> bump {args.bump} -> {version}")
    else:
        print("[ERROR] Provide a version (e.g. v1.3.1) or --bump patch/minor/major")
        sys.exit(1)

    # Validate format
    if not version.startswith("v"):
        print("[ERROR] Version must start with 'v'")
        sys.exit(1)

    m = re.match(r"^v(\d+\.\d+\.\d+)$", version)
    if not m:
        print("[ERROR] Version format must be vX.Y.Z")
        sys.exit(1)

    semver = m.group(1)

    print()
    print("========================================")
    print(f"  MediaTranX Release: {version}")
    print("========================================")

    preflight(version)
    step1_merge()
    step2_bump(semver, version)
    step3_build(semver, args.skip_build, args.full)
    step4_tag(version)
    step5_push_release(version, semver, args.full)
    step6_sync(version)

    print()
    print("========================================")
    print(f"  Release {version} complete!")
    print(f"  https://github.com/sw-willie-wu/MediaTranX/releases/tag/{version}")
    print("========================================")


if __name__ == "__main__":
    main()
