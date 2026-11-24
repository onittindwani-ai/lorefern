#!/usr/bin/env python3
"""Check a company folder: every numbered folder has a README and an owner, INDEX.md lists every document, links resolve, review dates are not overdue.

Usage: python3 tools/check_company_folder.py <folder> [--today YYYY-MM-DD] [--reindex] [--json]
Exit code 0 when there are no errors (warnings are printed), 1 when there are errors.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps/api/src"))
sys.path.insert(0, str(ROOT / "packages/core-py/src"))
from lorefern import folder_tool  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("folder", type=Path)
    ap.add_argument("--today", type=date.fromisoformat, default=date.today())
    ap.add_argument("--reindex", action="store_true", help="Rebuild INDEX.md first")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    if not a.folder.is_dir():
        print(f"{a.folder} is not a folder.", file=sys.stderr)
        return 2
    if a.reindex:
        folder_tool.reindex(a.folder, a.folder.name, a.today)
    rep = folder_tool.check(a.folder, a.today)
    if a.json:
        print(json.dumps({"documents": rep.documents, "ok": rep.ok, "findings": [f.__dict__ for f in rep.findings]}, indent=2))
    else:
        for f in rep.findings:
            print(f"{f.severity.upper():8} {f.code:22} {f.path}: {f.message}")
        errs = sum(f.severity == "error" for f in rep.findings)
        print(f"{rep.documents} documents checked, {errs} errors, {len(rep.findings) - errs} warnings.")
    return 0 if rep.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
