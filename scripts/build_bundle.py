"""Bundle the Python the page runs in the browser into site/py/bundle.zip.

    uv run python scripts/build_bundle.py      (or: npm run build)

The zip holds py/browser.py (the entry point), league/ and the football half of espn-api,
copied from this project's virtualenv. The page's Pyodide worker (site/worker.js) unpacks
it and imports ``browser``.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import espn_api

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "py" / "bundle.zip"
# espn-api's shared modules plus football; the other sports aren't needed.
ESPN_PARTS = ["__init__.py", "_version.py", "base_league.py", "base_offer.py", "base_pick.py",
              "base_settings.py", "requests", "utils", "football"]


def _add(z: zipfile.ZipFile, src: Path, arc: str) -> None:
    if src.is_dir():
        for f in sorted(src.rglob("*.py")):
            z.write(f, f"{arc}/{f.relative_to(src).as_posix()}")
    else:
        z.write(src, arc)


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    espn = Path(espn_api.__file__).parent
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(ROOT / "py" / "browser.py", "browser.py")
        _add(z, ROOT / "league", "league")
        for part in ESPN_PARTS:
            _add(z, espn / part, f"espn_api/{part}")
    print(f"{OUT.relative_to(ROOT)}: {OUT.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
