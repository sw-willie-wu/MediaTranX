"""
MediaTranX Release Script

Usage:
  python scripts/release.py v1.3.1           # direct version
  python scripts/release.py --bump patch      # auto from latest tag
  python scripts/release.py --bump minor      # bump minor version

Must be run from the project root (MediaTranX/).
Requires: git.

This script handles only git orchestration (merge → bump → tag → push → sync).
Build, code-signing, and GitHub release creation are performed by GitHub Actions
after the tag push (step 4/5).
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
    print("\n[0/5] Pre-flight checks...")
    errors = []

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

    # CHANGELOG section must exist BEFORE merge/tag: step2 never touches
    # CHANGELOG.md, so passing here guarantees the tagged commit carries the
    # section CI extracts for release notes. Same anchor rule as CI
    # (both call scripts/extract_changelog.py).
    semver = version.lstrip("v")
    chk = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "extract_changelog.py"),
         semver, "--check"],
        cwd=str(ROOT), shell=False,
    )
    if chk.returncode != 0:
        errors.append(
            f"CHANGELOG.md `## [{semver}]` section missing/empty/placeholder "
            f"(see message above)")

    if errors:
        for e in errors:
            print(f"  [ERROR] {e}")
        sys.exit(1)

    print("  [OK] All checks passed.")


# ── Release steps ────────────────────────────────────────────────────────────

def step1_merge():
    """Merge dev → main."""
    print("\n[1/5] Merge dev to main...")
    run(["git", "checkout", "main"])
    run(["git", "reset", "--hard", "origin/main"])
    run(["git", "merge", "dev", "--no-ff", "-m", "Merge branch 'dev' into main"])
    print("  [OK] Merged.")


def step2_bump(semver: str, version: str):
    """Bump version in backend/pyproject.toml (+uv.lock), electron/package.json, and frontend/package.json."""
    print(f"\n[2/5] Bump version to {semver}...")
    pyproject = ROOT / "backend" / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    text = re.sub(r'(?m)^version = ".*"', f'version = "{semver}"', text)
    pyproject.write_text(text, encoding="utf-8")

    run(["uv", "lock"], cwd=ROOT / "backend")
    run(["npm", "version", semver, "--no-git-tag-version"], cwd=ROOT / "electron")
    run(["npm", "version", semver, "--no-git-tag-version"], cwd=ROOT / "frontend")
    run(["git", "add",
         "backend/pyproject.toml", "backend/uv.lock",
         "electron/package.json", "electron/package-lock.json",
         "frontend/package.json", "frontend/package-lock.json"])
    run(["git", "commit", "-m", f"chore: bump version to {version}"])
    print("  [OK] Version bumped.")


def step3_tag(version: str):
    """Tag the release."""
    print(f"\n[3/5] Tagging {version}...")
    run(["git", "tag", "-a", version, "-m", f"Release {version}"])
    print("  [OK] Tagged.")


def step4_push(version: str):
    """Push main + tag; the tag push triggers the CI build & release."""
    print("\n[4/5] Pushing main + tag...")
    run(["git", "push", "origin", "main"])
    run(["git", "push", "origin", version])
    print("  [OK] Pushed. GitHub Actions builds, signs, and publishes the release.")


def step5_sync(version: str):
    """Sync main back to dev."""
    print("\n[5/5] Syncing main back to dev...")
    run(["git", "checkout", "dev"])
    run(["git", "merge", "main", "--no-edit"])
    print("  [OK] Synced.")


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="MediaTranX Release")
    parser.add_argument("version", nargs="?", default=None, help="Version (e.g. v1.3.1)")
    parser.add_argument("--bump", choices=["major", "minor", "patch"], default=None)
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
    step3_tag(version)
    step4_push(version)
    step5_sync(version)

    print()
    print("========================================")
    print(f"  Release {version} tagged & pushed!")
    print(f"  CI build (cold ~40-60 min):")
    print(f"    https://github.com/sw-willie-wu/MediaTranX/actions")
    print(f"  Release will appear at:")
    print(f"    https://github.com/sw-willie-wu/MediaTranX/releases/tag/{version}")
    print("========================================")


if __name__ == "__main__":
    main()
