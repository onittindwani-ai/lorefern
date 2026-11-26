"""The company folder template: build it, customise it, index it, check it. Used by tools/new_company_folder.py, tools/check_company_folder.py and the Company folder page.

The template is built from scratch for small companies. It holds no content from any real company. Example documents inside it are labelled as examples.
"""

from __future__ import annotations

import re
import shutil
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

from lorefern.chunking import parse_front_matter

# (folder, what belongs, owner role, review cadence in days, visibility, what does not belong)
FOLDERS = [
    ("00 Governance", "How the company is run: operating rules, document standards, decision records, and who owns what.", "Founder", 90, "company", "Day to day work notes, client material, anything private about a person."),
    ("01 Company", "Who we are: profile, values, team directory, history, locations.", "Founder", 180, "company", "Pricing, salaries, or client specifics."),
    ("02 Strategy", "Goals, plans, board or leadership notes, market research.", "Founder", 90, "leadership", "Anything every staff member needs for daily work."),
    ("03 Clients and Customers", "One brief per client, service levels, onboarding, standard agreements.", "Account manager", 90, "clients", "Invoices, payment details, or private talk about a client."),
    ("04 Revenue", "Pricing, terms, the sales process, proposals and win or loss notes.", "Account manager", 90, "clients", "Salaries, costs, or payroll."),
    ("05 Operations", "How recurring work is done: SOPs, policies, checklists, meeting notes.", "Operations lead", 180, "company", "One off projects and client specific files."),
    ("06 Product and Engineering", "How the product or service is built and run: runbooks, release steps, the tech stack, backups.", "Lead engineer", 180, "company", "Credentials, keys or passwords. Never store secrets in a document."),
    ("07 Finance and Legal", "Budgets, spending rules, payroll summaries, contract notes, insurance.", "Finance lead", 90, "finance", "Anything staff need to see. Put policies everyone follows in 05 Operations."),
    ("08 People", "Leave, reviews, hiring, onboarding, salary bands.", "People lead", 180, "people", "Anything about one person that the whole company may read."),
    ("09 Marketing", "Content plans, brand voice, campaigns, newsletters, results.", "Marketing lead", 180, "company", "Client private data."),
    ("10 Tools and Systems", "What tools we use, who owns each one, access rules.", "Operations lead", 180, "company", "Passwords, tokens or API keys."),
    ("11 Templates", "Blank templates: SOP, decision record, meeting note, client brief.", "Operations lead", 365, "company", "Filled in documents. Copy a template, then save the copy in the right folder."),
]
CADENCE = {7: "weekly", 30: "monthly", 90: "quarterly", 180: "every 6 months", 365: "yearly"}
SKIP_DIRS = {".git", "node_modules"}
MAX_DOC_BYTES = 10 * 1024 * 1024  # the same limit the reader of the index uses
LINK = re.compile(r"\[[^\]]*\]\(([^)#]+?)(?:#[^)]*)?\)")


def _fm(meta: dict) -> str:
    return "---\n" + "\n".join(f"{k}: {v}" for k, v in meta.items()) + "\n---\n\n"


def readme_text(name: str, belongs: str, role: str, days: int, vis: str, not_belongs: str, company: str, today: date) -> str:
    meta = {"title": f"{name}: what belongs here", "owner": f"{role} ({{{{OWNER}}}})", "updated": today.isoformat(), "review_by": (today + timedelta(days=days)).isoformat(), "visibility": vis, "type": "readme", "status": "current"}
    return _fm(meta) + f"""# {name}

## What belongs here
{belongs}

## What does not belong here
{not_belongs}

## Who owns it
The {role.lower()} owns this folder at {company}. The owner keeps every document here current and answers questions about it.

## How often it is reviewed
This folder is reviewed {CADENCE.get(days, f'every {days} days')}. The review date of each document sits in its header. A document past its review date is flagged in the weekly operating review.

## Who may see it
Visibility tag: {vis}. Every document here takes this tag, or a narrower one when its own header says so (`visibility: inherit` means "take the folder's tag"). A document can never be seen by more people than the folder allows.
"""


TEMPLATES = {
    "sop-template.md": ("SOP template", "sop", """# SOP: <what this process does>

Owner: <name>. Last reviewed: <date>.

## When to use this
<the trigger, in one sentence>

## Steps
1. <first step>
2. <second step>
3. <third step>

## Done when
<how anyone can tell the work is finished>

## If something goes wrong
<who to tell and what to do>
"""),
    "decision-record-template.md": ("Decision record template", "decision", """# Decision: <what was decided>

Decided on <date> by <name>.

## Decision
<one or two sentences>

## Why
<the reason, in plain words, with the numbers that mattered>

## Source
<the meeting, message or document where it was decided>
"""),
    "meeting-note-template.md": ("Meeting note template", "meeting_note", """# Meeting: <title>

Date: <date>. Attendees: <names>.

## Decisions
- <decision and who made it>

## Action items
- <name> will <task> by <date>.

## Open questions
- <question and who will find out>
"""),
    "client-brief-template.md": ("Client brief template", "client_brief", """# Client brief: <client name>

Owner: <account manager>.

## Goal
<what the client wants in one paragraph>

## Contacts
<who to talk to and how they like to be contacted>

## Report schedule
<what the client receives and when>
"""),
}
EXAMPLES = {
    "00 Governance/decisions/EXAMPLE-decision-use-a-shared-inbox.md": ("decision", """# Decision: use one shared inbox for client email

Example only. Decided on 2026-01-12 by the founder.

## Decision
Client email goes to one shared inbox instead of personal inboxes.

## Why
Replies were slow when the person who owned a client was away.

## Source
Weekly operating review, 2026-01-12.
"""),
    "05 Operations/EXAMPLE-sop-send-the-monthly-invoice.md": ("sop", """# SOP: send the monthly invoice

Example only. Owner: the finance lead. Last reviewed 2026-01-05.

## Steps
1. On the first working day, export the billable items.
2. Create the invoice and check the total against the contract.
3. Send it and record the date in the invoice tracker.

## Done when
The invoice is sent and recorded.
"""),
    "03 Clients and Customers/EXAMPLE-client-brief-northlake-cafe.md": ("client_brief", """# Client brief: Northlake Cafe

Example only. Owner: the account manager.

## Goal
A website with the menu and opening hours, updated by the cafe owner without help.

## Contacts
The owner replies to email in the evening.

## Report schedule
A short monthly summary on the first Monday.
"""),
    "05 Operations/EXAMPLE-meeting-note-weekly-sync.md": ("meeting_note", """# Meeting: weekly sync

Example only. Date: 2026-01-12. Attendees: the whole team.

## Decisions
- We will use one shared inbox for client email.

## Action items
- The finance lead will set up the shared inbox by Friday.

## Open questions
- Who answers the inbox on public holidays?
"""),
}


@dataclass
class Finding:
    severity: str  # error, warning
    code: str
    path: str
    message: str


@dataclass
class FolderReport:
    documents: int = 0
    findings: list[Finding] = field(default_factory=list)
    tree: list[dict] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not any(f.severity == "error" for f in self.findings)


def build_template(target: Path, company: str = "{{COMPANY}}", today: date | None = None, owner: str = "{{OWNER}}") -> list[str]:
    """Write the empty skeleton, the three root documents, the four templates and the labelled examples. Returns the files written."""
    today = today or date.today()
    target.mkdir(parents=True, exist_ok=True)
    written: list[str] = []

    def w(rel: str, text: str) -> None:
        p = target / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text.replace("{{COMPANY}}", company).replace("{{OWNER}}", owner), encoding="utf-8")
        written.append(rel)

    for name, belongs, role, days, vis, nb in FOLDERS:
        w(f"{name}/README.md", readme_text(name, belongs, role, days, vis, nb, "{{COMPANY}}", today))
    for fname, (title, typ, body) in TEMPLATES.items():
        meta = {"title": title, "owner": "{{OWNER}}", "updated": today.isoformat(), "review_by": (today + timedelta(days=365)).isoformat(), "visibility": "inherit", "type": "template", "status": "current"}
        w(f"11 Templates/{fname}", _fm(meta) + body)
    for rel, (typ, body) in EXAMPLES.items():
        meta = {"owner": "Example owner", "updated": "2026-01-12", "review_by": (today + timedelta(days=365)).isoformat(), "visibility": "inherit", "type": typ, "status": "example"}
        w(rel, _fm(meta) + body)
    root_meta = {"owner": "{{OWNER}}", "updated": today.isoformat(), "review_by": (today + timedelta(days=90)).isoformat(), "visibility": "company", "status": "current"}
    w("SOURCE-REGISTER.md", _fm({**root_meta, "title": "Source register", "type": "register"}) + """# Source register

Every place knowledge comes from, how far to trust it, and who owns it. Add a row before you connect a new source.

Reliability grades: A is a direct record (a contract, a ledger, a system export). B is what the owner states. C is an inference or a guess.

| Source | Kind | Reliability | Owner | Reviewed | Visibility tag |
| --- | --- | --- | --- | --- | --- |
| This folder | folder | B | {{OWNER}} | every 90 days | company |
""")
    w("OWNERS-AND-REVIEW-CADENCE.md", _fm({**root_meta, "title": "Owners and review cadence", "type": "register"}) + "# Owners and review cadence\n\nEach numbered folder has one owner and one review rhythm. Change a row when the person changes.\n\n| Folder | Owner | Reviewed |\n| --- | --- | --- |\n" + "\n".join(f"| {n} | {r} ({{{{OWNER}}}}) | {CADENCE.get(d, f'every {d} days')} |" for n, _, r, d, _, _ in FOLDERS) + "\n")
    reindex(target, company, today)
    written.append("INDEX.md")
    return written


def _rebase_dates(text: str, today: date) -> str:
    """Move `updated` to today and keep the same gap to `review_by`, so a copy made next year is not born overdue. Examples keep their dates."""
    meta, _ = parse_front_matter(text)
    if meta.get("status") == "example" or not meta.get("updated") or not meta.get("review_by"):
        return text
    try:
        gap = date.fromisoformat(meta["review_by"]) - date.fromisoformat(meta["updated"])
    except ValueError:
        return text
    text = re.sub(r"^updated: .*$", f"updated: {today.isoformat()}", text, count=1, flags=re.M)
    return re.sub(r"^review_by: .*$", f"review_by: {(today + gap).isoformat()}", text, count=1, flags=re.M)


def instantiate(template: Path, target: Path, company: str, owner: str, today: date | None = None) -> list[str]:
    """Copy the template and fill in the company name, the owner and today's date. Refuses a folder that already has files."""
    today = today or date.today()
    if target.exists() and any(target.iterdir()):
        raise FileExistsError(f"{target} is not empty. Pick a new folder.")
    done: list[str] = []
    for p in sorted(template.rglob("*")):
        if p.is_file() and not any(part in SKIP_DIRS for part in p.parts):
            rel = p.relative_to(template)
            out = target / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            if p.suffix == ".md":
                out.write_text(_rebase_dates(p.read_text(encoding="utf-8").replace("{{COMPANY}}", company).replace("{{OWNER}}", owner), today), encoding="utf-8")
            else:
                shutil.copyfile(p, out)
            done.append(str(rel))
    reindex(target, company, today)
    return done


def _inside(root: Path, p: Path) -> bool:
    try:
        p.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def iter_docs(root: Path):
    """The documents of the folder, with the same guards as the reader of the index: nothing hidden, nothing that is a link out of the folder, nothing over the size limit."""
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in {".md", ".pdf", ".txt"} and not any(part in SKIP_DIRS or part.startswith(".") for part in p.relative_to(root).parts) and p.name != "INDEX.md":
            if _inside(root, p) and p.stat().st_size <= MAX_DOC_BYTES:
                yield p


def doc_meta(p: Path) -> dict:
    if p.suffix.lower() != ".md":
        return {}
    if p.stat().st_size > MAX_DOC_BYTES:
        return {}
    meta, _ = parse_front_matter(p.read_text(encoding="utf-8", errors="replace"))
    return meta


def reindex(root: Path, company: str, today: date) -> None:
    rows = []
    for p in iter_docs(root):
        rel = p.relative_to(root).as_posix()
        m = doc_meta(p)
        link = rel.replace(" ", "%20")
        rows.append(f"| [{m.get('title') or rel}]({link}) | {rel.split('/')[0] if '/' in rel else 'root'} | {m.get('owner', '')} | {m.get('updated', '')} | {m.get('review_by', '')} | {m.get('visibility', '')} |")
    text = _fm({"title": "Index", "owner": "Founder", "updated": today.isoformat(), "review_by": (today + timedelta(days=30)).isoformat(), "visibility": "company", "type": "index", "status": "current"}) + f"""# {company}: index of documents

Every document in this folder is listed once. Rebuild it with `python3 tools/check_company_folder.py <folder> --reindex`.

| Document | Folder | Owner | Updated | Review by | Visibility |
| --- | --- | --- | --- | --- | --- |
""" + "\n".join(rows) + "\n"
    (root / "INDEX.md").write_text(text, encoding="utf-8")


def check(root: Path, today: date | None = None) -> FolderReport:
    """Every numbered folder has a README and an owner, INDEX lists every document, links resolve, review dates are not overdue, tags are known, and no document claims to be wider than its folder."""
    from lorefern.foldertag import folder_declared_tag
    from lorefern.visibility import INHERIT, TAGS, meet_tag

    today = today or date.today()
    folder_cache: dict = {}
    rep = FolderReport()
    root = root.resolve()
    add = lambda sev, code, p, msg: rep.findings.append(Finding(sev, code, p, msg))  # noqa: E731
    folders = sorted(p for p in root.iterdir() if p.is_dir() and re.match(r"^\d\d ", p.name))
    if not folders:
        add("error", "no_folders", ".", "No numbered folders found. Run tools/new_company_folder.py first.")
    for f in folders:
        rd = f / "README.md"
        if not rd.exists():
            add("error", "readme_missing", f.name, "The folder has no README.md that says what belongs here.")
        else:
            m = doc_meta(rd)
            if not m.get("owner"):
                add("error", "folder_owner_missing", f"{f.name}/README.md", "The folder README has no owner.")
    index_path = root / "INDEX.md"
    index_text = index_path.read_text(encoding="utf-8") if index_path.exists() else ""
    if not index_path.exists():
        add("error", "index_missing", "INDEX.md", "There is no INDEX.md.")
    listed = {(root / l.replace("%20", " ")).resolve() for l in LINK.findall(index_text)} if index_text else set()
    for p in iter_docs(root):
        rep.documents += 1
        rel = p.relative_to(root).as_posix()
        if index_text and p.resolve() not in listed:
            add("error", "not_in_index", rel, "This document is not listed in INDEX.md.")
        if p.suffix.lower() != ".md":
            continue
        txt = p.read_text(encoding="utf-8", errors="replace")
        m, body = parse_front_matter(txt)
        if not m.get("owner"):
            add("error", "owner_missing", rel, "No owner in the header.")
        vis = (m.get("visibility") or "").strip().lower()
        if vis and vis != INHERIT and vis not in TAGS:
            add("error", "bad_tag", rel, f"Unknown visibility tag '{m['visibility']}'. Until it is fixed the document is visible to the owner only.")
        elif not vis:
            add("error", "visibility_missing", rel, "No visibility tag in the header. A document with none takes the tag of its folder, and with no folder tag it is visible to the owner only. Write `visibility: inherit` to take the folder's tag on purpose.")
        elif vis in TAGS:
            folder_tag = folder_declared_tag(p.parent, root, folder_cache)
            if folder_tag and meet_tag(vis, folder_tag) != vis:
                add("warning", "wider_than_folder", rel, f"The header says '{vis}', but its folder says '{folder_tag}'. The narrower tag '{meet_tag(vis, folder_tag)}' is used. Write `visibility: inherit`, or move the file to the folder that matches.")
        rb = m.get("review_by", "")
        if not rb:
            add("warning", "review_missing", rel, "No review date. A document without one counts as overdue.")
        else:
            try:
                if date.fromisoformat(rb) < today and m.get("status") != "example":
                    add("warning", "review_overdue", rel, f"Review date {rb} has passed.")
            except ValueError:
                add("error", "bad_date", rel, f"Review date '{rb}' is not a date (use YYYY-MM-DD).")
        for target in LINK.findall(body):
            if re.match(r"^(https?:|mailto:)", target):
                continue
            dest = (p.parent / target.replace("%20", " ")).resolve()
            if not _inside(root, dest) or not dest.exists():  # a link that leaves the folder is reported like a missing one, so the check cannot be used to find out which files exist elsewhere
                add("error", "broken_link", rel, f"The link to {target} does not resolve.")
    for f in folders:
        docs = [p for p in iter_docs(f)]
        rep.tree.append({"folder": f.name, "documents": [{"path": p.relative_to(root).as_posix(), **{k: doc_meta(p).get(k, "") for k in ("owner", "review_by", "visibility", "type")}} for p in docs]})
    return rep
