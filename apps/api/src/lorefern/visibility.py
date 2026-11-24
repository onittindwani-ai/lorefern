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


# The base session role for each audience. The read only audiences use the base `viewer` role, which the base refuses on every change.
SESSION_ROLE = {"owner": "owner", "leadership": "approver", "finance": "viewer", "staff": "viewer"}


def session_role(audience: str) -> str:
    """Unknown audiences get the read only role, never a wider one."""
    return SESSION_ROLE.get(audience, "viewer")


def can_write(audience: str) -> bool:
    return audience in WRITERS


def audience_of(settings, email: str) -> str:
    """Map a signed in email to an audience. Unknown emails are staff."""
    e = (email or "").strip().lower()
    return settings.members().get(e, "staff")
