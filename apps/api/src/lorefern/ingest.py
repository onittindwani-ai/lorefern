"""Bring documents, Slack days and meeting transcripts into the index, each with a visibility tag.

Tag rule (fail closed): a source with a default tag other than `company` fixes the tag of everything in it. A `company` source may tag single documents (front matter
`visibility:`, or a Slack channel map). A tag nobody recognises becomes `leadership`, the narrowest one, never a wider one.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from lorefern import search
from lorefern.adapters.base import RemoteDoc, RemoteMeeting
from lorefern.chunking import ParsedDoc, chunk_document, content_hash, parse_pdf, parse_text, stems_for_index
from lorefern.injection import is_injection
from lorefern.models import TAGS, Chunk, Document, Meeting, Source, Transcript
from lorefern.textproc import split_sentences, stems

MAX_FILE_BYTES = 10 * 1024 * 1024
STALE_AFTER_DAYS = 540
NARROWEST = "leadership"


def resolve_tag(source: Source, wanted: str = "") -> str:
    if source.default_tag != "company":
        return source.default_tag if source.default_tag in TAGS else NARROWEST
    w = (wanted or "").strip().lower()
    if not w:
        return "company"
    return w if w in TAGS else NARROWEST


def _date(v: str | None) -> date | None:
    try:
        return date.fromisoformat((v or "").strip()) if v else None
    except ValueError:
        return None


GONE_WORDS = {"superseded", "withdrawn", "obsolete", "retired", "deprecated", "archived", "replaced", "expired", "outdated", "void", "revoked", "rescinded"}
BANNER = re.compile(r"\b(?:this (?:document|policy|page|version|procedure|guide|sop|file|note)\s+(?:has been|was|is|is now)\s+(?:superseded|replaced|withdrawn|retired|obsolete|archived|rescinded)|superseded by|replaced by|no longer (?:in force|valid|current)|rescinded|withdrawn)\b", re.I)
REPLACES_KEYS = ("supersedes", "replaces", "replaced", "obsoletes")
REPLACED_BY_KEYS = ("superseded_by", "replaced_by", "obsoleted_by", "superseded-by", "replaced-by")


def banner_in(text: str) -> bool:
    """A banner is in one of the first three short lines of the document (not a sentence deep inside it)."""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()][:3]
    return any(len(ln) <= 200 and BANNER.search(ln) for ln in lines)


def detect_status(meta: dict, text: str, banner: bool = True) -> str:
    """The document's status. 'superseded' when the front matter says it was replaced (a status word, or a replaced by field) or when its first lines carry a banner saying so.
    General document keeping habits, not a list of any one company's files."""
    st = (meta.get("status") or "").strip().lower()
    if st in GONE_WORDS or any((meta.get(k) or "").strip() for k in REPLACED_BY_KEYS):
        return "superseded"
    if banner and banner_in(text):
        return "superseded"
    return st[:20]


def _norm_ref(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower().rsplit("/", 1)[-1].rsplit(".", 1)[0]).strip()


def resolve_replacements(session: Session, pairs: list[tuple[Document, dict]]) -> int:
    """A document whose front matter says `supersedes` or `replaces` (one or more references, by path, file name, title or doc id) makes those documents superseded.
    The target is found only inside the same list of documents. Returns how many documents were marked."""
    by_ref: dict[str, list[Document]] = {}
    for d, meta in pairs:
        for key in (d.external_id, d.slug, d.title, (meta.get("doc_id") or "")):
            if key:
                by_ref.setdefault(_norm_ref(key), []).append(d)
    marked = 0
    for d, meta in pairs:
        for k in REPLACES_KEYS:
            for ref in re.split(r"[;,]|\s{2,}", meta.get(k) or ""):
                hits = by_ref.get(_norm_ref(ref.strip().strip("[]\"'")), []) if ref.strip() else []
                for target in {x.id: x for x in hits}.values():
                    if target.id != d.id and target.status != "superseded":
                        target.status = "superseded"
                        marked += 1
    session.flush()
    return marked


def guess_type(rel: str, meta: dict, title: str) -> str:
    t = (meta.get("type") or "").strip().lower()
    if t:
        return t
    low = f"{rel} {title}".lower()
    for key, name in (("sop", "sop"), ("decision", "decision"), ("meeting", "meeting_note"), ("client brief", "client_brief"), ("brief", "client_brief"), ("readme", "readme"), ("policy", "policy")):
        if key in low:
            return name
    return "other"


def store_document(session: Session, source: Source, external_id: str, parsed: ParsedDoc, today: date | None = None, tag_hint: str = "", rel: str = "") -> tuple[Document, str]:
    """Insert or update one document and rebuild its chunks. Returns (document, 'new' | 'changed' | 'same')."""
    meta = parsed.meta or {}
    tag = resolve_tag(source, tag_hint or meta.get("visibility", ""))
    h = content_hash(parsed.text + "|" + tag)
    doc = session.scalar(select(Document).where(Document.source_id == source.id, Document.external_id == external_id))
    state = "new"
    if doc is not None:
        if doc.content_hash == h:
            return doc, "same"
        state = "changed"
        for c in list(doc.chunks):
            session.delete(c)
        session.flush()
    else:
        doc = Document(source_id=source.id, external_id=external_id)
        session.add(doc)
    doc.slug, doc.title, doc.kind, doc.updated_on, doc.content_hash, doc.text = parsed.slug, parsed.title[:300], parsed.kind, parsed.updated_on, h, parsed.text
    doc.tag, doc.owner = tag, (meta.get("owner") or source.owner or "")[:120]
    doc.review_by, doc.status = _date(meta.get("review_by")), detect_status(meta, parsed.text, banner=rel not in {"meeting", "slack"})
    doc.doc_type = guess_type(rel or external_id, meta, parsed.title)[:20]
    doc.outdated = bool(today and parsed.updated_on and (today - parsed.updated_on).days > STALE_AFTER_DAYS)
    doc.flagged = any(is_injection(s) for s in split_sentences(parsed.text))
    session.flush()
    for spec in chunk_document(parsed.title, parsed.text):
        session.add(Chunk(document_id=doc.id, tag=tag, ordinal=spec.ordinal, section=spec.section, context=spec.context, text=spec.text, start=spec.start, end=spec.end,
                          stems=stems_for_index(parsed.title, spec), vec=search.hashed_vec(stems(f"{parsed.title} {spec.section} {spec.context} {spec.text}"))))
    session.flush()
    return doc, state


def ingest_folder(session: Session, source: Source, folder: Path, today: date | None = None) -> dict:
    counts = {"new": 0, "changed": 0, "same": 0, "skipped": 0}
    pairs: list[tuple[Document, dict]] = []
    root = folder.resolve()
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in {".md", ".txt", ".pdf"}:
            continue
        if p.name == "INDEX.md":  # the index lists the title of every document, restricted ones included, so it is never read into the search index
            counts["skipped"] += 1
            continue
        try:
            p.resolve().relative_to(root)  # a link that points outside the folder is skipped
        except ValueError:
            counts["skipped"] += 1
            continue
        if p.stat().st_size > MAX_FILE_BYTES:
            counts["skipped"] += 1
            continue
        rel = str(p.relative_to(root))
        slug = re.sub(r"[^a-z0-9]+", "-", rel.rsplit(".", 1)[0].lower()).strip("-")
        try:
            parsed = parse_pdf(p.name, p.read_bytes(), slug) if p.suffix.lower() == ".pdf" else parse_text(p.name, p.read_text(errors="replace"), slug)
        except Exception:  # a damaged PDF must not stop the run
            counts["skipped"] += 1
            continue
        doc, state = store_document(session, source, rel, parsed, today, rel=rel)
        pairs.append((doc, parsed.meta or {}))
        counts[state] += 1
    counts["superseded_by_reference"] = resolve_replacements(session, pairs)
    search.rebuild(session)
    return counts


def ingest_remote(session: Session, source: Source, docs: list[RemoteDoc], today: date | None = None) -> dict:
    counts = {"new": 0, "changed": 0, "same": 0}
    for d in docs:
        slug = re.sub(r"[^a-z0-9]+", "-", d.title.lower()).strip("-") or d.external_id
        parsed = parse_text(d.title + ".md", d.text, slug)
        parsed.title = d.title or parsed.title
        parsed.updated_on = parsed.updated_on or _date(d.updated_on)
        counts[store_document(session, source, d.external_id, parsed, today, rel=d.title)[1]] += 1
    search.rebuild(session)
    return counts


def ingest_slack(session: Session, source: Source, days, channel_tags: dict[str, str] | None = None, today: date | None = None) -> dict:
    counts = {"new": 0, "changed": 0, "same": 0}
    for d in days:
        slug = f"slack-{d.channel}-{d.day}"
        body = f"# #{d.channel} on {d.day}\n\n{d.text}\n"
        parsed = ParsedDoc(f"#{d.channel} on {d.day}", body, "slack", date.fromisoformat(d.day), slug, {})
        doc, st = store_document(session, source, slug, parsed, today, tag_hint=(channel_tags or {}).get(d.channel, ""), rel="slack")
        doc.doc_type = "slack"
        counts[st] += 1
    search.rebuild(session)
    return counts


def transcript_text(lines: list[tuple[str, str]]) -> str:
    return "\n".join(f"{who}: {words}" for who, words in lines)


def ingest_meeting(session: Session, source: Source, m: RemoteMeeting, today: date | None = None, tag_hint: str = "") -> tuple[Meeting, str]:
    """Store one meeting, its transcript text, and an indexed document so questions can cite it. Lines that look like instructions are listed and never acted on."""
    held = _date(m.held_on) or (today or date.today())
    text = transcript_text(m.lines)
    tag = resolve_tag(source, tag_hint)
    mt = session.scalar(select(Meeting).where(Meeting.source_id == source.id, Meeting.external_id == m.external_id))
    state = "new" if mt is None else "changed"
    if mt is None:
        mt = Meeting(source_id=source.id, external_id=m.external_id, title=m.title[:300], held_on=held, provider=m.provider)
        session.add(mt)
        mt.transcript = Transcript(text=text)
    elif mt.transcript and mt.transcript.text == text and mt.tag == tag:
        return mt, "same"
    else:
        mt.transcript.text = text
        mt.extracted = False
    mt.tag, mt.attendees = tag, sorted({w for w, _ in m.lines})
    mt.flagged_lines = [f"{w}: {t}" for w, t in m.lines if is_injection(t)]
    session.flush()
    slug = f"meeting-{held.isoformat()}-{re.sub(r'[^a-z0-9]+', '-', m.title.lower()).strip('-')[:50]}"
    parsed = ParsedDoc(f"{m.title} ({held.isoformat()})", f"# {m.title}\n\n{text}\n", "transcript", held, slug, {})
    doc, _ = store_document(session, source, f"meeting:{m.external_id}", parsed, today, tag_hint=tag, rel="meeting")
    doc.doc_type = "meeting_note"
    mt.document_id = doc.id
    session.flush()
    return mt, state


def sync_meetings(session: Session, ctx, today: date | None = None) -> dict:
    """Read the selected meetings adapter (a recorder or a folder of transcripts) into the database. Extraction happens later, and only proposes."""
    counts = {"new": 0, "changed": 0, "same": 0}
    found = ctx.adapters.meetings.list_meetings()
    if not found:
        return counts
    src = session.scalar(select(Source).where(Source.kind == "meetings"))
    if src is None:
        src = Source(kind="meetings", name="Meeting transcripts", uri=ctx.settings.meetings_adapter, default_tag="company", reliability="A", owner="", status="ready")
        session.add(src)
        session.flush()
    for m in found:
        _, st = ingest_meeting(session, src, m, today, tag_hint=getattr(m, "visibility", ""))
        counts[st] += 1
    src.last_synced_at, src.status, src.error = ctx.now(session), "ready", ""
    search.rebuild(session)
    return counts
