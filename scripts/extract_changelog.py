"""Extract a version section from CHANGELOG.md.

Shared by CI (.github/workflows/release.yml release step) and release.py
preflight so both sides use the IDENTICAL section anchor:
a line starting with `## [X.Y.Z]` (prefix match; trailing ` - date` OK),
ending at the next line starting with `## [` or EOF.

Stdlib only (release.py preflight calls it with sys.executable).

Usage:
  python scripts/extract_changelog.py 1.6.0                 # body to stdout
  python scripts/extract_changelog.py 1.6.0 --out notes.md  # body to file
  python scripts/extract_changelog.py 1.6.0 --check         # preflight gate
"""
import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CHANGELOG = ROOT / "CHANGELOG.md"


def extract_section(text: str, version: str) -> str | None:
    """Body of the `## [version]` section (heading line excluded, stripped).

    None if the heading is absent; "" if present but empty. Section ends at
    the next `## [` heading or EOF (the EOF case matters: a temporary test
    section like [0.0.0] may be the last one in the file).
    """
    anchor = re.compile(rf"^## \[{re.escape(version)}\]", re.MULTILINE)
    m = anchor.search(text)
    if not m:
        return None
    heading_end = text.find("\n", m.start())
    if heading_end == -1:
        return ""
    nxt = re.compile(r"^## \[", re.MULTILINE).search(text, heading_end + 1)
    body = text[heading_end + 1 : nxt.start() if nxt else len(text)]
    return body.strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="X.Y.Z (no leading v)")
    parser.add_argument("--changelog", type=Path, default=DEFAULT_CHANGELOG)
    parser.add_argument("--out", type=Path, default=None,
                        help="write body to file instead of stdout")
    parser.add_argument("--check", action="store_true",
                        help="preflight: exists + non-empty + no date placeholder + no BOM")
    args = parser.parse_args()

    if not args.changelog.is_file():
        print(f"[ERROR] {args.changelog} not found", file=sys.stderr)
        return 1

    raw = args.changelog.read_bytes()
    if raw.startswith(b"\xef\xbb\xbf"):
        print("[ERROR] CHANGELOG has a UTF-8 BOM; must be UTF-8 without BOM",
              file=sys.stderr)
        return 1
    text = raw.decode("utf-8").replace("\r\n", "\n")

    body = extract_section(text, args.version)
    if body is None:
        print(f"[ERROR] CHANGELOG has no `## [{args.version}]` section",
              file=sys.stderr)
        return 1
    if not body:
        print(f"[ERROR] `## [{args.version}]` section is empty", file=sys.stderr)
        return 1

    if args.check:
        heading = next(line for line in text.splitlines()
                       if line.startswith(f"## [{args.version}]"))
        if "XX" in heading:
            print(f"[ERROR] heading has a date placeholder: {heading}",
                  file=sys.stderr)
            return 1
        print(f"[OK] `## [{args.version}]` section present ({len(body)} chars)")
        return 0

    if args.out:
        args.out.write_text(body + "\n", encoding="utf-8", newline="\n")
    else:
        # bytes to avoid UnicodeEncodeError on cp950 Windows console
        sys.stdout.buffer.write((body + "\n").encode("utf-8"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
