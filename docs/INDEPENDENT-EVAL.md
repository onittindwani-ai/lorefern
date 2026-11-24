# Independent evaluation (two sets written by people who never saw the code)

This page reports how Lorefern's offline rules did on two test sets written by separate authors who read only the product spec, the start guide and the capabilities page. Neither author opened any code, test, data folder or other document of this repository. Everything in the sets is fictional (set A: a small heating and plumbing company, set B: a 41 person data consultancy).

**These numbers are for the offline rules stand in, which is plain rules and not a language model.** They say nothing about a live model (see the model path section of doc 14, which is UNVERIFIED live).

## The one thing to read first

| | Set A first run | Set A after the general fixes | Set B first run |
| --- | --- | --- | --- |
| Questions answered right | 42 of 79 (53.2 percent) | 45 of 79 (57.0 percent) | 65 of 87 (74.7 percent) |
| Restricted questions where a person must not see the answer | 7 of 10 refused cleanly, 0 real leaks | 7 of 10, 0 real leaks | 9 of 13, 0 real leaks |
| Meeting action items found (recall) | 16 of 25 (0.64) | 19 of 25 (0.76) | 15 of 21 (0.71) |
| Action item precision, strict | 0.62 (16 of 26) | 0.68 (19 of 28) | 0.54 (15 of 28) |
| Action item precision, vague items tolerated | 0.85 | 0.89 | 0.79 |
| Decisions found | 6 of 10 | 6 of 10 | 8 of 10 |

For comparison, the scores the system's own authors wrote and tuned themselves: answers 22 of 56 on the first run, 32 of 56 after tuning on the failures; action items precision 0.80 and recall 0.60, decisions 0 of 3. The independent first runs are the honest ones. Set A after the fixes is **no longer held out**, because the fixes were made after its first run (they were general, see below, but the first run came before them).

## How the sets were read as Lorefern's words (fixed before any run)

The authors invented tags (public, staff, managers, leadership, owner) and askers (guest, staff, leadership, owner). Lorefern has its own tags and audiences. The mapping, applied to a temporary copy of each set (the files in `data/eval/independent/` are untouched):

| Authors' word | Lorefern word |
| --- | --- |
| tag public | company |
| tag staff | clients (staff, leadership and owner see it, finance does not) |
| tag managers (unused by both sets) | leadership |
| tag leadership | leadership |
| tag owner | people (only the owner sees it) |
| asker guest | finance audience (sees company and finance tags only, and no document of either set is tagged finance, so it sees exactly the public ones) |
| asker staff, leadership, owner | staff, leadership, owner |

The company folder goes through Lorefern's own folder ingestion, the transcripts through its own meeting path (header and attendee lines are the header; the speakers are first names, the owners table is built from the attendee names), questions through `qa.ask`. The complete scoring rules are in the docstring of `tools/eval_independent.py`: a `must_contain` group is a case insensitive substring test with `|` alternatives, a refusal is the outcome `not_found` or `refuse` with nothing cited, an action item matches a key item when at least 34 percent (and 2) of the key text's word stems are in the proposal, and so on. Run it yourself: `python tools/eval_independent.py --set a` (the first run files are never overwritten).

## Answers in detail

| Kind | Set A first | Set A after | Set B first |
| --- | --- | --- | --- |
| Single document | 25 of 42 | 25 of 42 | 39 of 45 |
| Two or more documents | 3 of 11 | 3 of 11 | 7 of 13 |
| Superseded (the current value must win) | 0 of 6 | 3 of 6 | 5 of 8 |
| Not written anywhere (must say not found) | 7 of 10 | 7 of 10 | 5 of 8 |
| Restricted for this asker | 7 of 10 | 7 of 10 | 9 of 13 |

- **Right document first, among the questions that have a document.** Search ranked an expected document first for 45 of 59 (set A) and 59 of 66 (set B), and within the first three for 51 of 59 and 66 of 66. An expected document was cited in the answer for 40 of 59 and 58 of 66.
- **Facts.** Of the answers given, all required facts were present in 28 of 45 (A first), 31 of 46 (A after) and 51 of 60 (B). A stale value was quoted as the answer in 2 (A first), 1 (A after) and 0 (B) questions.
- **Superseded.** Before the fix Lorefern read only a `status` word in a conflict. It now also reads a replaced by field, a banner in the first lines ("this document has been replaced"), and a newer document that says it replaces an older one, and leaves the replaced document out of an answer when a current one covers the question. The old value was never quoted as the answer in any run.
- **Not written anywhere.** Lorefern answered anyway for 3 of 10 (A) and 3 of 8 (B). This is the offline matcher finding a nearby document, and the biggest honest weakness in this table next to reworded single document questions.

## The restricted question numbers (a person must not see it)

This is the most important failure to avoid, so it is reported alone.

| | Set A first | Set A after | Set B first |
| --- | --- | --- | --- |
| Restricted questions | 10 | 10 | 13 |
| Refused cleanly (not found, nothing cited, none of the key's strings anywhere in the response) | 7 | 7 | 9 |
| Answered from some other visible document, hidden document not cited, no key string | 3 | 2 | 3 |
| Flagged by the tool as a leak | 1 | 1 | 1 |
| Real leaks, after reading each flagged case | 0 | 0 | 0 |

The tool counts a leak when any `must_not_contain` string appears anywhere in the response (answer, sentences, citations, reason) or the hidden document is cited. Each flagged case was read by hand after the runs:

- A078 (asker guest): the answer cited a public pricing document, which the guest may read, and that document contains the word "owner", one of the key's alternatives. The hidden approval document was not cited. Not a leak.
- B077 (asker leadership): the response was a refusal that cited nothing; the key string "26" is the coverage percentage in the refusal's own reason text ("covers only 26 percent of the question"). Not a leak.

The mechanism is the same as before: every query filters by the asker's tags, so a hidden chunk is never fetched, ranked, cited or counted. These two sets did not find a way around it. They also did not try to: the sets contain restricted questions, not attacks on the filter, and the filter is a per source tag, not a mirror of Drive or Slack permissions (see doc 13).

## Meetings in detail

| | Set A first | Set A after | Set B first |
| --- | --- | --- | --- |
| Key action items | 25 | 25 | 21 |
| Proposed | 26 | 28 | 28 |
| Matched | 16 | 19 | 15 |
| Owner right of matched | 16 of 16 | 19 of 19 | 15 of 15 |
| Due date right of matched | 15 of 16 | 18 of 19 | 14 of 15 |
| Extra proposals that are listed vague commitments with no owner or no date (tolerated) | 6 | 6 | 7 |
| Extra proposals that invented both an owner and a date for a vague item | 0 | 0 | 0 |
| Extra proposals that overlap a listed false positive quote | 0 | 0 | 3 |
| Other extra proposals | 4 | 3 | 3 |
| Listed false positives that became a task or decision (false positive rate) | 2 of 23 (0.09) | 2 of 23 (0.09) | 3 of 28 (0.11) |
| Decisions found | 6 of 10 | 6 of 10 | 8 of 10 |
| Planted instruction lines flagged, and acted on | 1 of 1, 0 | 1 of 1, 0 | 1 of 1, 0 |
| Quotes that are exactly the transcript's characters | 32 of 32 | 34 of 34 | 36 of 36 |

Owners are resolved against a table built from the attendee lists, because the authors' speakers are first names. A real set up lists the staff. Every owner that Lorefern found was right; the weakness is recall (it misses commitments said in unusual ways) and a few extra proposals, which a person rejects on the approval screen.

## What changed between the first run of set A and the first run of set B (all general)

Made using only general language knowledge and Lorefern's own seed documents and own earlier test sets (all checked again after each change: the self written held out set stayed at 32 of 56, the development set at 33 of 38). No item of set A was read before the changes, with the exceptions listed under "What was looked at".

- Number words and dates read one way ("twenty five" is 25, "a day" is 1 day, "March 3", "3 March" and "2026-03-03" are one date), British and American spellings meet, a short list of irregular verbs.
- Documents marked as replaced, a replaced by field, an opening banner, and a `supersedes` or `replaces` field in a newer document; a replaced document is left out when a current one covers the question, unless the question asks about the past; a question about the past uses it and says so.
- A few dozen everyday synonym pairs (vehicle and truck, approve and sign, supplier and vendor and so on).
- Meetings: filler words and openers are read through ("okay, um, so, I'll ..."), a leading condition makes a commitment conditional, hypotheticals and things already done are not commitments, an offer ("if that helps") is not a commitment, "Name, do this" is an assignment, a correction ("Wednesday, no wait, Friday", also in the next sentence) keeps the last date, ordinal words for days ("the thirty first"), and more ways to say "we decided".

## What was looked at, and what that means

Honest list, in order:

1. Before writing the tool: the authors' README. To write the loader I also looked at the key names and types of the JSON files of both sets (not their values), the folder names of set A, the front matter lines of two set A documents, and the first lines (title, date, attendee line, first speaker lines clipped to 60 characters) of one meeting file in each set.
2. After the set A first run: the totals by kind. One item, A078, was read (its question, key and cited document) to decide whether a flagged leak was real.
3. The general fixes above were written after that. The field names `supersedes`, `replaces`, `superseded_by` and `replaced_by` and the status words come from the README's description of the document format, which is a contract, but it means the superseded fix is informed by set A's format. Part of the number word, irregular verb and filler handling is the same kind of general fix the sibling systems made; the lists were not made from set A items.
4. Set B was run once, after the fixes, and its first run saved untouched. Before that run set B was not read, apart from item 1 above. After the run only the flagged leak B077 was read (the key and the response).
5. Set A was run again after the fixes. It is no longer held out.

Set B scores higher than set A. Part of that is the style: set B's documents are formal, with document ids and tables, and its questions reuse the documents' own words more. It is not proof that the fixes helped by that much, and neither set is a sample of your documents.

## Weaknesses to know before you rely on it

- **Reworded questions that share few words with the document.** 8 single document questions in set A and 3 in set B came back as not found. A language model writer behind the same checks would help here (model path, doc 14), but that is UNVERIFIED.
- **Questions that need two documents** are the weakest kind (3 of 11 and 7 of 13).
- **Answering when it should say not found.** About a third of the not written anywhere questions got an answer from a nearby document. The sentence is supported by that document, so it is not invented, but it answers a different question.
- **Meetings.** Recall of 0.64 to 0.76 and strict precision of 0.54 to 0.68. Nothing is stored as approved, so extra and missed items cost a person's time, not a wrong task. The date words follow the conventions of `dates.py` (a weekday means the next one after the meeting; "next Friday" is the Friday of the following week).
- **Two documents that differ with no status and no replaces field** are not resolved by date: Lorefern says they disagree and asks the owners, by design.

## Same numbers after the model path and the stricter banner rule

After the first runs the model path was added and the replaced-banner rule was made stricter (it had marked a seed meeting as replaced because it contained the words "out of date"; it now looks only at the first three short lines of a document and never at meetings or Slack days). Both sets were run again with the final engine (`set_a_final_engine.json`, `set_b_final_engine.json`): every number in the tables above came out identical, which also shows that the offline default is unchanged by the model path. Both sets are no longer held out.

## Re running

```
python tools/eval_independent.py --set a      # or --set b, or a folder with company/, meetings/ and the keys
python tools/eval_independent.py --set a --check-load   # parse only
```

The first run files `set_a_first_run.json` and `set_b_first_run.json` in `data/eval/independent/` must never be overwritten; the tool refuses.
