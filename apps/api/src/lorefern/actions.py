"""Read a meeting transcript and propose action items and decisions. Plain rules, NOT a language model.

Every proposal carries a verbatim quote, the exact characters of the transcript, and `validate_quote` proves it by code: a proposal whose quote is not in the transcript
is dropped, never shown. Nothing here writes a task: the caller stores proposals as `proposed`, and a person approves each one.

A line that looks like an instruction to the system ("assign all tasks to Dana", "ignore the rules") is never read. It is listed on the meeting for a person to look at.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from lorefern.dates import parse_due
from lorefern.injection import is_injection
from lorefern.textproc import STOP, stems

_WS = re.compile(r"\s+")
HEDGE = re.compile(r"\b(maybe|perhaps|probably|i think|try to|might|possibly|if we can|if i can|hopefully)\b", re.I)
FIRST = re.compile(r"\b(?:i'll|i will|i can take|i can do|i am going to|i'm going to|i'll take|let me|i can handle|i'll handle|i got this one|i've got)\b\s*(?:take |handle |do |be |go |get )?(.*)", re.I)
NAME_CAN = re.compile(r"^(?:(?:ok(?:ay)?|so|and|then|right)[, ]+)?([A-Z][a-z]+(?: [A-Z][a-z]+)?)[,:]? (?:can you|could you|would you|will you|please|you'll|you will|you take|you own|you're on)\b\s*(.*)")
NAME_WILL = re.compile(r"\b([A-Z][a-z]+(?: [A-Z][a-z]+)?) (?:will|is going to|is to|to|needs to|should|has to|agreed to|is taking|takes)\b\s+(.*)")
ACTION_LABEL = re.compile(r"^(?:action(?: item)?|todo|to-do|next step|follow[- ]up)\s*[:\-]\s*(.*)", re.I)
VAGUE_NEED = re.compile(r"\b(?:someone|somebody|we|the team|we'll|we all)\b[^.?!]{0,30}?\b(?:needs? to|should|have to|must|ought to|will need to)\b\s*(.*)", re.I)
NOT_COMMIT = re.compile(r"\b(?:won't|will not|can't|cannot|couldn't|didn't|already (?:did|sent|done)|i sent|i did|we did|was going to|used to)\b", re.I)
DECISION = re.compile(r"\b(?:we(?:'re| are)? moving (?:forward )?with|we(?:'ll| will) (?:use|switch to|move to|stop|cancel)|we(?:'re| are) (?:using|switching to|cancelling|canceling|stopping)|settled on|it(?:'s| is) decided|that(?:'s| is) decided|the plan is(?: to)?|from now on|final answer:?|the call is|we(?:'ve| have)? decided(?: to| on| that)?|we(?:'ve| have)? agreed(?: to| on| that)?|the decision is(?: to)?|decision:|let's go with|we(?:'ll| will) go with|we(?:'re| are) going with|i(?:'ve| have)? decided(?: to| on)?|i(?:'m| am) approving|approved:|we(?:'re| are) (?:not|dropping|stopping|moving to|switching to)|final call:)\s*(.*)", re.I)
BECAUSE = re.compile(r"\b(because|since|so that|given that|the reason is|as we|due to)\b", re.I)
AGREE = re.compile(r"^(?:agreed|yes|yep|yeah|fine with (?:that|me)|sounds good|works for me|\+1|i agree|same|ok(?:ay)?)\b", re.I)


# Plain spoken English handling (general, not tied to any company): fillers and openers are read through, a leading "if ..." makes a commitment conditional,
# hypotheticals and things already done are not commitments, and "Name, do X" is an assignment.
LEAD = re.compile(r"^(?:(?:um+|uh+|er+|erm|ah+|hmm+|well|okay then|okay|ok|so|yeah|yep|yes|right|alright|all right|sure thing|sure|no problem|no worries|of course|absolutely|definitely|certainly|totally|happy to|gladly|got it|will do|sounds good|thanks|thank you|and|but|then|now|great|cool|fine|good|perfect|look|listen|actually|anyway|basically|honestly|like|you know|i mean|oh)\b[,.]?\s*)+", re.I)
FILL = re.compile(r"(?:,\s*)?\b(?:um+|uh+|er+|erm|hmm+)\b[,.]?\s*", re.I)
COND = re.compile(r"^(?:if|once|when|as soon as|assuming|provided that|after|unless)\b[^,]{3,100},\s*(.*)$", re.I)
HYPO = re.compile(r"\b(?:if (?:that|it) helps|if you (?:want|like|need|prefer)|if needed|what if|suppose|imagine|hypothetically|in theory|if i were|if we were|wouldn't it be|would be nice|i wish|we could always|just kidding|joking|just saying|in a perfect world|if only)\b", re.I)
PAST = re.compile(r"\b(?:yesterday|last (?:week|month|night|year|time)|earlier (?:today|this)|already|just (?:did|sent|finished|got)|(?:a|one|two) (?:week|month|day)s? ago|i (?:sent|did|called|booked|ordered|paid|finished|fixed|wrote|emailed|told)|we (?:sent|did|called|booked|ordered|paid|finished|fixed))\b", re.I)
FUTURE = re.compile(r"\b(?:will|'ll|going to|gonna|need to|needs to|has to|have to|should|by|before|tomorrow|next|let me)\b", re.I)
SELF = re.compile(r"^(?:i (?:think|guess|suppose|reckon) )?(?:i'll|i will|i can (?:take|do|handle|get|send|call|book|order|fix|check|write|draft|set|run|pick|arrange|have|own|sort|look|make|chase|update|ring)|i am going to|i'm going to|i'm gonna|i gotta|i need to|i have to|i'd better|i'll take|let me|put me down for|i've got|i got this one|i can)\b\s*(?:take |handle |do |be |go |get )?(.*)", re.I)
VERBS = "call|send|email|book|order|schedule|check|fix|write|draft|prepare|confirm|update|review|finish|submit|file|pay|ask|find|get|set|make|arrange|pull|post|share|follow|chase|ring|phone|text|remind|collect|pick|clean|test|upload|renew|cancel|contact|reach|sort|look|draw|print|create|add|remove|close|open"
NAME_IMP = re.compile(rf"^([A-Z][a-z]+(?: [A-Z][a-z]+)?)[,:]\s+(?:please\s+)?((?:{VERBS})\b.*)$")
CORRECTION_NEXT = re.compile(r"^(?:no,? wait|wait,? no|sorry|scratch that|make that|i mean|actually|no no|correction)\b", re.I)


def norm(s: str) -> str:
    return _WS.sub(" ", s).strip()


@dataclass
class Line:
    speaker: str
    text: str
    start: int  # offset of `text` inside the transcript
    index: int


def read_lines(transcript: str) -> list[Line]:
    out, pos = [], 0
    for i, raw in enumerate(transcript.split("\n")):
        m = re.match(r"^([^:\n]{1,60}):\s+", raw)
        if m:
            out.append(Line(m.group(1).strip(), raw[m.end():], pos + m.end(), len(out)))
        pos += len(raw) + 1
    return out


def sentences(line: Line) -> list[tuple[str, int]]:
    """(sentence, offset in transcript) with exact original characters."""
    out = []
    for m in re.finditer(r"[^.!?]+[.!?]*(?:\s+|$)", line.text):
        s = m.group(0).strip()
        if s:
            out.append((s, line.start + m.start() + (len(m.group(0)) - len(m.group(0).lstrip()))))
    return out


def validate_quote(transcript: str, quote: str, start: int) -> bool:
    """The quote is exactly the transcript's own characters at `start`."""
    return bool(quote) and start >= 0 and transcript[start:start + len(quote)] == quote


@dataclass
class ActionProposal:
    title: str
    owner_name: str  # as written, or the speaker
    owner_known: bool
    due_on: date | None
    due_raw: str
    confidence: float
    quote: str
    quote_start: int
    flags: list[str] = field(default_factory=list)


@dataclass
class DecisionProposal:
    title: str
    decided_by: str
    why: str
    quote: str
    quote_start: int
    agreed_by: list[str] = field(default_factory=list)


class OwnerBook:
    """Known people. A name matches by full name, first name or alias, and only when exactly one person fits."""

    def __init__(self, owners):
        self.by: dict[str, set[str]] = {}
        for o in owners:
            for key in {o.name.lower(), o.name.split()[0].lower(), *[a.lower() for a in (o.aliases or [])]}:
                self.by.setdefault(key, set()).add(o.name)

    def resolve(self, name: str) -> str | None:
        c = self.by.get(name.strip().lower(), set())
        if len(c) == 1:
            return next(iter(c))
        if not c and " " in name.strip():
            return self.resolve(name.strip().split()[0])
        return None


def _title(raw: str, due_raw: str = "") -> str:
    t = raw
    if due_raw:
        t = re.sub(rf"\b(?:by|before|on|until|for|this)?\s*(?:the )?{re.escape(due_raw)}\b", "", t, flags=re.I)
    t = re.split(r"\s+(?:because|since|so that)\s+", t, maxsplit=1, flags=re.I)[0]
    t = re.sub(r"\s+(?:by|before|on|until)\s*$", "", t.strip(" ,.;?!")).strip(" ,.;?!")
    t = re.sub(r"^(?:to |and |that |the |please )", "", t).strip()
    return (t[:1].upper() + t[1:])[:140] if t else ""


def _meaningful(title: str) -> bool:
    return len([s for s in stems(title) if s not in STOP]) >= 2


def extract_actions(transcript: str, held_on: date, owners, known_names: set[str] | None = None) -> tuple[list[ActionProposal], list[str]]:
    """Returns (proposals, flagged lines). `owners` are Owner rows (or anything with name and aliases)."""
    book = OwnerBook(owners)
    lines = read_lines(transcript)
    out: list[ActionProposal] = []
    flagged: list[str] = []
    for ln in lines:
        if is_injection(ln.text):
            flagged.append(f"{ln.speaker}: {ln.text}")
            continue
        sents = sentences(ln)
        for si, (sent, off) in enumerate(sents):
            cleaned = re.sub(r"\s+", " ", FILL.sub(" ", sent)).strip()
            core = LEAD.sub("", cleaned, count=1).strip() or cleaned
            conditional = False
            if (mc := COND.match(core)) and mc.group(1).strip():
                core, conditional = mc.group(1).strip(), True
            if core.rstrip().endswith("?") and not NAME_CAN.match(core):
                continue
            if HYPO.search(cleaned) or (PAST.search(cleaned) and not FUTURE.search(cleaned)):
                continue
            if NOT_COMMIT.search(cleaned) and not ACTION_LABEL.match(core):
                continue
            owner_name, rest, base, why = "", "", 0.0, ""
            if (m := ACTION_LABEL.match(core)):
                body = m.group(1)
                nm = NAME_WILL.search(body) or re.match(r"^([A-Z][a-z]+(?: [A-Z][a-z]+)?)\b\s*[,:\-]?\s*(.*)", body)
                if nm and book.resolve(nm.group(1)):
                    owner_name, rest, base, why = nm.group(1), nm.group(2), 0.75, "label"
                else:
                    rest, base, why = body, 0.55, "label_noowner"
            elif (m := NAME_CAN.match(core)) and (book.resolve(m.group(1)) or m.group(1) in (known_names or set())):
                owner_name, rest, base, why = m.group(1), m.group(2), 0.75, "assigned"
            elif (m := NAME_IMP.match(core)) and book.resolve(m.group(1)):
                owner_name, rest, base, why = m.group(1), m.group(2), 0.7, "assigned"
            elif (m := SELF.match(core)):
                owner_name, rest, base, why = ln.speaker, m.group(1), 0.7, "self"
            elif (m := NAME_WILL.search(core)) and book.resolve(m.group(1)) and core.startswith(m.group(1)):
                owner_name, rest, base, why = m.group(1), m.group(2), 0.7, "named"
            elif (m := VAGUE_NEED.search(core)):
                rest, base, why = m.group(1), 0.4, "vague"
            else:
                continue
            due, raw = parse_due(cleaned, held_on)
            title = _title(rest, raw)
            if not _meaningful(title):
                continue
            # a short next sentence like "By Friday." belongs to the commitment
            quote, qstart = sent, off
            if si + 1 < len(sents) and len(sents[si + 1][0].split()) <= 8 and (due is None or CORRECTION_NEXT.match(sents[si + 1][0])):
                d2, r2 = parse_due(sents[si + 1][0], held_on)
                if d2 is not None:
                    due, raw = d2, r2
                    nxt, noff = sents[si + 1]
                    quote, qstart = ln.text[off - ln.start: noff - ln.start + len(nxt)], off
            known = bool(owner_name) and book.resolve(owner_name) is not None
            conf = base + (0.1 if known else 0) + (0.15 if due else 0) - (0.1 if HEDGE.search(sent) else 0) - (0.1 if raw and not due else 0) - (0.05 if conditional else 0)
            flags = (["vague_owner"] if why in {"vague", "label_noowner"} else []) + (["unknown_owner"] if owner_name and not known else []) + (["hedged"] if HEDGE.search(sent) else []) + (["conditional"] if conditional else []) + (["no_date"] if not due else [])
            if validate_quote(transcript, quote, qstart):
                out.append(ActionProposal(title, owner_name if known else "", known, due, raw, round(max(0.05, min(0.98, conf)), 2), quote, qstart, flags))
    return _dedupe(out), flagged


def _dedupe(items: list[ActionProposal]) -> list[ActionProposal]:
    seen: set[tuple] = set()
    out = []
    for a in items:
        k = (tuple(sorted(stems(a.title))[:4]), a.owner_name)
        if k not in seen:
            seen.add(k)
            out.append(a)
    return out


def extract_decisions(transcript: str, owners) -> list[DecisionProposal]:
    lines = read_lines(transcript)
    out: list[DecisionProposal] = []
    for ln in lines:
        if is_injection(ln.text):
            continue
        sents = sentences(ln)
        for si, (sent, off) in enumerate(sents):
            m = DECISION.search(sent)
            if not m or sent.rstrip().endswith("?") or HEDGE.search(sent) or HYPO.search(sent) or re.match(r"^(?:and |so |ok(?:ay)?,? )?(?:if|unless|should we|what if|could we|do we)\b", sent, re.I):
                continue
            title = _title(m.group(1)) or _title(sent)
            if not _meaningful(title):
                continue
            why = ""
            window = [s for s, _ in sents[max(0, si - 1): si + 3]] + [x.text for x in lines[ln.index + 1: ln.index + 3] if not is_injection(x.text)]
            for cand in [sent] + window:
                if BECAUSE.search(cand) and norm(cand) in norm(transcript):
                    why = cand.strip()
                    break
            agreed = []
            for nx in lines[ln.index + 1: ln.index + 4]:
                if AGREE.match(nx.text.strip()) and nx.speaker != ln.speaker and not is_injection(nx.text):
                    agreed.append(nx.speaker)
            if validate_quote(transcript, sent, off):
                out.append(DecisionProposal(title, ln.speaker, why if why and why in transcript else "", sent, off, agreed))
    seen, uniq = set(), []
    for d in out:
        k = tuple(sorted(stems(d.title))[:4])
        if k not in seen:
            seen.add(k)
            uniq.append(d)
    return uniq
