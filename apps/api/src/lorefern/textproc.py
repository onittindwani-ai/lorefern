"""Small text tools shared by the index, the triage and the groundedness check. Plain rules, no model."""

from __future__ import annotations

import re

STOP = set("""a an the and or but if then so of to in on at by for with from as is are was were be been am do does did have has had i me my we our us you your he she it its they them their this that these those
can could would should will shall may might must how what when where which who whom whose why there here also just very really about into over under up down out off than too not no nor only own same such
furious useless terrible unacceptable awful ridiculous worst nobody useless see name happen now ask asked time times away right whole everyone three nobody help hardly today morning yesterday week again still already thing stuff way kind bit lot sure issue thanks hope trying tried try going go goes went said say says look looking seems seem anything something nothing everything
please hi hello hey thanks thank regards dear want need like get got let know tell make made use used using one two any some each every more most other another much many few""".split())
NEGATIONS = {"not", "no", "never", "cannot", "cant", "dont", "doesnt", "isnt", "arent", "wont", "none", "nor"}
_WORD = re.compile(r"[A-Za-z][A-Za-z']*|\d+(?:[.,]\d+)?")
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"'(])")


IRREGULAR = {"bought": "buy", "gave": "give", "given": "give", "took": "take", "taken": "take", "left": "leave", "lost": "lose", "broke": "break", "broken": "break", "ran": "run",
             "wrote": "write", "written": "write", "chose": "choose", "chosen": "choose", "kept": "keep", "built": "build", "sold": "sell", "spent": "spend", "made": "make", "found": "find", "thought": "think", "told": "tell",
             "began": "begin", "begun": "begin", "saw": "see", "seen": "see", "went": "go", "gone": "go", "did": "do", "done": "do", "children": "child", "people": "person", "men": "man", "women": "woman",
             "knives": "knife", "lives": "life", "wives": "wife", "shelves": "shelf", "met": "meet", "held": "hold", "leaving": "leave", "buying": "buy", "owed": "owe", "earned": "earn"}
# British spellings read as American ones, on both sides of every match, so a question and a document spelled differently still meet.
UK_US = {"centre": "center", "licence": "license", "cheque": "check", "grey": "gray", "catalogue": "catalog", "programme": "program", "judgement": "judgment", "colour": "color", "favour": "favor", "behaviour": "behavior",
         "labour": "labor", "neighbour": "neighbor", "honour": "honor", "organisation": "organization", "analyse": "analyze", "defence": "defense", "offence": "offense", "metre": "meter", "litre": "liter", "fibre": "fiber",
         "theatre": "theater", "ageing": "aging", "whilst": "while", "autumn": "fall", "mum": "mom", "tyre": "tire", "kerb": "curb", "plough": "plow", "mould": "mold", "cancelled": "canceled", "travelled": "traveled", "labelled": "labeled"}


def stem(w: str) -> str:
    w = w.lower().replace("'", "")
    w = IRREGULAR.get(w, UK_US.get(w, w))
    if w.endswith(("isation", "isations")):
        w = w.replace("isation", "ization")
    elif len(w) > 5 and w.endswith(("ised", "ises", "ising")) and not w.endswith(("raised", "praised", "advised", "revised", "promised", "exercised", "surprised", "comprised", "supervised", "devised", "raises", "advises", "revises", "promises", "exercises", "supervises", "devises", "raising", "advising", "revising", "supervising", "promising", "exercising", "surprising", "praising")):
        w = w[:-3] + "z" + w[-2:] if w.endswith(("ised", "ises")) else w[:-4] + "izing"
    if w.isdigit() or len(w) <= 3:
        return w
    for suf, rep in (("ies", "y"), ("sses", "ss"), ("ches", "ch"), ("shes", "sh"), ("xes", "x"), ("ing", ""), ("ers", "er"), ("ed", ""), ("ly", ""), ("s", "")):
        if w.endswith(suf) and len(w) - len(suf) >= 3 and not (suf == "s" and w.endswith("ss")):
            w = w[: len(w) - len(suf)] + rep
            break
    if len(w) > 4 and w[-1] == w[-2] and w[-1] not in "ls":
        w = w[:-1]
    return w[:-1] if w.endswith("e") and len(w) > 4 else w


NUMBER_WORDS = {"zero": 0, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14, "fifteen": 15, "sixteen": 16,
                "seventeen": 17, "eighteen": 18, "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90, "hundred": 100, "thousand": 1000}
_TENS = "twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety"
_UNITS = "one|two|three|four|five|six|seven|eight|nine"
_TENS_UNITS = re.compile(rf"\b({_TENS})[\s-]+({_UNITS})\b", re.I)
_NUMWORD = re.compile(r"\b(" + "|".join(NUMBER_WORDS) + r")\b", re.I)
_ONE_UNIT = re.compile(r"\b(?:one|a|an)(?=[\s-]+(?:business |calendar |working )?(?:second|minute|hour|day|week|month|year|percent)s?\b)", re.I)
MONTH_NUM = {m: i + 1 for i, m in enumerate("january february march april may june july august september october november december".split())}
_MON = "|".join(list(MONTH_NUM) + ["jan", "feb", "mar", "apr", "jun", "jul", "aug", "sep", "sept", "oct", "nov", "dec"])
_MON_FIRST = re.compile(rf"\b({_MON})\.?\s+(\d{{1,2}})(?:st|nd|rd|th)?\b", re.I)
_DAY_FIRST = re.compile(rf"\b(\d{{1,2}})(?:st|nd|rd|th)?\s+(?:of\s+)?({_MON})\b", re.I)
MONTH_ABBR_OF = {i + 1: m for i, m in enumerate(MONTH_NUM)}
_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")


ABBR = {i + 1: m[:3] for i, m in enumerate(MONTH_NUM)}


def _month(name: str) -> str:
    n = name.lower()
    num = MONTH_NUM.get(n) or next(v for k, v in MONTH_NUM.items() if k.startswith(n[:3]))
    return "xm" + ABBR[num]  # letters only, so the word reader keeps it as one token


def digitize(text: str) -> str:
    """Read number words and dates one way: 'twenty five' and 'two weeks' become 25 and 2 weeks, 'a day' becomes 1 day, and 'March 3', '3 March' and '2026-03-03' all become 'xmmar 3' (a month token and the day).
    Used on both the question side and the document side, so the same fact written two ways still matches."""
    text = _ISO.sub(lambda m: f"{m.group(1)} {_month(MONTH_ABBR_OF[int(m.group(2))])} {int(m.group(3))}", text)
    text = _MON_FIRST.sub(lambda m: f"{_month(m.group(1))} {int(m.group(2))}", text)
    text = _DAY_FIRST.sub(lambda m: f"{int(m.group(1))} {_month(m.group(2))}", text)
    text = _TENS_UNITS.sub(lambda m: str(NUMBER_WORDS[m.group(1).lower()] + NUMBER_WORDS.get(m.group(2).lower(), {"one": 1}.get(m.group(2).lower(), 0))), text)
    text = _NUMWORD.sub(lambda m: str(NUMBER_WORDS[m.group(1).lower()]), text)
    return _ONE_UNIT.sub("1", text)


def words(text: str) -> list[str]:
    return _WORD.findall(digitize(text))


def stems(text: str, keep_stop: bool = False) -> list[str]:
    out = []
    for w in words(text):
        lw = w.lower().replace("'", "")
        if not keep_stop and (lw in STOP or lw in NEGATIONS):
            continue
        out.append(stem(w))
    return out


def has_negation(text: str) -> bool:
    return any(w.lower().replace("'", "") in NEGATIONS or w.lower().endswith("n't") for w in words(text))


def split_sentences(text: str) -> list[str]:
    parts = []
    for para in re.split(r"\n\s*\n|\n(?=#)", text):
        para = " ".join(para.split())
        if para:
            parts += [s.strip() for s in _SENT.split(para) if s.strip()]
    return parts


def numbers(text: str) -> set[str]:
    return {n.replace(",", "") for n in re.findall(r"\d+(?:[.,]\d+)?", digitize(text))}
