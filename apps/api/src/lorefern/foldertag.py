"""The tag a folder declares for the documents inside it. Kept apart from the reader of the index so the folder checker can use it without the database libraries."""

from __future__ import annotations

from pathlib import Path

from lorefern.chunking import normalise_text, parse_front_matter
from lorefern.visibility import INHERIT, TAGS, declared_tag, narrowest_tag

MAX_DECLARATION_BYTES = 64 * 1024


def _declared_in(directory: Path, problems: list[str] | None, root: Path) -> str:
    """What the `.visibility` file or the README.md of this folder declares ("" when neither says anything). A file that is there but cannot be honoured (a link, larger than 64 KB, or
    unreadable) could hold a restriction, so the folder takes the narrowest tag and the file is named in `problems`: it must never turn into 'no tag', which would open the folder. A tag
    nobody recognises is named in `problems` too (it becomes the narrowest tag where the tags are combined)."""
    for name in (".visibility", "README.md"):
        f = directory / name
        try:
            if not (f.exists() or f.is_symlink()):
                continue
            if f.is_symlink() or not f.is_file() or f.stat().st_size > MAX_DECLARATION_BYTES:
                raise OSError(name)
            raw = normalise_text(f.read_text(errors="replace"))
        except OSError:
            if problems is not None:
                problems.append(f.relative_to(root).as_posix() if root in f.parents else name)
            return narrowest_tag()
        found = (raw.strip().splitlines() or [""])[0].strip().lower() if name == ".visibility" else (parse_front_matter(raw)[0].get("visibility") or "").strip().lower()
        if found:
            if problems is not None and found not in TAGS and found != INHERIT:  # a typo is the narrowest tag (declared_tag), and the owner is told which file to fix
                problems.append(f.relative_to(root).as_posix() if root in f.parents else name)
            return found
    return ""


def folder_declared_tag(directory: Path, root: Path, cache: dict, problems: list[str] | None = None) -> str:
    """The tag a folder declares for what is inside it: a `.visibility` file (one word) or the `visibility:` line of its README.md, combined with every folder above it up to the root
    of the tree (`root`: for a source that points at a sub folder, the knowledge folder, so a restriction above the source still counts). A nested folder can only narrow its parent, never widen it ("" when no folder says anything). A declaration that cannot be read counts as the narrowest tag
    and is added to `problems` (once per folder)."""
    if directory in cache:
        return cache[directory]
    found = _declared_in(directory, problems, root)
    parent = folder_declared_tag(directory.parent, root, cache, problems) if directory != root and root in directory.parents else ""
    cache[directory] = declared_tag(found, parent)
    return cache[directory]
