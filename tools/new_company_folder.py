#!/usr/bin/env python3
"""Copy the company folder template and fill in the company name, the owner and today's date.

Usage: python3 tools/new_company_folder.py <target folder> --name "Acme Studio" [--owner "Pat Lee"] [--build-template]
`--build-template` rebuilds the shipped blank template in templates/company-folder instead (maintainers only).
"""

from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps/api/src"))
sys.path.insert(0, str(ROOT / "packages/core-py/src"))
from lorefern import folder_tool  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("target", type=Path)
    ap.add_argument("--name", required=True, help="Company name")
    ap.add_argument("--owner", default="the founder", help="Name of the person who owns the folder (default: the founder)")
    ap.add_argument("--template", type=Path, default=ROOT / "templates/company-folder")
    ap.add_argument("--build-template", action="store_true")
    a = ap.parse_args(argv)
    if a.build_template:
        files = folder_tool.build_template(a.target, today=date.today())
        print(f"Wrote the blank template: {len(files)} files in {a.target}")
        return 0
    try:
        files = folder_tool.instantiate(a.template, a.target, a.name, a.owner)
    except FileExistsError as exc:
        print(exc, file=sys.stderr)
        return 2
    rep = folder_tool.check(a.target)
    print(f"Created {len(files)} files for {a.name} in {a.target}")
    print(f"Check: {'OK' if rep.ok else 'problems'}; {len([f for f in rep.findings if f.severity == 'error'])} errors, {len([f for f in rep.findings if f.severity == 'warning'])} warnings")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
