"""Read a document into plain text and cut it into chunks that carry context.

Contextual retrieval, the simple way: every chunk keeps the document title and section, and gets a one line context sentence that is part of what the index reads
(but the chunk text itself, and the offsets used to highlight it, stay exactly the document's own words).
"""

from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from datetime import date

from lorefern.textproc import split_sentences, stems

MAX_WORDS = 110


@dataclass
class ParsedDoc:
    title: str
    text: str
    kind: str
    updated_on: date | None
    slug: str
    meta: dict = None  # type: ignore[assignment]  # front matter: visibility, type, owner, review_by, status


@dataclass
class ChunkSpec:
    ordinal: int
    section: str
    context: str
    text: str
    start: int
    end: int


def parse_front_matter(raw: str) -> tuple[dict, str]:
    raw = raw.lstrip("\ufeff")
    if raw.startswith("---\n"):
        end = raw.find("\n---\n", 4)
        if end > 0:
            meta = {}
            for line in raw[4:end].splitlines():
                if ":" in line:
                    k, v = line.split(":", 1)
                    meta[k.strip().lower()] = v.strip()
            return meta, raw[end + 5:].lstrip("\n")
    return {}, raw


def parse_text(name: str, raw: str, slug: str) -> ParsedDoc:
    meta, body = parse_front_matter(raw)
    title = meta.get("title") or next((m.group(1) for m in re.finditer(r"^#\s+(.+)$", body, re.M)), "") or slug.replace("-", " ").title()
    try:
        upd = date.fromisoformat(meta["updated"]) if meta.get("updated") else None
    except ValueError:
        upd = None
    return ParsedDoc(title.strip(), body.strip() + "\n", "md" if name.endswith(".md") else "txt", upd, slug, meta)


def parse_pdf(name: str, data: bytes, slug: str) -> ParsedDoc:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    pages = [(p.extract_text() or "").strip() for p in reader.pages]
    text = "\n\n".join(p for p in pages if p)
    first = text.splitlines()[0] if text else slug
    meta_title = (reader.metadata.title if reader.metadata and reader.metadata.title else "") or first
    m = re.search(r"effective (\d{1,2}) (\w+) (\d{4})", text)
    upd = None
    if m:
        months = {n: i for i, n in enumerate(["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"], 1)}
        if m.group(2) in months:
            upd = date(int(m.group(3)), months[m.group(2)], int(m.group(1)))
    return ParsedDoc(str(meta_title).strip(), text + "\n", "pdf", upd, slug, {})


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def chunk_document(doc_title: str, text: str) -> list[ChunkSpec]:
    """Split on markdown headings, then on sentence groups of at most MAX_WORDS words. Offsets point into `text`."""
    sections: list[tuple[str, int, int]] = []
    heads = [(m.start(), m.end(), m.group(2).strip()) for m in re.finditer(r"^(#{2,4})\s+(.+)$", text, re.M)]
    if not heads:
        sections.append(("", 0, len(text)))
    else:
        first = heads[0][0]
        if text[:first].strip():
            sections.append(("", 0, first))
        for i, (s, e, name) in enumerate(heads):
            sections.append((name, e, heads[i + 1][0] if i + 1 < len(heads) else len(text)))
    out: list[ChunkSpec] = []
    for name, a, b in sections:
        body = text[a:b]
        sents = split_sentences(body)
        group: list[str] = []
        count = 0
        groups: list[list[str]] = []
        for s in sents:
            n = len(s.split())
            if group and count + n > MAX_WORDS:
                groups.append(group); group, count = [], 0
            group.append(s); count += n
        if group:
            groups.append(group)
        cursor = a
        spans: dict[int, tuple[int, int]] = {}
        for g in groups:
            first = None
            last_end = cursor
            for sent in g:
                idx = text.find(sent, cursor)
                if idx < 0:
                    idx = text.find(sent[:20], cursor)
                idx = idx if idx >= 0 else cursor
                last_end = min(b, idx + len(sent))
                cursor = last_end
                first = idx if first is None else first
            spans[id(g)] = (first if first is not None else a, last_end)
        for g in groups:
            start, end = spans[id(g)]
            ctx = f"This passage is from the article '{doc_title}'" + (f", section '{name}'." if name else ".")
            out.append(ChunkSpec(len(out), name, ctx, text[start:end], start, end))
    return out


def stems_for_index(doc_title: str, c: ChunkSpec) -> str:
    return " ".join(stems(f"{doc_title} {c.section} {c.context} {c.text}"))
