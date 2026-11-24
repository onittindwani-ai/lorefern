"""Answer a question from the documents a person is allowed to see, with citations, a groundedness check and honest refusals.

Order of work: refuse instructions and non company questions, search only the visible tags, handle two documents that disagree, pick source sentences (an extractive
stand in, NOT a language model), drop every sentence the groundedness check cannot support, and cite the passage each kept sentence relies on.

What a person cannot see is invisible all the way through: not searched, not ranked, not cited, not counted, not named in a refusal. "Not found" reads the same whether
the answer is missing or restricted.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from lorefern import grounding, search
from lorefern.injection import is_injection
from lorefern.models import Chunk, Document, Owner
from lorefern.textproc import split_sentences, stem, stems
from lorefern.visibility import allowed_tags

RETRIEVAL_MIN = 0.40
T_NOT_FOUND = "I could not find this in the documents you can see. If it should be written down, ask the owner of the topic to add it."
T_REFUSE = "I can only answer questions about this company's own documents, meetings and tasks."
T_INSTRUCTION = "I answer questions from the company's documents. I do not follow instructions inside a question or inside a document."
T_CONFLICT = "Two documents give different answers. I have not picked one. Ask the owners to confirm the right one and fix the other."

COMPANY_CUES = {"we", "our", "us", "company", "pinegate", "team", "office", "client", "clients", "staff", "employee", "employees", "my", "i", "policy", "policies", "meeting", "task", "tasks", "project", "invoice", "invoices", "customer", "customers"}
OFF_TOPIC = re.compile(r"\b(poem|haiku|joke|story|song|recipe|lyrics|essay|horoscope|weather|capital of|who won|stock price|translate|write me|write a|tallest|highest mountain|population of|president of|prime minister|speed of light|boiling point|how far is)\b", re.I)
DECISION_Q = re.compile(r"\b(decid\w*|decision|agree\w*|approved?)\b", re.I)
TASK_INTENT = re.compile(r"\b(overdue|stuck|late|blocked|behind schedule) (tasks?|work|items?)\b|\bwhat(?:'s| is| are) (?:overdue|stuck|blocked|late)\b|\bstuck work\b", re.I)
TOPIC_CUES = {"salary", "salaries", "payroll", "budget", "pay", "offer", "wifi", "insurance", "benefits"}
BOILERPLATE = ("readme", "template", "index", "register")
WHY = re.compile(r"\b(why|reason|because|how come)\b", re.I)
BECAUSE = re.compile(r"\b(because|since|so that|given that|the reason is|due to|estimated)\b", re.I)
SIG = re.compile(r"\$\s?(\d[\d,]*(?:\.\d+)?)(?:\s?(million|k))?|(\d+)\s+(business hours?|working days?|days?|hours?|minutes?|months?|percent|working hours?)|next business day|same day|next working day", re.I)


@dataclass
class Citation:
    chunk_id: int
    document_id: int
    title: str
    section: str
    passage: str
    start: int  # offset of the passage inside the document text, for the source viewer highlight
    end: int
    updated_on: str = ""
    owner: str = ""
    doc_type: str = ""


@dataclass
class Sent:
    text: str
    kind: str = "fact"  # fact (checked) or template (no claim)
    chunk_id: int | None = None
    support: float = 1.0
    quote: str = ""
    removed: bool = False
    reason: str = ""

    def as_dict(self) -> dict:
        return {"text": self.text, "kind": self.kind, "chunk_id": self.chunk_id, "support": round(self.support, 3), "quote": self.quote, "removed": self.removed, "reason": self.reason}


@dataclass
class Answer:
    outcome: str  # answer, not_found, refuse, conflict, tasks
    text: str = ""
    sentences: list[Sent] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    retrieval: float = 0.0
    groundedness: float = 0.0
    reason: str = ""
    writer: str = "offline rules (not a language model)"
    conflict: list[dict] = field(default_factory=list)
    stale: bool = False
    items: list[dict] = field(default_factory=list)  # for task answers

    @property
    def confidence(self) -> float:
        return round(0.5 * self.retrieval + 0.5 * self.groundedness, 3) if self.outcome in {"answer", "conflict"} else 0.0

    def as_dict(self) -> dict:
        return {"outcome": self.outcome, "text": self.text, "sentences": [s.as_dict() for s in self.sentences], "citations": [c.__dict__ for c in self.citations], "retrieval": round(self.retrieval, 3),
                "groundedness": round(self.groundedness, 3), "confidence": self.confidence, "reason": self.reason, "writer": self.writer, "conflict": self.conflict, "stale": self.stale, "items": self.items}


class RulesWriter:
    """Pick the source sentences that together cover the most telling words of the question."""

    def write(self, question, passages, terms):
        total = sum(w for _, w in terms) or 1.0
        cands = [(s, cid) for cid, text in passages for s in split_sentences(text) if len(s.split()) >= 3 and not s.startswith("#") and not s.rstrip().endswith("?") and not is_injection(s)]
        covered: set[str] = set()
        chosen: list[tuple[str, int]] = []
        for _ in range(3):
            best, gain = None, 0.0
            for s, cid in cands:
                st = set(stems(s))
                g = sum(w for t, w in terms if t in st and t not in covered) / total
                if g > gain + 1e-9:
                    best, gain = (s, cid), g
            if best is None or gain < 0.14:
                break
            chosen.append(best)
            covered |= set(stems(best[0]))
        return chosen


def _clean(s: str) -> str:
    return re.sub(r"[*_`]", "", s).strip()


def _signature(s: str) -> set[tuple[str, str]]:
    out = set()
    for m in SIG.finditer(s):
        if m.group(1):
            out.add(("money", m.group(1).replace(",", "") + (m.group(2) or "").lower()))
        elif m.group(3):
            unit = m.group(4).lower().rstrip("s")
            out.add(("time" if any(x in unit for x in ("hour", "day", "minute")) else unit, f"{m.group(3)} {unit}"))
        else:
            out.add(("time", "next business day"))
    return out


def find_conflict(session: Session, hits: list[search.Hit], terms) -> tuple[Sent, Sent, Document, Document] | None:
    """Two different documents give a different value for the same thing. Compared only inside the hits this person may see."""
    ids = [h.chunk_id for h in hits[:8]]
    rows = session.execute(select(Chunk, Document).join(Document, Chunk.document_id == Document.id).where(Chunk.id.in_(ids))).all()
    best: dict[int, tuple[float, str, int, Document]] = {}
    for c, d in rows:
        for s in split_sentences(c.text):
            if not _signature(s) or is_injection(s):
                continue
            st = set(stems(s))
            sc = sum(w for t, w in terms if t in st)
            if sc > best.get(d.id, (0, "", 0, d))[0]:
                best[d.id] = (sc, s, c.id, d)
    order = sorted(best, key=lambda d: -best[d][0])[:5]
    for i in range(len(order)):
        for j in range(i + 1, len(order)):
            a, b = best[order[i]], best[order[j]]
            sa, sb = _signature(a[1]), _signature(b[1])
            kinds = {k for k, _ in sa} & {k for k, _ in sb}
            differ = any({v for k, v in sa if k == kd} != {v for k, v in sb if k == kd} for kd in kinds)
            wa, wb = set(stems(a[1])), set(stems(b[1]))
            total = sum(w for _, w in terms) or 1.0
            cover = lambda ws: sum(w for t, w in terms if t in ws) / total  # noqa: E731
            if differ and len(wa & wb) / max(1, len(wa | wb)) >= 0.25 and cover(wa) >= 0.25 and cover(wb) >= 0.25:
                return Sent(_clean(a[1]), "fact", a[2]), Sent(_clean(b[1]), "fact", b[2]), a[3], b[3]
    return None


def _passage_citation(chunk: Chunk, doc: Document, quote: str) -> Citation:
    """The passage is the document's own characters. The quote from the groundedness check can differ in white space or markup, so it is located again in the chunk with a tolerant pattern."""
    words = re.findall(r"\S+", quote or "")
    m = re.search(r"\s+".join(re.escape(w) for w in words), chunk.text) if words else None
    if m is not None:
        start, end, passage = chunk.start + m.start(), chunk.start + m.end(), chunk.text[m.start():m.end()]
    else:
        start, end, passage = chunk.start, chunk.end or chunk.start + len(chunk.text), chunk.text
    return Citation(chunk.id, doc.id, doc.title, chunk.section, passage.strip(), start, end, doc.updated_on.isoformat() if doc.updated_on else "", doc.owner, doc.doc_type)


def _check(session: Session, cands: list[tuple[str, int]], tags: tuple[str, ...], allowed_ids: list[int]) -> list[Sent]:
    rows = session.execute(select(Chunk, Document).join(Document, Chunk.document_id == Document.id).where(Chunk.id.in_(allowed_ids), Chunk.tag.in_(tags))).all()
    info = {c.id: (c, d) for c, d in rows}
    idf, _ = search.idf_table(session, tags)
    texts = [c.text for c, _ in info.values()]
    ents = grounding.entities_from(texts)
    chunks = [(cid, c.text) for cid, (c, d) in info.items()]
    ctx = {cid: f"{d.title} {c.section}" for cid, (c, d) in info.items()}
    out = []
    for text, cid in cands:
        text = _clean(text)
        sup = grounding.check_sentence(text, chunks, idf, ents, ctx)
        s = Sent(text, "fact", sup.chunk_id, sup.score, sup.quote)
        if not sup.supported:
            s.removed, s.reason = True, f"Not supported by the cited text (score {sup.score:.2f}, needed {grounding.THRESHOLD})."
        out.append(s)
    return out


def _task_answer(session: Session, ctx, tags: tuple[str, ...]) -> Answer:
    from lorefern import stuck

    items = stuck.detect(session, ctx.today(session), ctx.settings, tags)
    shown = [{"kind": s.kind, "task_id": s.task_id, "owner": s.owner, "days": s.days, "evidence": s.evidence} for s in items if s.kind != "overloaded"][:12]
    text = f"{len(shown)} tasks need attention." if shown else "No task is stuck right now."
    return Answer("tasks", text, [Sent(text, "template")], [], 1.0, 1.0, "Answered from the task list, not from documents.", items=shown)


def _rank(session: Session, hits: list[search.Hit], q: str, tags: tuple[str, ...], names: set[str]) -> list[search.Hit]:
    """Drop navigation pages (folder READMEs, templates, the index) unless nothing else matches, then order by how much of the question a chunk covers, with the search score as a tie breaker."""
    if not hits:
        return hits
    kinds = dict(session.execute(select(Document.id, Document.doc_type).where(Document.id.in_([h.document_id for h in hits]))).all())
    real = [h for h in hits if kinds.get(h.document_id) not in BOILERPLATE]
    pool = real or hits
    st = dict(session.execute(select(Chunk.id, Chunk.stems).where(Chunk.id.in_([h.chunk_id for h in pool]))).all())
    for h in pool:  # a person's name says who the question is about, not what it asks, so it counts for less
        h.coverage = search.coverage(session, q, st.get(h.chunk_id, ""), tags, soft=names)
    top = max(h.fused for h in pool) or 1.0
    return sorted(pool, key=lambda h: -(0.6 * h.coverage + 0.4 * h.fused / top))


HISTORY = re.compile(r"\b(previous|previously|former|formerly|used to|before|earlier|last year|original|originally|old|older|history|what changed|changed from|no longer|back then|in the past)\b", re.I)


def ask(session: Session, ctx, question: str, audience: str, writer=None) -> Answer:
    """Answer one question. A document marked superseded is left out of the answer when a current one covers the question (unless the question asks about the past),
    and when ONLY a superseded document covers it the answer says so."""
    notes: dict = {"left_out": [], "old_only": False}
    writer = writer or getattr(ctx, "writer", None) or (ctx.answer_writer(session) if hasattr(ctx, "answer_writer") else None)
    a = _ask(session, ctx, question, audience, writer, notes)
    if writer is not None and getattr(writer, "label", ""):
        a.writer = writer.label
        if getattr(writer, "note", ""):
            a.reason = (a.reason + " " if a.reason else "") + writer.note
    if notes["left_out"] and a.outcome == "answer":
        a.reason = (a.reason + " " if a.reason else "") + "Left out as replaced: " + ", ".join(notes["left_out"]) + "."
    if notes["old_only"] and a.outcome == "answer":
        a.stale = True
        a.reason = (a.reason + " " if a.reason else "") + "Only a document marked as replaced covers this, so check it with its owner."
    return a


def _drop_superseded(session: Session, hits: list[search.Hit], q: str, notes: dict) -> list[search.Hit]:
    if not hits:
        return hits
    ids = {h.document_id for h in hits}
    gone = {i for (i,) in session.execute(select(Document.id).where(Document.id.in_(ids), Document.status == "superseded"))}
    if not gone or HISTORY.search(q):
        return hits
    current = [h for h in hits if h.document_id not in gone]
    top_old = max(h.coverage for h in hits if h.document_id in gone)
    top_new = max((h.coverage for h in current), default=0.0)
    if top_new < RETRIEVAL_MIN or top_new < 0.7 * top_old:  # no current document covers the question about as well
        notes["old_only"] = True
        return [h for h in hits if h.document_id in gone] if top_new < RETRIEVAL_MIN else hits
    titles = dict(session.execute(select(Document.id, Document.title).where(Document.id.in_(gone))).all())
    notes["left_out"] = sorted({titles[h.document_id] for h in hits if h.document_id in gone})
    return current


def _ask(session: Session, ctx, question: str, audience: str, writer, notes: dict) -> Answer:
    writer = writer or getattr(ctx, "writer", None) or RulesWriter()
    tags = allowed_tags(audience)
    q = (question or "").strip()
    if not q:
        return Answer("refuse", T_REFUSE, [Sent(T_REFUSE, "template")], reason="The question is empty.")
    if is_injection(q):
        return Answer("refuse", T_INSTRUCTION, [Sent(T_INSTRUCTION, "template")], reason="The question contains an instruction aimed at the system. It was not followed.")
    if OFF_TOPIC.search(q):
        return Answer("refuse", T_REFUSE, [Sent(T_REFUSE, "template")], reason="The question is not about the company.")
    if TASK_INTENT.search(q):
        return _task_answer(session, ctx, tags)
    names = {stem(p) for (n,) in session.execute(select(Owner.name)) for p in n.split()}
    hits = _drop_superseded(session, _rank(session, search.search(session, q, tags, 12), q, tags, names), q, notes)[:8]
    strength = max((h.coverage for h in hits[:3]), default=0.0)
    if strength < RETRIEVAL_MIN:
        return Answer("not_found", T_NOT_FOUND, [Sent(T_NOT_FOUND, "template")], retrieval=strength, reason=f"The best visible source covers only {strength:.0%} of the question (needed {RETRIEVAL_MIN:.0%}).")
    gone = search.unmatched_terms(session, q, tags, names)
    if gone and strength < 0.6:
        return Answer("not_found", T_NOT_FOUND, [Sent(T_NOT_FOUND, "template")], retrieval=strength, reason=f"The documents you can see never use the word '{gone[0]}' and nothing close to it, so the match is probably by chance.")
    terms = search.query_terms(session, q, tags, 8, soft=names)
    conflict = find_conflict(session, hits, terms) if re.search(r"\b(how|what|when|from what|at what|limit|amount|rule|days?|hours?|much|many)\b", q, re.I) else None
    if conflict:
        a, b, da, db = conflict
        newer_a = (da.updated_on or db.updated_on) >= (db.updated_on or da.updated_on) if da.updated_on and db.updated_on else True
        if da.status == "superseded" or db.status == "superseded":
            past = bool(HISTORY.search(q))
            win = (a if da.status == "superseded" else b) if past else (b if da.status == "superseded" else a)
            sents = _check(session, [(win.text, win.chunk_id)], tags, [win.chunk_id])
            kept = [s for s in sents if not s.removed]
            if kept:
                cs = session.get(Chunk, kept[0].chunk_id)
                text = " ".join(s.text for s in kept)
                return Answer("answer", ("Before it was replaced, the document said: " + text) if past else text, sents, [_passage_citation(cs, session.get(Document, cs.document_id), kept[0].quote)], strength, kept[0].support,
                              "You asked about the past, so the replaced document is used." if past else "One document is marked superseded, so the current one is used.", stale=past)
        sents = _check(session, [(a.text, a.chunk_id), (b.text, b.chunk_id)], tags, [a.chunk_id, b.chunk_id])
        kept = [s for s in sents if not s.removed]
        cites = []
        for s in kept:
            c = session.get(Chunk, s.chunk_id)
            cites.append(_passage_citation(c, session.get(Document, c.document_id), s.quote))
        info = [{"title": d.title, "owner": d.owner, "updated_on": d.updated_on.isoformat() if d.updated_on else "", "says": s.text} for s, d in ((a, da), (b, db))]
        return Answer("conflict", " ".join(s.text for s in kept) + " " + T_CONFLICT, sents + [Sent(T_CONFLICT, "template")], cites, strength, sum(s.support for s in kept) / max(1, len(kept)),
                      "Two documents the person can see disagree and neither is marked superseded.", conflict=info, stale=not newer_a)
    rows = session.execute(select(Chunk, Document).join(Document, Chunk.document_id == Document.id).where(Chunk.id.in_([h.chunk_id for h in hits]))).all()
    info_ = {c.id: (c, d) for c, d in rows}
    passages = [(h.chunk_id, info_[h.chunk_id][0].text) for h in hits[:4]]
    cands = writer.write(q, passages, terms)
    if DECISION_Q.search(q):
        dec = [(sn, cid) for cid, text in passages for sn in split_sentences(text) if re.search(r"\b(decided|agreed|decision|approve|approved|going with|go with)\b", sn, re.I) and not sn.rstrip().endswith("?") and not is_injection(sn)]
        if dec:
            st_q = set(stems(q)) - {"decid", "decision", "agre", "approv"}
            best = max(dec, key=lambda r: len(st_q & set(stems(r[0]))))
            if len(st_q & set(stems(best[0]))) >= 1:
                cands = [best] + [c for c in cands if c != best][:2]
    if WHY.search(q):  # a why question needs the sentence that gives the reason, if one exists in the same passages
        reasons = [(sn, cid) for cid, text in passages for sn in split_sentences(text) if BECAUSE.search(sn) and not is_injection(sn)]
        if reasons:
            st_q = set(stems(q))
            best = max(reasons, key=lambda r: len(st_q & set(stems(r[0]))))
            if best not in cands and len(st_q & set(stems(best[0]))) >= 1:
                cands = cands[:2] + [best]
    if not cands:
        return Answer("not_found", T_NOT_FOUND, [Sent(T_NOT_FOUND, "template")], retrieval=strength, reason="No sentence in the visible sources covers the question.")
    sents = _check(session, cands, tags, [h.chunk_id for h in hits])
    kept = [s for s in sents if not s.removed]
    if not kept:
        return Answer("not_found", T_NOT_FOUND, sents + [Sent(T_NOT_FOUND, "template")], retrieval=strength, reason="Every drafted sentence failed the groundedness check, so nothing was claimed.")
    cites, seen = [], set()
    for s in kept:
        c, d = info_.get(s.chunk_id) or (session.get(Chunk, s.chunk_id), None)
        d = d or session.get(Document, c.document_id)
        if c.id not in seen:
            seen.add(c.id)
            cites.append(_passage_citation(c, d, s.quote))
    stale = any(info_[s.chunk_id][1].outdated for s in kept if s.chunk_id in info_)
    removed = len(sents) - len(kept)
    return Answer("answer", " ".join(s.text for s in kept), sents, cites, strength, sum(s.support for s in kept) / len(kept),
                  (f"{removed} unsupported sentence(s) were removed. " if removed else "") + ("A cited document is more than 18 months old." if stale else ""), stale=stale)
