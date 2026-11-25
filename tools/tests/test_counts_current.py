"""The numbers the docs quote (<!--n:...--> markers, filled from data/counts.json) are checked against the code, so a count cannot drift: a new test, route or table without a run of
`python tools/make_counts.py` and `python tools/check_docs.py --fix` fails here. The browser test count needs Playwright, so it is measured only by make_counts."""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COUNTS = json.loads((ROOT / "data" / "counts.json").read_text())


def test_the_number_of_python_tests_is_the_number_the_docs_quote():
    out = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-o", "addopts=", "-p", "no:cacheprovider", "apps/api/tests", "mock/tests", "tools/tests"], cwd=ROOT, capture_output=True, text=True, timeout=300).stdout
    m = re.search(r"(\d+) tests? collected", out)
    assert m, out[-300:]
    quoted = COUNTS["tests"]["passed"] + COUNTS["tests"]["skipped"] + COUNTS["tests"]["failed"]
    assert int(m.group(1)) == quoted, f"{m.group(1)} tests exist, the docs quote {quoted}: run tools/make_counts.py, then tools/check_docs.py --fix"


def test_the_route_and_table_counts_match_the_app_and_the_published_schema():
    sys.path[:0] = [str(ROOT / "apps" / "api" / "src"), str(ROOT / "packages" / "core-py" / "src")]
    from lorefern.api.app import create_app
    from lorefern.config import Settings

    with tempfile.TemporaryDirectory() as d:
        live = create_app(Settings(_env_file=None, database_url=f"sqlite:///{d}/x.sqlite3")).openapi()
    published = json.loads((ROOT / "docs" / "openapi.json").read_text())
    assert live == published, "docs/openapi.json is out of date: run tools/export_openapi.py"
    ops = sum(1 for v in live["paths"].values() for k in v if k in ("get", "post", "put", "patch", "delete"))
    assert (len(live["paths"]), ops) == (COUNTS["api_paths"], COUNTS["api_operations"]), "route counts changed: run tools/make_counts.py"
    tables = len(re.findall(r'__tablename__ = "cx_', (ROOT / "apps/api/src/lorefern/models.py").read_text()))
    assert tables == COUNTS["tables"]
