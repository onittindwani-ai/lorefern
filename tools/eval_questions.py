#!/usr/bin/env python3
"""Score the answer engine against a question key, per class.

Usage: python3 tools/eval_questions.py --set heldout|dev [--out file]
The held out set's FIRST run is saved to data/eval/heldout_first_run.json and never overwritten. Later runs go to heldout_after_tuning.json.
A question is correct when: the outcome is the expected one; for answers, a cited document is one of the expected ones and every must-contain text is in the answer; for conflicts both
values are shown; for refusals and not found, no must-not text appears anywhere in the response (a restricted fact leaking counts as a leak, reported on its own).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "apps/api/src"), str(ROOT / "packages/core-py/src")]
from sqlalchemy import select  # noqa: E402

from lorefern import demo, qa  # noqa: E402
from lorefern.config import Settings  # noqa: E402
from lorefern.context import Ctx  # noqa: E402
from lorefern.models import Document  # noqa: E402
from sendora_core import models as _core  # noqa: E402,F401
from sendora_core.db import Base, make_engine, make_session_factory  # noqa: E402

norm = lambda s: re.sub(r"\s+", " ", s.lower())  # noqa: E731


def build_ctx(tmp: Path) -> Ctx:
    s = Settings(database_url=f"sqlite:///{tmp / 'eval.sqlite3'}", session_secret="eval-secret-eval-secret", seed_dir=str(ROOT / "data"), _env_file=None)
    eng = make_engine(s.database_url)
    Base.metadata.create_all(eng)
    return Ctx(s, make_session_factory(eng))


def run(questions: list[dict]) -> dict:
    with tempfile.TemporaryDirectory(dir=ROOT) as td:
        ctx = build_ctx(Path(td))
        with ctx.factory() as s:
            demo.reset(s, ctx)
        per: dict[str, list[bool]] = defaultdict(list)
        misses, leaks, cites_checked, cites_valid = [], 0, 0, 0
        with ctx.factory() as s:
            slug_of = {d.id: d.slug for d in s.scalars(select(Document))}
            text_of = {d.id: d.text for d in s.scalars(select(Document))}
            for q in questions:
                a = qa.ask(s, ctx, q["question"], q["audience"])
                blob = norm(json.dumps(a.as_dict()))
                ok = a.outcome == q["expect_outcome"]
                reason = "" if ok else f"outcome {a.outcome}, wanted {q['expect_outcome']}"
                if ok and q["expect_outcome"] in {"answer", "conflict"}:
                    cited = {slug_of[c.document_id] for c in a.citations}
                    if q["expect_docs"] and not (cited & set(q["expect_docs"])):
                        ok, reason = False, f"cited {sorted(cited)}"
                    elif any(norm(m) not in norm(a.text) for m in q.get("must_contain", [])):
                        ok, reason = False, "missing: " + ", ".join(m for m in q.get("must_contain", []) if norm(m) not in norm(a.text))
                leak = [m for m in q.get("must_not", []) if norm(m) in blob]
                if leak:
                    ok, reason, leaks = False, f"LEAK: {leak}", leaks + 1
                for c in a.citations:
                    cites_checked += 1
                    cites_valid += text_of.get(c.document_id, "")[c.start:c.end].strip() == c.passage.strip() or c.passage.strip() in text_of.get(c.document_id, "")
                per[q["class"]].append(ok)
                if not ok:
                    misses.append({"id": q["id"], "class": q["class"], "question": q["question"], "audience": q["audience"], "why": reason, "answer": a.text[:140]})
        allr = [x for v in per.values() for x in v]
        return {"questions": len(allr), "correct": sum(allr), "accuracy": round(sum(allr) / max(1, len(allr)), 3), "leaks": leaks, "citations_checked": cites_checked, "citations_valid": cites_valid,
                "per_class": {k: {"n": len(v), "correct": sum(v), "accuracy": round(sum(v) / len(v), 3)} for k, v in sorted(per.items())}, "misses": misses}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", choices=["heldout", "dev"], default="heldout")
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    f = ROOT / f"data/eval/{'heldout' if a.set == 'heldout' else 'dev'}_questions.json"
    qs = json.loads(f.read_text())["questions"]
    res = run(qs)
    out = a.out
    if out is None and a.set == "heldout":
        first = ROOT / "data/eval/heldout_first_run.json"
        out = first if not first.exists() else ROOT / "data/eval/heldout_after_tuning.json"
    elif out is None:
        out = ROOT / "data/eval/dev_run.json"
    out.write_text(json.dumps(res, indent=1))
    print(json.dumps({k: v for k, v in res.items() if k != "misses"}, indent=1))
    print(f"saved to {out.relative_to(ROOT)}; {len(res['misses'])} misses")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
