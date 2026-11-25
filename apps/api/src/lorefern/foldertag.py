"""The tag a folder declares for the documents inside it. Kept apart from the reader of the index so the folder checker can use it without the database libraries."""

from __future__ import annotations

from pathlib import Path

from lorefern.chunking import normalise_text, parse_front_matter
from lorefern.visibility import declared_tag


def folder_declared_tag(directory: Path, root: Path, cache: dict) -> str:
    """The tag a folder declares for what is inside it: a `.visibility` file (one word) or the `visibility:` line of its README.md, combined with every folder above it up to the root
    of the source. A nested folder can only narrow its parent, never widen it ("" when no folder says anything)."""
    if directory in cache:
        return cache[directory]
    found = ""
    for name in (".visibility", "README.md"):
        f = directory / name
        try:
            if f.is_file() and not f.is_symlink() and f.stat().st_size <= 64 * 1024:
                raw = normalise_text(f.read_text(errors="replace"))
                found = (raw.strip().splitlines() or [""])[0].strip().lower() if name == ".visibility" else (parse_front_matter(raw)[0].get("visibility") or "").strip().lower()
        except OSError:
            found = ""
        if found:
            break
    parent = folder_declared_tag(directory.parent, root, cache) if directory != root and root in directory.parents else ""
    cache[directory] = declared_tag(found, parent)
    return cache[directory]
