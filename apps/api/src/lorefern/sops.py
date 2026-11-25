"""The SOP coverage map: which recurring processes found in meetings and tasks have an SOP, which have a stale one, and which have none.

How a recurring process is found (plain counting, no model): take every task title, proposed or approved, and every decision title. Reduce each to its meaningful word
stems (names of people and clients, and everyday words, are dropped). Count two and three word stem groups across different meetings and tasks. A group seen in at least
MIN_SOURCES different sources over at least two different weeks is a process. Groups inside a larger group with the same support are merged.

How coverage is decided: an SOP document (type sop) covers a process when every stem of the process appears in the SOP and at least one in its title. It is `stale` when
its review date has passed or it is older than the configured review days. No match is a `gap`.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from lorefern.actions import extract_actions
from lorefern.models import Decision, Document, Meeting, Owner, Process, Task
from lorefern.textproc import STOP, stem, stems
from lorefern.visibility import allowed_tags

MIN_SOURCES = 3
GENERIC = {"send", "update", "check", "make", "start", "finish", "write", "move", "prepare", "review", "book", "ask", "share", "set", "plan", "new", "next", "first", "last", "week", "month", "day", "thing", "week", "time", "work", "end", "friday", "monday", "thursday", "wednesday", "tuesday", "template", "page", "list"}
ORDER = ("company", "clients", "finance", "people", "leadership")


def _content(title: str, names: set[str]) -> list[str]:
    out = []
    for w in re.findall(r"[A-Za-z']+", title):
        lw = w.lower().replace("'", "")
        if lw in names or lw in STOP or (w[0].isupper() and title.split()[0] != w and len(w) > 2 and lw not in {"care", "plan"}):
            continue
        s = stem(w)
        if len(s) >= 3 and s not in GENERIC:
            out.append(s)
    return out


def _grams(seq: list[str]) -> set[tuple[str, ...]]:
    out = set()
    for n in (2, 3):
        for i in range(len(seq) - n + 1):
            out.add(tuple(seq[i:i + n]))
    return out


def detect(session: Session, today: date, settings, wording=None) -> list[Process]:
    names = {p.lower() for o in session.scalars(select(Owner)) for p in re.findall(r"[A-Za-z]+", o.name)} | {"harbor", "dental", "elm", "street", "bakery", "brightside", "physio", "lantern", "books", "corner", "cycle", "pinegate"}
    srcs: list[tuple[str, int, str, date, str, str]] = []  # kind, id, title, day, tag, surface. A meeting counts once however many of its lines match.
    for t in session.scalars(select(Task).where(Task.status != "rejected")):
        srcs.append(("meeting", t.meeting_id, t.title, t.meeting.held_on, t.tag, t.title) if t.meeting else ("task", t.id, t.title, t.created_at.date(), t.tag, t.title))
    owners = list(session.scalars(select(Owner)))
    for m in session.scalars(select(Meeting)):
        acts, _ = extract_actions(m.transcript.text if m.transcript else "", m.held_on, owners)
        for a in acts:
            srcs.append(("meeting", m.id, a.title, m.held_on, m.tag, a.title))
    for d in session.scalars(select(Decision).where(Decision.status != "rejected")):
        srcs.append(("decision", d.id, d.title, d.decided_on or today, d.tag, d.title))
    seen: dict[tuple[str, ...], list[tuple]] = defaultdict(list)
    for s in srcs:
        for g in _grams(_content(s[2], names)):
            seen[g].append(s)
    cands = []
    for g, items in seen.items():
        uniq = {(i[0], i[1]): i for i in items}
        weeks = {(i[3] - timedelta(days=i[3].weekday())) for i in uniq.values()}
        meetings_or_tasks = len(uniq)
        if meetings_or_tasks >= MIN_SOURCES and len(weeks) >= 2:
            cands.append((g, list(uniq.values())))
    # merge candidates that are the same process: one stem set inside the other, or mostly the same sources
    cands.sort(key=lambda c: (-len(c[1]), -len(c[0])))
    kept: list[list] = []  # [stems, items]
    for g, items in cands:
        ids = {(i[0], i[1]) for i in items}
        home = next((k for k in kept if set(g) <= set(k[0]) or set(k[0]) <= set(g) or ((set(g) & set(k[0])) - {"client"} and len(ids & {(i[0], i[1]) for i in k[1]}) >= 0.7 * min(len(ids), len(k[1])))), None)
        if home is None:
            kept.append([g, items])
        else:
            have = {(i[0], i[1]) for i in home[1]}
            home[1] = home[1] + [i for i in items if (i[0], i[1]) not in have]
    sops = list(session.scalars(select(Document).where(Document.doc_type == "sop")))
    sop_stems = {d.id: (set(stems(d.title)), set(stems(d.text))) for d in sops}
    session.query(Process).delete()
    out = []
    for g, items in sorted(kept, key=lambda k: -len(k[1])):
        g = tuple(g)
        sg = set(g)
        scored = [(len(sg & sop_stems[d.id][0]), d) for d in sops if sg <= sop_stems[d.id][1]]
        scored = [x for x in scored if x[0] >= max(1, len(sg) - 1)]
        match = max(scored, key=lambda x: x[0])[1] if scored else None
        cov = "gap"
        if match:
            overdue = bool(match.review_by and match.review_by < today) or bool(match.updated_on and (today - match.updated_on).days > settings.sop_review_days and not match.review_by)
            cov = "stale" if overdue else "covered"
        surface = max((i[5] for i in items), key=lambda x: sum(w in {stem(v) for v in re.findall(r"[A-Za-z']+", x)} for w in g)).lower()
        evidence = [{"kind": i[0], "id": i[1], "text": i[2], "tag": i[4], "on": i[3].isoformat()} for i in sorted(items, key=lambda x: x[3])]
        forms: dict[str, dict[str, int]] = {}
        for i in items:
            for v in re.findall(r"[A-Za-z']+", i[5]):
                if stem(v) in g:
                    forms.setdefault(stem(v), {}).setdefault(v.lower(), 0)
                    forms[stem(v)][v.lower()] += 1
        label = " ".join(max(forms[w], key=forms[w].get) if w in forms else w for w in g)  # show real words, not stems
        shareable = [e["text"] for e in evidence if e["tag"] == "company"]  # the name is shown to everyone who sees any of the evidence, and the text goes to a model outside this system: only company wide lines are sent
        if wording is not None and len(out) < 12 and shareable:  # the model only names what code counted, for the twelve biggest
            label = wording(label, shareable) or label
        p = Process(key="-".join(g), label=label, area="", mentions=len(items), evidence=evidence, sop_id=match.id if match else None, coverage=cov,
                    tag=max((e["tag"] for e in evidence), key=ORDER.index))
        session.add(p)
        out.append(p)
    session.flush()
    return out


def visible(session: Session, audience: str) -> list[dict]:
    """Processes as a person may see them: evidence rows above their tags are removed, and a process with none left is hidden."""
    tags = allowed_tags(audience)
    res = []
    for p in session.scalars(select(Process).order_by(Process.mentions.desc())):
        ev = [e for e in p.evidence if e["tag"] in tags]
        if len(ev) == 0:
            continue
        sop = session.get(Document, p.sop_id) if p.sop_id else None
        sop_ok = sop is not None and sop.tag in tags
        res.append({"id": p.id, "key": p.key, "label": p.label, "mentions": len(ev), "coverage": p.coverage, "evidence": ev,
                    "sop": {"id": sop.id, "title": sop.title, "owner": sop.owner, "review_by": sop.review_by.isoformat() if sop.review_by else ""} if sop_ok else None})
    return res
