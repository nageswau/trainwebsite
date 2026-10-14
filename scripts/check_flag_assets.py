"""PUB-023 (DEC-SCOPE-222): every ISO country code that migration 0101 creates must have /flags/<code>.svg in the web app.

The api-test and web-test containers each see only their own app, so this cross-app check is a repo script.
Run from anywhere:  python scripts/check_flag_assets.py   (exit 0 = complete, 1 = missing flags listed)
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "apps" / "api" / "alembic" / "versions" / "0101_country_master.py"
FLAGS = ROOT / "apps" / "web" / "public" / "flags"


def iso_codes() -> set[str]:
    """The codes in 0101's `_BY_REGION` literal, read with ast (the migration is never imported)."""
    tree = ast.parse(MIGRATION.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "_BY_REGION" for t in node.targets):
            regions = ast.literal_eval(node.value)
            return {code for rows in regions.values() for code, _name in rows}
    raise SystemExit(f"_BY_REGION not found in {MIGRATION}")


def main() -> int:
    codes = iso_codes()
    present = {p.stem.upper() for p in FLAGS.glob("*.svg")} if FLAGS.is_dir() else set()
    missing = sorted(codes - present)
    if missing:
        print(f"{len(missing)} of {len(codes)} ISO codes have no flag in {FLAGS}: {', '.join(missing)}")
        return 1
    print(f"All {len(codes)} ISO codes from migration 0101 have a flag SVG.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
