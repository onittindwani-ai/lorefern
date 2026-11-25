"""Bring documents, Slack days and meeting transcripts into the index, each with a visibility tag.

Tag rule (fail closed, the narrowest wins): a source with a default tag other than `company` fixes the tag of everything in it. In a `company` source a document gets the NARROWEST
of its own tag (front matter or transcript header `visibility:`, a Slack channel map, a PDF property) and the tags of every folder above it (a `.visibility` file or the folder README,
each nested folder narrowing its parent, never widening it). A document may only narrow what its folder says; `visibility: inherit` means "no opinion". A document with no tag
at all, in a folder with none, gets the tag the owner chose for that source's unlabelled items (see untagged.py), and when there is none, the NARROWEST tag.
A tag nobody recognises becomes the narrowest tag too, never a wider one.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from lorefern import search, source_tags, untagged
from lorefern.adapters.base import RemoteDoc, RemoteMeeting
from lorefern.chunking import ParsedDoc, chunk_document, content_hash, normalise_text, parse_pdf, parse_text, stems_for_index
from lorefern.foldertag import folder_declared_tag
from lorefern.injection import is_injection
from lorefern.models import TAGS, Chunk, Decision, Document, Meeting, Process, Source, Task, Transcript
from lorefern.textproc import split_sentences, stems
from lorefern.visibility import audiences_of, declared_tag, meet_tag, narrowest_tag

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FILES = 5000  # most files one read looks at
MAX_TOTAL_BYTES = 500 * 1024 * 1024  # most bytes one read looks at. A read that hits either limit stops, says so, and removes nothing.
STALE_AFTER_DAYS = 540
SKIP_DIRS = {"node_modules", "__pycache__"}
MEETINGS_DIR = "meetings"  # the meetings reader owns this folder, and it carries each transcript's own visibility header


def _narrowest() -> str:
    return narrowest_tag()


def resolve_tag(source: Source, wanted: str = "", inherited: str = "", unlabelled: str = "") -> str:
    """The tag of one item. `wanted` is what the item says about itself, `inherited` what its folders say (already the narrowest of them), `unlabelled` what the owner chose for unlabelled
    items of this source. The narrowest of everything that was written wins: a restricted source fixes the tag and an item may only narrow it further, and in an open (`company`)
    source the item's own tag and its folder's tag are combined the same way, so a document can never be wider than the folder it sits in. When nothing was written the owner's
    choice for this source applies, and when there is none the narrowest tag."""
    if source.default_tag != "company":
        base = source.default_tag if source.default_tag in TAGS else _narrowest()
        own = [c for c in (wanted, inherited) if (c or "").strip().lower() in TAGS]
        return meet_tag(base, declared_tag(*own)) if own else base
    return declared_tag(wanted, inherited) or declared_tag(unlabelled) or _narrowest()


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
    The target is found only inside the same list of documents, and only when the claim can be trusted: both documents have the same owner (or neither names one),
    and everyone who may see the replaced document may also see the replacing one. Every read starts from what each document says about itself, so deleting the
    replacing file puts the replaced one back. Returns how many documents were marked."""
    for d, meta in pairs:
        d.status = detect_status(meta, d.text, banner=True)
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
                    if target.id == d.id or target.status == "superseded":
                        continue
                    same_owner = (d.owner or "").strip().lower() == (target.owner or "").strip().lower()
                    if same_owner and audiences_of(target.tag) <= audiences_of(d.tag):
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


def store_document(session: Session, source: Source, external_id: str, parsed: ParsedDoc, today: date | None = None, tag_hint: str = "", rel: str = "", inherited: str = "") -> tuple[Document, str]:
    """Insert or update one document and rebuild its chunks. Returns (document, 'new' | 'changed' | 'same')."""
    meta = parsed.meta or {}
    tag = resolve_tag(source, tag_hint or meta.get("visibility", ""), inherited, untagged.get(session, source.id))
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


def store_safely(session: Session, counts: dict, *args, **kwargs) -> tuple[Document | None, str]:
    """store_document inside its own savepoint: one file the database refuses is counted as failed and the rest of the read goes on."""
    try:
        with session.begin_nested():
            return store_document(session, *args, **kwargs)
    except Exception:  # a bad file must not stop the read. The failure is counted, and the old copy of that document (if any) stays as it was
        counts["failed"] = counts.get("failed", 0) + 1
        return None, "failed"


def remove_documents(session: Session, docs: list[Document]) -> int:
    """Take documents out of the index: their passages go with them, and nothing is left pointing at them."""
    ids = [d.id for d in docs]
    if not ids:
        return 0
    session.execute(update(Meeting).where(Meeting.document_id.in_(ids)).values(document_id=None))
    session.execute(update(Decision).where(Decision.document_id.in_(ids)).values(document_id=None))
    session.execute(update(Process).where(Process.sop_id.in_(ids)).values(sop_id=None, coverage="gap"))
    for d in docs:
        session.delete(d)
    session.flush()
    return len(ids)


def remove_missing(session: Session, source: Source, seen: set[str]) -> int:
    """After a read that finished, drop every document of the source that the read did not see: deleted, moved, renamed or no longer shared files must not stay searchable."""
    gone = [d for d in session.scalars(select(Document).where(Document.source_id == source.id)) if d.external_id not in seen]
    return remove_documents(session, gone)


def ingest_folder(session: Session, source: Source, folder: Path, today: date | None = None, exclude: tuple[Path, ...] = ()) -> dict:
    """Read a folder of markdown, text and PDF files. `exclude` lists sub folders that belong to another source (a stricter one), which this read leaves alone."""
    counts = {"new": 0, "changed": 0, "same": 0, "skipped": 0, "removed": 0}
    pairs: list[tuple[Document, dict]] = []
    root = folder.resolve()
    if not root.is_dir():
        raise FileNotFoundError("The folder is not there, so nothing was read and nothing was removed.")
    skip_roots = tuple(p.resolve() for p in exclude)
    seen: set[str] = set()
    cache: dict = {}
    files = total = 0
    complete = True
    for p in sorted(root.rglob("*")):
        if not p.is_file() or p.suffix.lower() not in {".md", ".txt", ".pdf"}:
            continue
        parts = p.relative_to(root).parts
        if any(x.startswith(".") or x in SKIP_DIRS for x in parts[:-1]) or p.name.startswith("."):
            counts["skipped"] += 1  # hidden folders, trash and package folders are never read
            continue
        if p.name == "INDEX.md":  # the index lists the title of every document, restricted ones included, so it is never read into the search index
            counts["skipped"] += 1
            continue
        if (len(parts) > 1 and parts[0] == MEETINGS_DIR) or root.name == MEETINGS_DIR:
            counts["skipped"] += 1  # transcripts are read by the meetings reader, with the visibility each one declares
            continue
        try:
            resolved = p.resolve()
            resolved.relative_to(root)  # a link that points outside the folder is skipped
        except ValueError:
            counts["skipped"] += 1
            continue
        if any(resolved == s or s in resolved.parents for s in skip_roots):
            counts["skipped"] += 1  # this sub folder is another source's, with its own tag
            continue
        rel = str(p.relative_to(root))
        seen.add(rel)  # a file that is there but cannot be read keeps its old copy
        size = p.stat().st_size
        if size > MAX_FILE_BYTES:
            counts["skipped"] += 1
            continue
        files, total = files + 1, total + size
        if files > MAX_FILES or total > MAX_TOTAL_BYTES:
            complete = False
            counts["truncated"] = 1
            break
        slug = re.sub(r"[^a-z0-9]+", "-", rel.rsplit(".", 1)[0].lower()).strip("-")
        try:
            parsed = parse_pdf(p.name, p.read_bytes(), slug) if p.suffix.lower() == ".pdf" else parse_text(p.name, p.read_text(errors="replace"), slug)
        except Exception:  # a damaged PDF must not stop the run
            counts["skipped"] += 1
            continue
        doc, state = store_safely(session, counts, source, rel, parsed, today, rel=rel, inherited=folder_declared_tag(p.parent, root, cache))
        if doc is None:
            continue
        pairs.append((doc, parsed.meta or {}))
        counts[state] += 1
    if complete:
        counts["removed"] = remove_missing(session, source, seen)
    counts["superseded_by_reference"] = resolve_replacements(session, pairs)
    search.rebuild(session)
    return counts


def held_elsewhere(session: Session, source: Source) -> set[str]:
    """File ids held by another source of the same kind that names its own folders or pages. A source that names none must not also hold those files."""
    others = session.scalars(select(Source.id).where(Source.kind == source.kind, Source.id != source.id, Source.uri != ""))
    ids = [i for i in others]
    if not ids:
        return set()
    return set(session.scalars(select(Document.external_id).where(Document.source_id.in_(ids))))


def ingest_remote(session: Session, source: Source, docs: list[RemoteDoc], today: date | None = None) -> dict:
    """Store what a Drive or Notion read returned. A file the read no longer returns (deleted, trashed, unshared, moved out of the chosen folders) is removed from the index, but only when the read
    says it saw everything (`docs.complete`): a read that hit a limit or could not read a file removes nothing.
    A source that names its own folders or pages takes its files from every other source of the same kind, and one that names none leaves those files to them."""
    counts = {"new": 0, "changed": 0, "same": 0, "removed": 0}
    complete = getattr(docs, "complete", True)  # read before the list is filtered below
    if not source.uri:
        taken = held_elsewhere(session, source)
        docs = [d for d in docs if d.external_id not in taken]
    seen = {d.external_id for d in docs}
    for d in docs:
        slug = re.sub(r"[^a-z0-9]+", "-", d.title.lower()).strip("-") or d.external_id
        parsed = parse_text(d.title + ".md", d.text, slug)
        parsed.title = normalise_text(d.title) or parsed.title
        parsed.updated_on = parsed.updated_on or _date(d.updated_on)
        doc, state = store_safely(session, counts, source, d.external_id, parsed, today, rel=d.title)
        if doc is not None:
            counts[state] += 1
    if complete:
        counts["removed"] = remove_missing(session, source, seen)
    else:
        counts["incomplete"] = 1  # the read did not see everything, so a file it did not return is not known to be gone: nothing is removed
    if source.uri:
        mine = [x for x in session.scalars(select(Document).where(Document.external_id.in_(seen), Document.source_id != source.id)) if x.source.kind == source.kind]
        counts["removed"] += remove_documents(session, mine)
    search.rebuild(session)
    return counts


def ingest_slack(session: Session, source: Source, days, channel_tags: dict[str, str] | None = None, today: date | None = None) -> dict:
    counts = {"new": 0, "changed": 0, "same": 0, "removed": 0}
    seen: set[str] = set()
    for d in days:
        slug = f"slack-{d.channel}-{d.day}"
        seen.add(slug)
        body = f"# #{d.channel} on {d.day}\n\n{normalise_text(d.text)}\n"
        try:
            day = date.fromisoformat(d.day)
        except ValueError:  # a member name of 15 characters is not a day
            counts["failed"] = counts.get("failed", 0) + 1
            continue
        parsed = ParsedDoc(f"#{d.channel} on {d.day}", body, "slack", day, slug, {})
        doc, st = store_safely(session, counts, source, slug, parsed, today, tag_hint=(channel_tags or {}).get(d.channel, ""), rel="slack")
        if doc is None:
            continue
        doc.doc_type = "slack"
        counts[st] += 1
    counts["removed"] = remove_missing(session, source, seen)
    search.rebuild(session)
    return counts


def transcript_text(lines: list[tuple[str, str]]) -> str:
    return "\n".join(f"{who}: {words}" for who, words in lines)


def ingest_meeting(session: Session, source: Source, m: RemoteMeeting, today: date | None = None, tag_hint: str = "") -> tuple[Meeting, str]:
    """Store one meeting, its transcript text, and an indexed document so questions can cite it. Lines that look like instructions are listed and never acted on."""
    held = _date(m.held_on) or (today or date.today())
    text = normalise_text(transcript_text(m.lines))
    tag = resolve_tag(source, tag_hint, "", untagged.get(session, source.id))
    mt = session.scalar(select(Meeting).where(Meeting.source_id == source.id, Meeting.external_id == m.external_id))
    state = "new" if mt is None else "changed"
    was = None if mt is None else mt.tag
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
    if was is not None and was != tag:
        retag_meeting_rows(session, mt, was, tag)
    slug = f"meeting-{held.isoformat()}-{re.sub(r'[^a-z0-9]+', '-', m.title.lower()).strip('-')[:50]}"
    parsed = ParsedDoc(f"{m.title} ({held.isoformat()})", f"# {m.title}\n\n{text}\n", "transcript", held, slug, {})
    doc, _ = store_document(session, source, f"meeting:{m.external_id}", parsed, today, tag_hint=tag, rel="meeting")
    doc.doc_type = "meeting_note"
    mt.document_id = doc.id
    session.flush()
    return mt, state


def retag_meeting_rows(session: Session, meeting: Meeting, was: str, now: str) -> None:
    """The tasks and decisions found in a meeting always carry the meeting's tag. When the tag changes they follow it. When it narrows (some audience can no longer see the meeting),
    text built earlier that may quote it (weekly reviews, process evidence, stored answers) is cleared, so the next job builds it again without the meeting."""
    session.execute(update(Task).where(Task.meeting_id == meeting.id).values(tag=now))
    session.execute(update(Decision).where(Decision.meeting_id == meeting.id).values(tag=now))
    if not audiences_of(was) <= audiences_of(now):
        source_tags.scrub_derived(session, now)
    search.clear_cache()


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
        try:
            with session.begin_nested():  # one transcript the database refuses must not stop the others
                _, st = ingest_meeting(session, src, m, today, tag_hint=getattr(m, "visibility", ""))
        except Exception:
            counts["failed"] = counts.get("failed", 0) + 1
            continue
        counts[st] += 1
    src.last_synced_at, src.status, src.error = ctx.now(session), "ready", ""
    search.rebuild(session)
    return counts
