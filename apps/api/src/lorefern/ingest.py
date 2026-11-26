"""Bring documents, Slack days and meeting transcripts into the index, each with a visibility tag.

Tag rule (fail closed, the narrowest wins): a source with a default tag other than `company` fixes the tag of everything in it. In a `company` source a document gets the NARROWEST
of its own tag (front matter or transcript header `visibility:`, a Slack channel map, a PDF property) and the tags of every folder above it (a `.visibility` file or the folder README,
each nested folder narrowing its parent, never widening it). A document may only narrow what its folder says; `visibility: inherit` means "no opinion". A document with no tag
at all, in a folder with none, gets the tag the owner chose for that source's unlabelled items (see untagged.py), and when there is none, the NARROWEST tag.
A tag nobody recognises becomes the narrowest tag too, never a wider one.
"""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from lorefern import search, source_tags, untagged
from lorefern.adapters.base import RemoteDoc, RemoteMeeting, RemoteMeetings
from lorefern.chunking import ParsedDoc, chunk_document, content_hash, normalise_text, parse_pdf, parse_text, stems_for_index
from lorefern.foldertag import folder_declared_tag
from lorefern.injection import is_injection
from lorefern.models import TAGS, Chunk, Decision, Document, Meeting, Process, Reminder, Source, Task, Transcript
from lorefern.textproc import split_sentences, stems
from lorefern.visibility import INHERIT, audiences_of, declared_tag, meet_tag, narrowest_tag

MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FILES = 5000  # most files one read looks at
MAX_TOTAL_BYTES = 500 * 1024 * 1024  # most bytes one read looks at. A read that hits either limit stops, says so, and removes nothing.
STALE_AFTER_DAYS = 540
SKIP_DIRS = {"node_modules", "__pycache__"}
MEETINGS_DIR = "meetings"  # the meetings reader owns this folder, and it carries each transcript's own visibility header
IMPORT_PREFIX = "import-"  # the external id of a transcript a person pasted in: no recorder or folder returns it, so a read of the recorder never removes it


def _narrowest() -> str:
    return narrowest_tag()


def own_tag(wanted: str = "", inherited: str = "", unlabelled: str = "") -> str:
    """The tag an item has in an open (`company`) source: the narrowest of what it and its folders wrote, else the owner's choice for unlabelled items, else the narrowest tag."""
    return declared_tag(wanted, inherited) or declared_tag(unlabelled) or _narrowest()


def resolve_tag(source: Source, wanted: str = "", inherited: str = "", unlabelled: str = "") -> str:
    """The tag of one item. `wanted` is what the item says about itself, `inherited` what its folders say (already the narrowest of them), `unlabelled` what the owner chose for unlabelled
    items of this source. The narrowest of everything that was written wins: a restricted source fixes the tag and an item may only narrow it further, and in an open (`company`)
    source the item's own tag and its folder's tag are combined the same way, so a document can never be wider than the folder it sits in. When nothing was written the owner's
    choice for this source applies, and when there is none the narrowest tag."""
    if source.default_tag != "company":
        base = source.default_tag if source.default_tag in TAGS else _narrowest()
        written = declared_tag(wanted, inherited)  # a tag nobody recognises (a typo) counts as the narrowest tag, so it can never leave the source's own tag in place
        return meet_tag(base, written) if written else base
    return own_tag(wanted, inherited, unlabelled)


def unrecognised_tag(*written: str) -> bool:
    """True when a document wrote a tag nobody recognises (a typo such as `peple`). It is treated as the narrowest tag, and the read counts it so the owner can fix the file."""
    return any((w or "").strip() and (w or "").strip().lower() not in TAGS and (w or "").strip().lower() != INHERIT for w in written)


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


def _folder_of(external_id: str) -> str:
    """The folder part of a document's path in its source ("" for a file at the top, and for a Drive or Notion id, which has no path)."""
    return external_id.rsplit("/", 1)[0] if "/" in external_id else ""


def _may_retire(replacing: Document, target: Document) -> bool:
    """A document may retire another only from the same folder or a folder above it: a file added somewhere else cannot take a policy away from the folder that holds it."""
    mine, theirs = _folder_of(replacing.external_id), _folder_of(target.external_id)
    return mine == theirs or mine == "" or theirs.startswith(mine + "/")


def resolve_replacements(session: Session, pairs: list[tuple[Document, dict]]) -> int:
    """A document whose front matter says `supersedes` or `replaces` (one or more references, by path, file name, title or doc id) makes those documents superseded.
    The target is found only inside the same list of documents, and only when the claim can be trusted: both documents have the same owner (or neither names one), the replacing
    document sits in the same folder as the replaced one or in a folder above it, and everyone who may see the replaced document may also see the replacing one. Whoever may add files to a
    folder can still retire a document in it, as they could edit it: the folders are the boundary, so limit who can write to them (docs/13). Every read starts from what each document says about itself, so deleting the
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
                    if same_owner and _may_retire(d, target) and audiences_of(target.tag) <= audiences_of(d.tag):
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


def store_document(session: Session, source: Source, external_id: str, parsed: ParsedDoc, today: date | None = None, tag_hint: str = "", rel: str = "", inherited: str = "",
                   own_log: dict[int, str] | None = None, unknown: list[str] | None = None) -> tuple[Document, str]:
    """Insert or update one document and rebuild its chunks. Returns (document, 'new' | 'changed' | 'same').
    `own_log` collects, for a restricted source, the tag each document would have in an open one (see source_tags.note_own). `unknown` collects the documents that wrote a tag nobody recognises."""
    meta = parsed.meta or {}
    wanted, unlabelled = tag_hint or meta.get("visibility", ""), untagged.get(session, source.id)
    if unknown is not None and unrecognised_tag(wanted):
        unknown.append(external_id)
    tag = resolve_tag(source, wanted, inherited, unlabelled)
    h = content_hash(parsed.text + "|" + tag)
    doc = session.scalar(select(Document).where(Document.source_id == source.id, Document.external_id == external_id))
    state = "new"
    if doc is not None:
        if doc.content_hash == h:
            if own_log is not None:
                own_log[doc.id] = own_tag(wanted, inherited, unlabelled)
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
    if own_log is not None:
        own_log[doc.id] = own_tag(wanted, inherited, unlabelled)
    return doc, state


def note_reads(session: Session, source: Source, own_log: dict[int, str]) -> None:
    """After a read of a restricted source, remember for each document the tag it has in an open source, so that setting the source back gives it the right one."""
    if source.default_tag != "company" and own_log:
        source_tags.note_own(session, source.id, "d", own_log)


def store_safely(session: Session, counts: dict, *args, **kwargs) -> tuple[Document | None, str]:
    """store_document inside its own savepoint: one file the database refuses is counted as failed and the rest of the read goes on. A document that wrote a tag nobody recognises
    is stored with the narrowest tag and counted in `unknown_tags`."""
    unknown: list[str] = []
    try:
        with session.begin_nested():
            out = store_document(session, *args, unknown=unknown, **kwargs)
    except Exception:  # a bad file must not stop the read. The failure is counted, and the old copy of that document (if any) stays as it was
        counts["failed"] = counts.get("failed", 0) + 1
        return None, "failed"
    if unknown:
        counts["unknown_tags"] = counts.get("unknown_tags", 0) + 1
    return out


def remove_documents(session: Session, docs: list[Document]) -> int:
    """Take documents out of the index: their passages go with them, and nothing is left pointing at them."""
    ids = [d.id for d in docs]
    if not ids:
        return 0
    tags = {d.tag for d in docs}
    session.execute(update(Meeting).where(Meeting.document_id.in_(ids)).values(document_id=None))
    session.execute(update(Decision).where(Decision.document_id.in_(ids)).values(document_id=None))
    session.execute(update(Process).where(Process.sop_id.in_(ids)).values(sop_id=None, coverage="gap"))
    for d in docs:
        session.delete(d)
    session.flush()
    source_tags.scrub_removed(session, tags)  # stored answers may quote what is now gone
    search.clear_cache()
    return len(ids)


def remove_meetings(session: Session, meetings: list[Meeting]) -> int:
    """Take meetings out of the app: the transcript, its indexed document and passages, the decisions that are still only proposals or were rejected, and the tasks that are still only
    proposals or were rejected. A task a person already approved is work someone may be doing, and a decision a person confirmed is the company's record, so both stay, but neither
    quotes the transcript or points at it any more (a decision then shows its source as gone; a renamed file is therefore a new meeting). Weekly reviews,
    process evidence and stored answers that may quote the meeting are cleared. Returns how many meetings were removed."""
    if not meetings:
        return 0
    ids = [m.id for m in meetings]
    tasks = list(session.scalars(select(Task).where(Task.meeting_id.in_(ids))))
    gone = [t for t in tasks if t.status in {"proposed", "rejected"}]
    for t in tasks:
        if t not in gone:
            t.meeting_id, t.quote, t.quote_start = None, "", -1
    if gone:
        session.execute(delete(Reminder).where(Reminder.task_id.in_([t.id for t in gone])))
        for t in gone:
            session.delete(t)
    for dec in session.scalars(select(Decision).where(Decision.meeting_id.in_(ids))):
        if dec.status == "confirmed":  # a person confirmed it: it is the company's record. It stays with its title, date and tag, no longer quotes the transcript, and shows its source as gone
            dec.meeting_id, dec.quote, dec.quote_start, dec.why = None, "", -1, ""
        else:
            session.delete(dec)
    session.flush()
    docs = [d for d in (session.get(Document, m.document_id) for m in meetings if m.document_id) if d is not None]
    tags = {m.tag for m in meetings}
    for m in meetings:
        session.delete(m)
    session.flush()
    remove_documents(session, docs)
    source_tags.scrub_removed(session, tags, derived=True)  # reviews and process evidence are built from meetings
    search.clear_cache()
    return len(ids)


def remove_missing(session: Session, source: Source, seen: set[str]) -> int:
    """After a read that finished, drop every document of the source that the read did not see: deleted, moved, renamed or no longer shared files must not stay searchable."""
    gone = [d for d in session.scalars(select(Document).where(Document.source_id == source.id)) if d.external_id not in seen]
    return remove_documents(session, gone)


def ingest_folder(session: Session, source: Source, folder: Path, today: date | None = None, exclude: tuple[Path, ...] = (), tag_root: Path | None = None) -> dict:
    """Read a folder of markdown, text and PDF files. `exclude` lists sub folders that belong to another source (a stricter one), which this read leaves alone. `tag_root` is the
    top of the folder tree whose `.visibility` files and READMEs count (the knowledge folder): a source that points at a sub folder still obeys every folder above it."""
    counts = {"new": 0, "changed": 0, "same": 0, "skipped": 0, "removed": 0}
    pairs: list[tuple[Document, dict]] = []
    root = folder.resolve()
    if not root.is_dir():
        raise FileNotFoundError("The folder is not there, so nothing was read and nothing was removed.")
    top = tag_root.resolve() if tag_root is not None and (tag_root.resolve() == root or tag_root.resolve() in root.parents) else root
    skip_roots = tuple(p.resolve() for p in exclude)
    seen: set[str] = set()
    cache: dict = {}
    unreadable: list[str] = []  # folder tag files that could not be honoured
    own: dict[int, str] = {}
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
        doc, state = store_safely(session, counts, source, rel, parsed, today, rel=rel, inherited=folder_declared_tag(p.parent, top, cache, unreadable), own_log=own)
        if doc is None:
            continue
        pairs.append((doc, parsed.meta or {}))
        counts[state] += 1
    if complete:
        counts["removed"] = remove_missing(session, source, seen)
    counts["superseded_by_reference"] = resolve_replacements(session, pairs)
    if unreadable:
        counts["unreadable_folder_tags"] = sorted(set(unreadable))
    note_reads(session, source, own)
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
    own: dict[int, str] = {}
    for d in docs:
        slug = re.sub(r"[^a-z0-9]+", "-", d.title.lower()).strip("-") or d.external_id
        parsed = parse_text(d.title + ".md", d.text, slug)
        parsed.title = normalise_text(d.title) or parsed.title
        parsed.updated_on = parsed.updated_on or _date(d.updated_on)
        doc, state = store_safely(session, counts, source, d.external_id, parsed, today, rel=d.title, own_log=own)
        if doc is not None:
            counts[state] += 1
    if complete:
        counts["removed"] = remove_missing(session, source, seen)
    else:
        counts["incomplete"] = 1  # the read did not see everything, so a file it did not return is not known to be gone: nothing is removed
    if source.uri:
        mine = [x for x in session.scalars(select(Document).where(Document.external_id.in_(seen), Document.source_id != source.id)) if x.source.kind == source.kind]
        counts["removed"] += remove_documents(session, mine)
    note_reads(session, source, own)
    search.rebuild(session)
    return counts


def ingest_slack(session: Session, source: Source, days, channel_tags: dict[str, str] | None = None, today: date | None = None, inherited: str = "") -> dict:
    """Store the days of a Slack export. `inherited` is the tag the folders above the export declare: a channel tag or the source's tag can only narrow it."""
    counts = {"new": 0, "changed": 0, "same": 0, "removed": 0}
    seen: set[str] = set()
    own: dict[int, str] = {}
    complete = getattr(days, "complete", True)  # a day file that could not be read is not a day that is gone
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
        doc, st = store_safely(session, counts, source, slug, parsed, today, tag_hint=(channel_tags or {}).get(d.channel, ""), rel="slack", inherited=inherited, own_log=own)
        if doc is None:
            continue
        doc.doc_type = "slack"
        counts[st] += 1
    if complete:
        counts["removed"] = remove_missing(session, source, seen)
    else:
        counts["incomplete"] = 1  # the export could not be read in full, so a day that is missing from it is not known to be gone: nothing is removed
    note_reads(session, source, own)
    search.rebuild(session)
    return counts


def transcript_text(lines: list[tuple[str, str]]) -> str:
    return "\n".join(f"{who}: {words}" for who, words in lines)


def ingest_meeting(session: Session, source: Source, m: RemoteMeeting, today: date | None = None, tag_hint: str = "") -> tuple[Meeting, str]:
    """Store one meeting, its transcript text, and an indexed document so questions can cite it. Lines that look like instructions are listed and never acted on."""
    held = _date(m.held_on) or (today or date.today())
    text = normalise_text(transcript_text(m.lines))
    unlabelled = untagged.get(session, source.id)
    tag, own = resolve_tag(source, tag_hint, "", unlabelled), own_tag(tag_hint, "", unlabelled)
    mt = session.scalar(select(Meeting).where(Meeting.source_id == source.id, Meeting.external_id == m.external_id))
    state = "new" if mt is None else "changed"
    was = None if mt is None else mt.tag
    if mt is None:
        mt = Meeting(source_id=source.id, external_id=m.external_id, title=m.title[:300], held_on=held, provider=m.provider)
        session.add(mt)
        mt.transcript = Transcript(text=text)
    elif mt.transcript and mt.transcript.text == text and mt.tag == tag:
        note_meeting_reads(session, source, mt, own)
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
    note_meeting_reads(session, source, mt, own)
    return mt, state


def note_meeting_reads(session: Session, source: Source, mt: Meeting, own: str) -> None:
    """For a restricted source: the tag this meeting, its transcript document and the tasks and decisions found in it would have in an open source."""
    if source.default_tag == "company":
        return
    source_tags.note_own(session, source.id, "m", {mt.id: own})
    if mt.document_id:
        source_tags.note_own(session, source.id, "d", {mt.document_id: own})
    for kind, model in (("t", Task), ("x", Decision)):
        source_tags.note_own(session, source.id, kind, {i: own for i in session.scalars(select(model.id).where(model.meeting_id == mt.id))})


def retag_meeting_rows(session: Session, meeting: Meeting, was: str, now: str) -> None:
    """The tasks and decisions found in a meeting always carry the meeting's tag. When the tag changes they follow it. When it narrows (some audience can no longer see the meeting),
    text built earlier that may quote it (weekly reviews, process evidence, stored answers) is cleared, so the next job builds it again without the meeting."""
    session.execute(update(Task).where(Task.meeting_id == meeting.id).values(tag=now))
    session.execute(update(Decision).where(Decision.meeting_id == meeting.id).values(tag=now))
    if not audiences_of(was) <= audiences_of(now):
        source_tags.scrub_derived(session, now)
    search.clear_cache()


def held_note(count: int, cap: int) -> str:
    return (f"{count} meetings are no longer in the recorder or the transcript folder, but removing more than {cap} at once needs the owner. "
            "If that is right, the owner presses Confirm removal on this page. If not, check the recorder key and the folder first.")


def incomplete_note(counts: dict) -> str:
    """What the Sources page says to everyone after a read that stopped early (a limit, or a file that could not be read) or held something back. It names no folder and no file: a path can
    be a restricted folder's name, so the paths are in `incomplete_detail`, for the people who may see the narrowest tag. Empty after a complete read."""
    notes = []
    if counts.get("incomplete") or counts.get("truncated"):
        notes.append("The last read stopped before it saw everything, so nothing was removed from the index. Read it again, and see the limits in docs/13.")
    n = len(counts.get("unreadable_folder_tags") or [])
    if n:
        notes.append(f"{n} folder tag file{'s' if n != 1 else ''} could not be read or holds a tag nobody recognises, so the folders {'they belong' if n != 1 else 'it belongs'} to {'are' if n != 1 else 'is'} owner only until "
                     "that is fixed. The owner can see which on this page.")
    if counts.get("unknown_tags"):
        k = counts["unknown_tags"]
        notes.append(f"{k} document{'s' if k != 1 else ''} wrote a visibility tag nobody recognises and {'are' if k != 1 else 'is'} owner only until it is fixed.")
    if counts.get("removal_held"):
        notes.append(held_note(counts["removal_held"], counts.get("removal_cap", 5)))
    return " ".join(notes)


def incomplete_detail(counts: dict) -> str:
    """The paths behind `incomplete_note`, for the people who may see the narrowest tag only."""
    paths = counts.get("unreadable_folder_tags") or []
    if not paths:
        return ""
    return "Folder tag files that could not be read, or hold a tag nobody recognises (each must be a plain file of at most 64 KB, not a link, with one of the five tags): " + ", ".join(paths[:10]) + "."


def record_read(session: Session, src: Source, counts: dict) -> None:
    """Write what a read says about itself onto its source: the note everyone may see, and the detail only the owner may see."""
    from lorefern.context import set_state

    src.error = incomplete_note(counts)
    set_state(session, f"source_detail:{src.id}", incomplete_detail(counts))


def _reset_removal_waits(session: Session, src: Source) -> None:
    """A read that did not see everything ends any streak of empty reads and any held drop: what was true on the last complete read is not known to be true now."""
    from lorefern.context import set_state

    set_state(session, f"meetings_empty_read:{src.id}", "[]")
    set_state(session, f"meetings_removals_held:{src.id}", "0")


def _decide_removals(session: Session, ctx, src: Source, gone: list[Meeting], empty: bool, confirm: bool, counts: dict) -> list[Meeting]:
    """Which of the meetings a finished read no longer returns may be removed now. Three safeguards, because a wrong answer here deletes transcripts, decisions and the answers built on them:
    an empty reply while meetings exist is believed only when the next read says the same (a wrong key or a failing recorder can look like an empty account), a drop of more than
    MEETINGS_MAX_REMOVALS meetings in one read waits for the owner (`confirm`), and the owner's confirmation removes whatever is gone."""
    from lorefern.context import get_state, set_state

    wait_key, held_key = f"meetings_empty_read:{src.id}", f"meetings_removals_held:{src.id}"
    ids = sorted(m.external_id for m in gone)
    waiting = set(json.loads(get_state(session, wait_key, "[]") or "[]"))
    set_state(session, wait_key, json.dumps(ids if empty and gone else []))
    set_state(session, held_key, "0")
    if not gone:
        return []
    if confirm:
        return gone
    cap = ctx.settings.meetings_max_removals
    if len(gone) > cap:
        counts["removal_held"], counts["removal_cap"] = len(gone), cap
        set_state(session, held_key, str(len(gone)))
        return []
    if empty and not set(ids) <= waiting:
        counts["removal_pending"] = len(gone)  # the first empty read: the next one decides
        return []
    return gone


def sync_meetings(session: Session, ctx, today: date | None = None, confirm_removals: bool = False) -> dict:
    """Read the selected meetings adapter (a recorder or a folder of transcripts) into the database. Extraction happens later, and only proposes. A meeting is removed only after a
    read that saw everything, and only as `_decide_removals` allows. `confirm_removals` is the owner saying that a large drop is real."""
    counts = {"new": 0, "changed": 0, "same": 0, "removed": 0}
    found = ctx.adapters.meetings.list_meetings()
    complete = bool(getattr(found, "complete", False))  # only a read that says it saw everything can say a meeting is gone
    src = session.scalar(select(Source).where(Source.kind == "meetings"))
    if not found and not (complete and src is not None):
        if isinstance(found, RemoteMeetings) and not complete and src is not None:  # the folder or recorder could not be read in full: say so on the source
            counts["incomplete"] = 1
            _reset_removal_waits(session, src)
            record_read(session, src, counts)
        return counts  # nothing came back, and nothing is known to be gone
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
    if complete:
        seen = {m.external_id for m in found}
        gone = [x for x in session.scalars(select(Meeting).where(Meeting.source_id == src.id)) if x.external_id not in seen and not x.external_id.startswith(IMPORT_PREFIX)]
        counts["removed"] = remove_meetings(session, _decide_removals(session, ctx, src, gone, not found, confirm_removals, counts))
    else:
        counts["incomplete"] = 1  # the read did not see every meeting, so one it did not return is not known to be gone: nothing is removed
        _reset_removal_waits(session, src)
    src.last_synced_at, src.status = ctx.now(session), "ready"
    record_read(session, src, counts)
    search.rebuild(session)
    return counts
