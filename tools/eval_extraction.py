#!/usr/bin/env python3
"""Score meeting action and decision extraction against a key.

Usage: python3 tools/eval_extraction.py <transcripts folder> <key.json> [--out result.json]
Matching: a found action matches a key action when the key quote sits inside the found quote (or the other way round), ignoring case and spacing.
Reported: precision, recall, owner accuracy and due date accuracy on matched actions, decision recall, quote validity (must be 100 percent), flagged lines.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps/api/src"))
sys.path.insert(0, str(ROOT / "packages/core-py/src"))
from lorefern.actions import OwnerBook, extract_actions, extract_decisions, validate_quote  # noqa: E402
from lorefern.adapters.meetings import load_transcript_file  # noqa: E402
from lorefern.ingest import transcript_text  # noqa: E402


def norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", re.sub(r"\s+", " ", s.lower())).strip()


def run(folder: Path, key: dict, owners) -> dict:
    book = OwnerBook(owners)
    tp = fp = fn = owner_ok = due_ok = valid = total = dec_tp = dec_n = flagged_ok = 0
    per = {}
    for stem, exp in key.items():
        if stem == "note":
            continue
        m = load_transcript_file(folder / f"{stem}.txt")
        text = transcript_text(m.lines)
        acts, flagged = extract_actions(text, date.fromisoformat(m.held_on), owners)
        decs = extract_decisions(text, owners)
        used: set[int] = set()
        row = {"found": len(acts), "expected": len(exp["actions"]), "missed": [], "extra": [], "wrong_owner": [], "wrong_due": []}
        for k in exp["actions"]:
            hit = next((i for i, a in enumerate(acts) if i not in used and (norm(k["quote"]) in norm(a.quote) or norm(a.quote) in norm(k["quote"]))), None)
            if hit is None:
                fn += 1
                row["missed"].append(k["quote"])
                continue
            used.add(hit)
            tp += 1
            a = acts[hit]
            if (book.resolve(a.owner_name) if a.owner_name else None) == k["owner"]:
                owner_ok += 1
            else:
                row["wrong_owner"].append((k["quote"], a.owner_name))
            if (a.due_on.isoformat() if a.due_on else None) == k["due"]:
                due_ok += 1
            else:
                row["wrong_due"].append((k["quote"], str(a.due_on), k["due"]))
        for i, a in enumerate(acts):
            total += 1
            valid += validate_quote(text, a.quote, a.quote_start)
            if i not in used:
                fp += 1
                row["extra"].append(a.quote)
        for ex in exp["decisions"]:
            dec_n += 1
            dec_tp += any(norm(ex) in norm(d.quote) for d in decs)
        flagged_ok += len(flagged) == exp["flagged"]
        per[stem] = row
    n_files = len(per)
    return {"transcripts": n_files, "expected_actions": tp + fn, "found_actions": tp + fp, "precision": round(tp / max(1, tp + fp), 3), "recall": round(tp / max(1, tp + fn), 3),
            "owner_accuracy": round(owner_ok / max(1, tp), 3), "due_accuracy": round(due_ok / max(1, tp), 3), "decision_recall": round(dec_tp / max(1, dec_n), 3), "decisions_expected": dec_n,
            "quote_validity": round(valid / max(1, total), 3), "quotes_checked": total, "flagged_lines_right": f"{flagged_ok} of {n_files}", "per_transcript": per}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("folder", type=Path)
    ap.add_argument("key", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args(argv)
    owners = [SimpleNamespace(**o) for o in json.loads((ROOT / "data/seed/owners.json").read_text())]
    res = run(a.folder, json.loads(a.key.read_text()), owners)
    if a.out:
        a.out.write_text(json.dumps(res, indent=2))
    print(json.dumps({k: v for k, v in res.items() if k != "per_transcript"}, indent=2))
    return 0 if res["quote_validity"] == 1.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
