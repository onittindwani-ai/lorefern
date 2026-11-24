#!/usr/bin/env python3
"""Measure the numbers the docs quote and write them to data/counts.json.

Every count in README and docs/ comes from this file. Run it after any change, then run tools/check_docs.py.
  python3 tools/make_counts.py            measure and write (runs the Python tests once, with coverage)
  python3 tools/make_counts.py --fast     skip the test run and keep the last test and coverage numbers
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "counts.json"
PY = str(ROOT / ".venv" / "bin" / "python") if (ROOT / ".venv" / "bin" / "python").exists() else sys.executable


def run_tests() -> dict:
    cov = ROOT / ".coverage-counts.json"
    p = subprocess.run([PY, "-m", "pytest", "apps/api/tests", "mock/tests", "tools/tests", "-o", "addopts=", "-q", "-p", "no:warnings", "--cov=lorefern", f"--cov-report=json:{cov}"], cwd=ROOT, capture_output=True, text=True)
    m = re.search(r"(\d+) passed", p.stdout)
    skipped = re.search(r"(\d+) skipped", p.stdout)
    failed = re.search(r"(\d+) failed", p.stdout)
    pct = None
    if cov.exists():
        pct = round(json.loads(cov.read_text())["totals"]["percent_covered"], 1)
        cov.unlink()
    return {"passed": int(m.group(1)) if m else 0, "skipped": int(skipped.group(1)) if skipped else 0, "failed": int(failed.group(1)) if failed else 0, "coverage_percent": pct}


def main(argv: list[str]) -> int:
    old = json.loads(OUT.read_text()) if OUT.exists() else {}
    sd = ROOT / "data" / "seed"
    key = json.loads((sd / "stuck_key.json").read_text())
    seed = {"company_files": sum(1 for p in (sd / "company").rglob("*") if p.is_file()), "meetings": len(list((sd / "meetings").glob("*.txt"))), "planted_tasks": len(json.loads((sd / "tasks.json").read_text())),
            "slack_files": sum(1 for p in (sd / "slack").rglob("*") if p.is_file()), "people": len(json.loads((sd / "owners.json").read_text())), "stuck_pairs": len(key["stuck"]),
            "heldout_transcripts": len(list((ROOT / "data/eval/heldout_transcripts").glob("*.txt")))}
    ev = ROOT / "data" / "eval"
    first, tuned, dev = (json.loads((ev / f).read_text()) for f in ("heldout_first_run.json", "heldout_after_tuning.json", "dev_run.json"))
    ext = json.loads((ev / "heldout_transcripts_first_run.json").read_text())
    evals = {"answers_first_run": {"correct": first["correct"], "of": first["questions"], "leaks": first["leaks"]}, "answers_after_tuning": {"correct": tuned["correct"], "of": tuned["questions"], "leaks": tuned["leaks"]},
             "answers_dev": {"correct": dev["correct"], "of": dev["questions"]}, "extraction": {k: ext[k] for k in ("transcripts", "expected_actions", "found_actions", "precision", "recall", "quote_validity")}}
    ind = ev / "independent"

    def indep(name: str) -> dict:
        r = json.loads((ind / f"{name}.json").read_text())
        a, m = r["answers"], r["meetings"]
        return {"correct": a["correct"], "of": a["questions"], "restricted_refused_clean": a["restricted"]["refused_clean"], "restricted_of": a["restricted"]["n"], "tool_flagged_leaks": a["restricted"]["leaks"],
                "actions_matched": m["matched"], "actions_key": m["key_actions"], "precision_strict": m["precision_strict"], "recall": m["recall"], "decisions_found": m["decisions_found"]}

    evals["independent"] = {n: indep(n) for n in ("set_a_first_run", "set_a_after_improvements", "set_b_first_run")}
    evals["contract_tests"] = len(re.findall(r"^def test_", (ROOT / "mock/tests/test_contracts.py").read_text(), re.M))
    evals["model_path_tests"] = len(re.findall(r"^def test_", (ROOT / "apps/api/tests/test_model_path.py").read_text(), re.M))
    evals["llm_fixtures"] = len(list((ROOT / "data/llm_fixtures").glob("*.json")))
    api = json.loads((ROOT / "docs" / "openapi.json").read_text())
    ops = sum(1 for v in api["paths"].values() for k in v if k in ("get", "post", "put", "patch", "delete"))
    models = (ROOT / "apps/api/src/lorefern/models.py").read_text()
    tables = len(re.findall(r'__tablename__ = "cx_', models))
    lst = subprocess.run(["pnpm", "exec", "playwright", "test", "--list"], cwd=ROOT / "apps" / "web", capture_output=True, text=True).stdout
    mm = re.search(r"Total: (\d+) tests? in (\d+) files?", lst)
    e2e = {"tests": int(mm.group(1)), "files": int(mm.group(2))} if mm else old.get("e2e")
    scores = json.loads((ROOT / "data" / "tool_scores.json").read_text())
    pages = len(re.findall(r'id: "/', (ROOT / "apps/web/src/components/AppFrame.tsx").read_text()))
    shots = len(list((ROOT / "docs" / "screenshots").glob("*.png")))
    tests = old.get("tests") if "--fast" in argv else run_tests()
    data = {
        "tables": tables, "api_paths": len(api["paths"]), "api_operations": ops, "pages": pages, "screenshots": shots,
        "tool_groups": len(scores["groups"]), "tools_scored": sum(len(g["tools"]) for g in scores["groups"]),
        "seed": seed, "heldout_questions": first["questions"], "eval": evals, "e2e": e2e, "tests": tests,
    }
    OUT.write_text(json.dumps(data, indent=1) + "\n")
    print("OK wrote", OUT.relative_to(ROOT), json.dumps({k: data[k] for k in ("tables", "api_paths", "pages", "screenshots", "tools_scored", "tests")}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
