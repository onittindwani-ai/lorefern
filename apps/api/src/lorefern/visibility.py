"""Who may see what. Each document, chunk, meeting, task and decision carries one visibility tag.

An audience (owner, leadership, finance, staff) allows a set of tags. Every read goes through `allowed_tags` and filters in the query itself, so a restricted row is
never fetched, ranked, cited or counted for a person who may not see it.

This is a per source tag, set by whoever connects the source. It is NOT a mirror of the permissions inside Google Drive, Notion or Slack, and the system is single
tenant. Read docs/13-SECURITY-AND-DATA.md before you rely on it.
"""

from __future__ import annotations

TAGS = ("company", "clients", "finance", "people", "leadership")

# Which audience sees which tag. Decided defaults for a small company (owner sees all, leadership everything but people material, finance company and finance, staff company and client material). The implementer changes the map per client.
AUDIENCE_TAGS: dict[str, tuple[str, ...]] = {
    "owner": TAGS,
    "leadership": ("company", "clients", "finance", "leadership"),
    "finance": ("company", "finance"),
    "staff": ("company", "clients"),
}
AUDIENCES = tuple(AUDIENCE_TAGS)
# Audiences that may approve tasks, decisions and other changes. Others read only.
WRITERS = {"owner", "leadership"}
RANK = {"owner": 4, "leadership": 3, "finance": 2, "staff": 1}


def allowed_tags(audience: str) -> tuple[str, ...]:
    """Unknown audiences get the narrowest set, never a wider one."""
    return AUDIENCE_TAGS.get(audience, AUDIENCE_TAGS["staff"])


def can_see(audience: str, tag: str) -> bool:
    return tag in allowed_tags(audience)


def audiences_of(tag: str) -> frozenset[str]:
    """The audiences that may see a tag. An unknown tag is seen by nobody."""
    return frozenset(a for a, tags in AUDIENCE_TAGS.items() if tag in tags)


def narrowest_tag(audience: str | None = None) -> str:
    """The tag the fewest audiences may see, read from the map above (so it follows a map the implementer has changed). With the default map this is `people`, which only the owner sees.
    It is the tag of anything whose tag is missing or not recognised: a document nobody labelled is never visible to more people than the owner.
    With an audience, the narrowest of the tags that audience may itself see (a person cannot create something they could not open afterwards)."""
    pool = allowed_tags(audience) if audience else TAGS
    return min(pool, key=lambda t: (len(audiences_of(t)), -TAGS.index(t)))


def widens(old: str, new: str) -> bool:
    """True when moving a row from tag `old` to tag `new` lets an audience see it that could not before."""
    return not audiences_of(new) <= audiences_of(old)


def meet_tag(a: str, b: str) -> str:
    """The tag that is no wider than either `a` or `b`: the one seen by exactly the audiences that see both, or the narrowest tag when there is none."""
    both = audiences_of(a) & audiences_of(b)
    return next((t for t in TAGS if audiences_of(t) == both), narrowest_tag())


INHERIT = "inherit"  # what a document writes when it has no opinion of its own: it takes the tag of its folder


def declared_tag(*written: str) -> str:
    """The narrowest of the tags people wrote down (a document's own line, its folders' lines), or "" when none of them wrote one. A blank value and `inherit` mean "no opinion".
    A tag nobody recognises counts as the narrowest tag, never as a wider one. A document, its folder and its source can only ever narrow one another."""
    out = ""
    for w in written:
        c = (w or "").strip().lower()
        if not c or c == INHERIT:
            continue
        c = c if c in TAGS else narrowest_tag()
        out = c if not out else meet_tag(out, c)
    return out


# The base session role for each audience. The read only audiences use the base `viewer` role, which the base refuses on every change.
SESSION_ROLE = {"owner": "owner", "leadership": "approver", "finance": "viewer", "staff": "viewer"}


def session_role(audience: str) -> str:
    """Unknown audiences get the read only role, never a wider one."""
    return SESSION_ROLE.get(audience, "viewer")


def can_write(audience: str) -> bool:
    return audience in WRITERS


def audience_of(settings, email: str) -> str:
    """Map a signed in email to an audience. Unknown emails are staff."""
    from sendora_core.auth import clean_email

    return settings.members().get(clean_email(email), "staff")
