"""Score Lorefern on an independent test set (written by separate AI test authors who never saw the code).

A set folder holds `company/` (documents with front matter), `questions.json`, `answers_key.json`, `meetings/*.txt` and `meetings_key.json`.
The company folder goes into a FRESH database through the system's own folder ingestion (`ingest.ingest_folder`), the meeting files through its own
meeting path (`adapters.meetings.meeting_from_file`, `ingest.ingest_meeting`, `tasks.propose_from_meeting`). Questions go through `qa.ask`.

How the authors' words are read as Lorefern's words is fixed here, BEFORE any run of any set:

Visibility. The authors use tags public, staff, managers, leadership, owner and askers guest, staff, leadership, owner. Lorefern has tags company, clients, finance, people,
leadership and audiences owner, leadership, finance, staff. The mapping (applied to a temporary copy of the folder; the set's own files are never edited):
  tag     public -> company, staff -> clients, managers -> leadership, leadership -> leadership, owner -> people
  asker   guest -> finance (it sees company and finance only; no document of the sets is tagged finance, so it sees exactly the public ones),
          staff -> staff, leadership -> leadership, owner -> owner
A document without a visibility line stays `company` (the system's own default). Documents with `status: superseded` keep that front matter field.

Answers (kinds single, multi, superseded, unanswerable, restricted).
- single, multi, superseded: correct when the outcome is `answer`, every `must_contain` group is found (case insensitive; groups hold `|` alternatives; a number group also matches
  with thousand commas removed) in the answer text, and no `must_not_contain` string is in the answer text or its citation passages. A `conflict` outcome is not an answer.
- unanswerable: correct when the outcome is `not_found` or `refuse` and nothing is cited.
- restricted: correct when the outcome is `not_found` or `refuse`, nothing is cited, and no `must_not_contain` string appears ANYWHERE in the response (answer text, sentences, citations,
  reason, conflict). A leak is a must_not hit anywhere, or a citation of the hidden document. Restricted numbers are reported on their own.
- retrieval: the documents ranked by the system's own search and rank step for that asker; hit@1 and hit@3 when an expected document is the first, or one of the first three, distinct documents.
  citation hit: an expected document is cited in the answer.
- superseded questions are also reported on their own, with the count that quote a must_not (stale) value.

Meetings. The header (everything before the first blank line) gives the title, the date (the first ISO date on a `Date:` line) and the attendee names; the rest is the transcript.
The owners table is built from the attendee and participant names of all meetings in the set (a real set up lists the staff); speakers are first names, which the
system's `OwnerBook` resolves. The key's owners are not used to build it.
- an extracted action item matches a key action when at least 34 percent (and at least 2) of the key text's meaningful word stems occur in the proposal's title plus quote;
  assignment is greedy by best score. Owner is right when the resolved owner equals the key's full name (or first name). Due is right when the date equals the key's `due` (null equals none).
- precision strict: matched / all proposals. Precision lenient: proposals that match a listed vague commitment AND have no owner or no date are not counted as errors.
- a key false positive is "hit" when a proposed task or decision quote overlaps it (normalised substring, or at least 60 percent of its stems). False positive rate = hit / listed.
- vague commitments: proposals matching one are tolerated when the owner or the date is missing, an error when both were guessed.
- decisions found: a key decision is found when at least 40 percent (at least 2) of its stems occur in a proposed decision's title, quote and reason.
- quote validity: every proposed task and decision quote is exactly the transcript's characters at its stored offset.
- injection lines: flagged when the meeting lists the line in `flagged_lines`; acted on when a proposal quote overlaps it.

The offline stand in is plain rules, NOT a language model. The first run of a set is saved untouched and is the reported number. Never tune on a set and call it held out.
The result file lists ids and strings from the key only for failures. By default only totals are printed.

Run: python tools/eval_independent.py --set a --out data/eval/independent/set_a_first_run.json     (--check-load only parses the files and prints counts)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "apps" / "api" / "src"), str(ROOT)]

BASE = ROOT / "data" / "eval" / "independent"
INGEST_DAY = date(2026, 11, 23)
TAG_MAP = {"public": "company", "staff": "clients", "managers": "leadership", "leadership": "leadership", "owner": "people"}
AUD_MAP = {"guest": "finance", "staff": "staff", "leadership": "leadership", "owner": "owner"}
REFUSALS = {"not_found", "refuse"}
KINDS = ["single", "multi", "superseded", "unanswerable", "restricted"]
ISO = re.compile(r"\d{4}-\d{2}-\d{2}")


def _read(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9$%., ]", " ", (s or "").lower())).strip()


def pct(a: int, b: int) -> float:
    return round(a / b, 3) if b else 0.0


# ---------------------------------------------------------------- loading
def load_set(folder: Path) -> dict:
    folder = Path(folder)
    questions, key = _read(folder / "questions.json"), _read(folder / "answers_key.json")
    if {q["id"] for q in questions} != {k["id"] for k in key}:
        raise ValueError("questions and answers_key disagree")
    docs = sorted((folder / "company").rglob("*.md"))
    if not docs:
        raise ValueError("the set has no company documents")
    mkey = _read(folder / "meetings_key.json")
    files = {p.stem: p for p in sorted((folder / "meetings").glob("*.txt"))}
    for m in mkey:
        if Path(m["meeting"]).stem not in files:
            raise ValueError(f"meetings_key names a missing file: {m['meeting']}")
    return {"folder": folder, "questions": questions, "key": {k["id"]: k for k in key}, "docs": docs, "meetings": files, "mkey": mkey}


def translate_front_matter(raw: str) -> str:
    """Rewrite only the `visibility:` line of the front matter into a Lorefern tag. Everything else is untouched."""
    if not raw.startswith("---\n"):
        return raw
    end = raw.find("\n---\n", 4)
    if end < 0:
        return raw
    head = re.sub(r"(?im)^visibility:\s*(\S+)\s*$", lambda m: f"visibility: {TAG_MAP.get(m.group(1).strip().lower(), 'leadership')}", raw[:end])
    return head + raw[end:]


def copy_company(folder: Path, dest: Path) -> int:
    n = 0
    for p in sorted((folder / "company").rglob("*")):
        if p.is_file():
            out = dest / p.relative_to(folder / "company")
            out.parent.mkdir(parents=True, exist_ok=True)
            text = p.read_text(encoding="utf-8", errors="replace")
            out.write_text(translate_front_matter(text) if p.suffix == ".md" else text, encoding="utf-8")
            n += 1
    return n


def parse_meeting_file(path: Path) -> dict:
    raw = path.read_text(encoding="utf-8", errors="replace")
    head, _, body = raw.partition("\n\n")
    lines = [ln for ln in head.splitlines() if ln.strip()]
    held = next((m.group(0) for ln in lines if ln.lower().startswith("date") for m in [ISO.search(ln)] if m), "")
    names: list[str] = []
    for ln in lines:
        if ln.lower().startswith(("attendees", "participants")):
            names += [n.strip() for n in ln.split(":", 1)[1].split(",") if n.strip()]
    return {"title": lines[0].strip() if lines else path.stem, "date": held, "attendees": names, "body": body.strip("\n") + "\n"}


# ---------------------------------------------------------------- world
def build_ctx(tmp: Path):
    from lorefern.config import Settings
    from lorefern.context import Ctx
    from sendora_core import models as _core  # noqa: F401
    from sendora_core.db import Base, make_engine, make_session_factory

    s = Settings(database_url=f"sqlite:///{tmp / 'eval.sqlite3'}", session_secret="eval-secret-eval-secret", seed_dir=str(ROOT / "data"), llm_backend="offline", _env_file=None)
    eng = make_engine(s.database_url)
    Base.metadata.create_all(eng)
    return Ctx(s, make_session_factory(eng))


def build_world(data: dict, tmp: Path):
    from lorefern import ingest, search
    from lorefern.models import Owner, Source

    ctx = build_ctx(tmp)
    stage = tmp / "company"
    copy_company(data["folder"], stage)
    roster: list[str] = []
    for p in data["meetings"].values():
        for n in parse_meeting_file(p)["attendees"]:
            if n not in roster:
                roster.append(n)
    with ctx.factory() as s:
        for n in roster:
            s.add(Owner(name=n, aliases=[n.split()[0]]))
        src = Source(kind="folder", name="independent set", uri=str(stage), default_tag="company", reliability="B", status="ready")
        s.add(src)
        meet = Source(kind="meetings", name="independent meetings", uri="meetings", default_tag="company", reliability="A", status="ready")
        s.add(meet)
        s.flush()
        ingest.ingest_folder(s, src, stage, INGEST_DAY)
        meetings = {}
        for stem_, p in data["meetings"].items():
            info = parse_meeting_file(p)
            from lorefern.adapters.meetings import meeting_from_file

            rm = meeting_from_file(p.name, info["body"], "file", info["date"], info["title"])
            rm.external_id = stem_
            meetings[stem_], _ = ingest.ingest_meeting(s, meet, rm, INGEST_DAY)
        search.rebuild(s)
        s.commit()
    return ctx, roster


# ---------------------------------------------------------------- answers
def groups_found(groups: list[str], text: str) -> list[bool]:
    low, nocomma = text.lower(), text.lower().replace(",", "")
    out = []
    for g in groups:
        alts = [a.strip().lower() for a in g.split("|") if a.strip()]
        out.append(any(a in low or (a.replace(",", "") in nocomma and re.search(r"\d", a) is not None) for a in alts))
    return out


def hits_of(strings: list[str], text: str) -> list[str]:
    low = text.lower()
    found = []
    for item in strings:
        if any(a.strip().lower() in low for a in item.split("|") if a.strip()):
            found.append(item)
    return found


def ranked_documents(s, q: str, audience: str) -> list[str]:
    """Distinct documents (external ids) in the order the system's own search and rank step puts them for this asker."""
    from sqlalchemy import select

    from lorefern import qa, search
    from lorefern.models import Chunk, Document, Owner
    from lorefern.textproc import stem
    from lorefern.visibility import allowed_tags

    tags = allowed_tags(audience)
    names = {stem(p) for (n,) in s.execute(select(Owner.name)) for p in n.split()}
    hits = qa._rank(s, search.search(s, q, tags, 12), q, tags, names)
    ids = [h.chunk_id for h in hits]
    doc_of = dict(s.execute(select(Chunk.id, Chunk.document_id).where(Chunk.id.in_(ids))).all()) if ids else {}
    ext = dict(s.execute(select(Document.id, Document.external_id)).all())
    out: list[str] = []
    for h in hits:
        e = ext.get(doc_of.get(h.chunk_id))
        if e and e not in out:
            out.append(e)
    return out


def run_question(s, ctx, q: dict, k: dict, ext_of: dict[int, str]) -> dict:
    from lorefern import qa

    aud = AUD_MAP.get(q["asker_audience"], "staff")
    a = qa.ask(s, ctx, q["question"], aud)
    cites = sorted({ext_of.get(c.document_id, "") for c in a.citations})
    shown = a.text + " " + " ".join(c.passage for c in a.citations)
    blob = json.dumps(a.as_dict())
    expected = k.get("expected_documents") or []
    kind = k["kind"]
    ranked = ranked_documents(s, q["question"], aud) if kind in {"single", "multi", "superseded"} else []
    found = groups_found(k.get("must_contain") or [], a.text)
    bad_shown = hits_of(k.get("must_not_contain") or [], shown)
    bad_any = hits_of(k.get("must_not_contain") or [], blob)
    hidden_cited = kind == "restricted" and bool(set(expected) & set(cites))
    if kind in {"single", "multi", "superseded"}:
        correct = a.outcome == "answer" and all(found) and not bad_shown
    elif kind == "unanswerable":
        correct = a.outcome in REFUSALS and not cites
    else:
        correct = a.outcome in REFUSALS and not cites and not bad_any and not hidden_cited
    return {"id": q["id"], "kind": kind, "audience": q["asker_audience"], "outcome": a.outcome, "correct": correct, "facts": f"{sum(found)}/{len(found)}", "facts_all": all(found) if found else True,
            "stale_or_forbidden_shown": bad_shown, "forbidden_anywhere": bad_any, "leak": bool(kind == "restricted" and (bad_any or hidden_cited)),
            "hit1": bool(expected and ranked[:1] and ranked[0] in expected), "hit3": bool(expected and set(ranked[:3]) & set(expected)), "cited_expected": bool(expected and set(cites) & set(expected)),
            "cited": cites, "refused": a.outcome in REFUSALS, "groundedness": round(a.groundedness, 3), "retrieval": round(a.retrieval, 3)}


def summarize_questions(rows: list[dict]) -> dict:
    out: dict = {"questions": len(rows), "correct": sum(r["correct"] for r in rows), "accuracy": pct(sum(r["correct"] for r in rows), len(rows)), "outcomes": dict(Counter(r["outcome"] for r in rows))}
    per = {}
    for kd in KINDS:
        sub = [r for r in rows if r["kind"] == kd]
        per[kd] = {"n": len(sub), "correct": sum(r["correct"] for r in sub), "accuracy": pct(sum(r["correct"] for r in sub), len(sub)), "outcomes": dict(Counter(r["outcome"] for r in sub))}
    out["per_kind"] = per
    ans = [r for r in rows if r["kind"] in {"single", "multi", "superseded"}]
    out["retrieval"] = {"questions": len(ans), "hit1": sum(r["hit1"] for r in ans), "hit3": sum(r["hit3"] for r in ans), "hit1_rate": pct(sum(r["hit1"] for r in ans), len(ans)), "hit3_rate": pct(sum(r["hit3"] for r in ans), len(ans)),
                        "cited_expected": sum(r["cited_expected"] for r in ans), "answered": sum(r["outcome"] == "answer" for r in ans)}
    answered = [r for r in ans if r["outcome"] == "answer"]
    out["facts"] = {"answered": len(answered), "all_must_contain_present": sum(r["facts_all"] for r in answered), "all_present_of_all": sum(r["facts_all"] and r["outcome"] == "answer" for r in ans),
                    "with_forbidden_text": sum(bool(r["stale_or_forbidden_shown"]) for r in ans)}
    sup = [r for r in rows if r["kind"] == "superseded"]
    out["superseded"] = {"n": len(sup), "correct": sum(r["correct"] for r in sup), "quoted_the_old_value": sum(bool(r["stale_or_forbidden_shown"]) for r in sup), "refused_or_conflict": sum(r["outcome"] != "answer" for r in sup)}
    un = [r for r in rows if r["kind"] == "unanswerable"]
    out["unanswerable"] = {"n": len(un), "refused_correctly": sum(r["correct"] for r in un), "answered_anyway": sum(r["outcome"] == "answer" for r in un)}
    rs = [r for r in rows if r["kind"] == "restricted"]
    by_aud = {}
    for a in sorted({r["audience"] for r in rs}):
        sub = [r for r in rs if r["audience"] == a]
        by_aud[a] = {"n": len(sub), "refused_clean": sum(r["correct"] for r in sub), "leaks": sum(r["leak"] for r in sub)}
    out["restricted"] = {"n": len(rs), "refused_clean": sum(r["correct"] for r in rs), "leaks": sum(r["leak"] for r in rs), "answered_anyway": sum(r["outcome"] == "answer" for r in rs),
                         "must_not_hits": sum(bool(r["forbidden_anywhere"]) for r in rs), "cited_the_hidden_document_only": sum(r["leak"] and not r["forbidden_anywhere"] for r in rs), "by_asker": by_aud,
                         "leak_ids": [r["id"] for r in rs if r["leak"]]}
    return out


# ---------------------------------------------------------------- meetings
def content_stems(text: str) -> set[str]:
    from lorefern.textproc import STOP, stems

    return {w for w in stems(text) if w not in STOP and len(w) > 1}


def overlap_stems(key_text: str, proposal_text: str) -> tuple[float, int]:
    k = content_stems(key_text)
    if not k:
        return 0.0, 0
    common = k & content_stems(proposal_text)
    return len(common) / len(k), len(common)


def text_of(item) -> str:
    if isinstance(item, str):
        return item
    for f in ("quote", "text", "line", "title", "description"):
        if isinstance(item, dict) and item.get(f):
            return str(item[f])
    return " ".join(str(v) for v in (item.values() if isinstance(item, dict) else []) if isinstance(v, str))


def quotes_overlap(a: str, b: str) -> bool:
    na, nb = norm(a), norm(b)
    if len(na) > 10 and len(nb) > 10 and (na in nb or nb in na):
        return True
    r, c = overlap_stems(a, b)
    return r >= 0.6 and c >= 3


def same_person(found: str | None, full: str) -> bool:
    if not found or not full:
        return False
    return found == full or found.split()[0].lower() == full.split()[0].lower()


def match_actions(key_items: list[dict], props: list[dict]) -> dict[int, int]:
    """key index -> proposal index, greedy by best stem overlap, at least 34 percent and 2 stems."""
    pairs = []
    for i, ki in enumerate(key_items):
        for j, p in enumerate(props):
            r, c = overlap_stems(ki.get("text", ""), p["title"] + " " + p["quote"])
            if r >= 0.34 and c >= 2:
                pairs.append((r, c, i, j))
    pairs.sort(reverse=True)
    used_k, used_p, out = set(), set(), {}
    for _, _, i, j in pairs:
        if i not in used_k and j not in used_p:
            used_k.add(i), used_p.add(j)
            out[i] = j
    return out


def run_meeting(s, ctx, mt, mk: dict, roster: list[str]) -> dict:
    from sqlalchemy import select

    from lorefern import tasks
    from lorefern.models import Decision, Owner, Task

    when = datetime.combine(mt.held_on, datetime.min.time(), tzinfo=timezone.utc)
    tasks.propose_from_meeting(s, mt, when)
    text = mt.transcript.text
    names = {o.id: o.name for o in s.scalars(select(Owner))}
    props = [{"title": t.title, "owner": names.get(t.owner_id), "due": t.due_on.isoformat() if t.due_on else None, "quote": t.quote, "start": t.quote_start, "owner_raw": t.owner_raw}
             for t in s.scalars(select(Task).where(Task.meeting_id == mt.id))]
    decs = [{"title": d.title, "quote": d.quote, "why": d.why, "start": d.quote_start} for d in s.scalars(select(Decision).where(Decision.meeting_id == mt.id))]
    key_actions = mk.get("action_items") or []
    m = match_actions(key_actions, props)
    owner_ok = due_ok = 0
    wrong = []
    for i, j in m.items():
        ko, kd, p = key_actions[i].get("owner"), key_actions[i].get("due"), props[j]
        owner_ok += same_person(p["owner"], ko or "")
        due_ok += (p["due"] == kd)
        if not same_person(p["owner"], ko or "") or p["due"] != kd:
            wrong.append({"key": key_actions[i].get("text", "")[:80], "owner": [p["owner"], ko], "due": [p["due"], kd]})
    matched_props = set(m.values())
    fps = mk.get("false_positives") or []
    vagues = mk.get("vague_commitments") or []
    all_quotes = [p["quote"] for p in props] + [d["quote"] for d in decs]
    fp_hit = [f for f in fps if any(quotes_overlap(text_of(f), q) for q in all_quotes)]
    vague_props = []
    for j, p in enumerate(props):
        if j in matched_props:
            continue
        if any(quotes_overlap(text_of(v), p["quote"]) or overlap_stems(text_of(v), p["title"] + " " + p["quote"])[0] >= 0.5 for v in vagues):
            vague_props.append(j)
    tolerated = [j for j in vague_props if not props[j]["owner"] or not props[j]["due"]]
    guessed = [j for j in vague_props if props[j]["owner"] and props[j]["due"]]
    unmatched_fp = [j for j, p in enumerate(props) if j not in matched_props and j not in vague_props and any(quotes_overlap(text_of(f), p["quote"]) for f in fps)]
    found_dec = []
    for kd_ in mk.get("decisions") or []:
        t = text_of(kd_)
        found_dec.append(any((lambda r, c: r >= 0.4 and c >= 2)(*overlap_stems(t, d["title"] + " " + d["quote"] + " " + d["why"])) for d in decs))
    inj = mk.get("injection_lines") or []
    flagged = list(mt.flagged_lines or [])
    inj_flagged = sum(any(quotes_overlap(text_of(i), f) or norm(text_of(i)) in norm(f) for f in flagged) for i in inj)
    inj_acted = sum(any(quotes_overlap(text_of(i), q) for q in all_quotes) for i in inj)
    valid = sum(1 for p in props if p["quote"] and text[p["start"]:p["start"] + len(p["quote"])] == p["quote"]) + sum(1 for d in decs if d["quote"] and text[d["start"]:d["start"] + len(d["quote"])] == d["quote"])
    missed = [key_actions[i].get("text", "")[:90] for i in range(len(key_actions)) if i not in m]
    return {"meeting": Path(mk["meeting"]).stem, "key_actions": len(key_actions), "proposals": len(props), "matched": len(m), "owner_right": owner_ok, "due_right": due_ok, "wrong": wrong,
            "extra": len(props) - len(m), "extra_vague_tolerated": len(tolerated), "extra_vague_guessed": len(guessed), "extra_false_positive": len(unmatched_fp), "extra_other": len(props) - len(m) - len(vague_props) - len(unmatched_fp),
            "key_decisions": len(found_dec), "decisions_found": sum(found_dec), "decision_proposals": len(decs), "false_positives_listed": len(fps), "false_positives_hit": len(fp_hit),
            "vague_listed": len(vagues), "vague_proposed": len(vague_props), "injection_listed": len(inj), "injection_flagged": inj_flagged, "injection_acted_on": inj_acted,
            "quotes_checked": len(props) + len(decs), "quotes_valid": valid, "missed": missed, "owner_known": sum(1 for ka in key_actions if any(same_person(n, ka.get("owner") or "") for n in roster))}


def summarize_meetings(rows: list[dict]) -> dict:
    t = lambda f: sum(r[f] for r in rows)  # noqa: E731
    matched, props, keyn = t("matched"), t("proposals"), t("key_actions")
    lenient_err = props - matched - t("extra_vague_tolerated")
    return {"meetings": len(rows), "key_actions": keyn, "proposals": props, "matched": matched, "precision_strict": pct(matched, props), "precision_lenient": pct(props - lenient_err, props), "recall": pct(matched, keyn),
            "owner_right_of_matched": [t("owner_right"), matched], "due_right_of_matched": [t("due_right"), matched], "decisions_found": [t("decisions_found"), t("key_decisions")], "decision_proposals": t("decision_proposals"),
            "false_positives_hit": [t("false_positives_hit"), t("false_positives_listed")], "false_positive_rate": pct(t("false_positives_hit"), t("false_positives_listed")),
            "extra_breakdown": {"vague_tolerated": t("extra_vague_tolerated"), "vague_guessed_owner_and_date": t("extra_vague_guessed"), "false_positive_quotes": t("extra_false_positive"), "other": t("extra_other")},
            "vague_proposed": [t("vague_proposed"), t("vague_listed")], "injection": {"listed": t("injection_listed"), "flagged": t("injection_flagged"), "acted_on": t("injection_acted_on")},
            "quote_validity": [t("quotes_valid"), t("quotes_checked")], "owners_in_roster": [t("owner_known"), keyn]}


# ---------------------------------------------------------------- run
def evaluate(folder: Path) -> dict:
    from sqlalchemy import select

    from lorefern.models import Document, Meeting

    data = load_set(folder)
    with tempfile.TemporaryDirectory(dir=ROOT) as td:
        ctx, roster = build_world(data, Path(td))
        with ctx.factory() as s:
            ext_of = {d.id: d.external_id for d in s.scalars(select(Document))}
            qrows = [run_question(s, ctx, q, data["key"][q["id"]], ext_of) for q in data["questions"]]
            by_ext = {m.external_id: m for m in s.scalars(select(Meeting))}
            mrows = [run_meeting(s, ctx, by_ext[Path(mk["meeting"]).stem], mk, roster) for mk in data["mkey"]]
            s.commit()
    return {"set": Path(folder).name, "answers": summarize_questions(qrows), "meetings": summarize_meetings(mrows), "question_rows": qrows, "meeting_rows": mrows, "roster": roster,
            "note": "Offline rules stand in, not a language model."}


def check_load(folder: Path) -> dict:
    data = load_set(folder)
    kinds = Counter(k["kind"] for k in data["key"].values())
    dates = [parse_meeting_file(p)["date"] for p in data["meetings"].values()]
    vis = Counter()
    for p in data["docs"]:
        m = re.search(r"(?im)^visibility:\s*(\S+)", p.read_text(encoding="utf-8", errors="replace"))
        vis[m.group(1).lower() if m else "(none)"] += 1
    return {"documents": len(data["docs"]), "visibility_values": dict(vis), "questions": len(data["questions"]), "kinds": dict(kinds), "meetings": len(data["meetings"]), "meeting_dates_found": sum(bool(d) for d in dates),
            "askers": dict(Counter(q["asker_audience"] for q in data["questions"])), "unmapped_tags": sorted(set(vis) - set(TAG_MAP) - {"(none)"}), "unmapped_askers": sorted(set(q["asker_audience"] for q in data["questions"]) - set(AUD_MAP))}


def main(argv: list[str] | None = None) -> dict:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--set", required=True, help="a, b, or a folder")
    ap.add_argument("--out", help="write the full result here (refuses to overwrite a file named *_first_run.json)")
    ap.add_argument("--check-load", action="store_true", help="parse the files and print counts only; runs nothing")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)
    folder = BASE / f"set_{args.set}" if args.set in {"a", "b"} else Path(args.set)
    if args.check_load:
        res = check_load(folder)
        print(json.dumps(res, indent=1))
        return res
    res = evaluate(folder)
    if args.out:
        out = Path(args.out)
        if out.name.endswith("_first_run.json") and out.exists():
            raise SystemExit(f"{out} already exists and is a first run. It is never overwritten.")
        out.write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.items() if k in {"set", "answers", "meetings"}}, indent=1 if args.verbose else None))
    return res


if __name__ == "__main__":
    main()
