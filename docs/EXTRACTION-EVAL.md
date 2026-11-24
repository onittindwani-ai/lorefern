# Meeting extraction results

What was measured, how, and what it does not prove.

## Method

- Eight **held out** transcripts in `data/eval/heldout_transcripts/` were written **before** the extractor was run on them, in different styles from the demo meetings and from the rules: an Otter style export, a Fireflies style export, quarterly minutes, a casual chat, a formal board meeting, a Fathom style export, a transcript with planted instructions, and a meeting with no action items.
- The answer key (`heldout_transcripts_key.json`) lists the action items, owners, due dates and decisions a careful reader finds.
- The first run is saved untouched in `data/eval/heldout_transcripts_first_run.json`. Run it again with `python3 tools/eval_extraction.py`.
- The extractor is **rules, not a language model**. A model might do better or worse.

## Results of the first run

| Measure | Result |
| --- | --- |
| Action items expected | <!--n:eval.extraction.expected_actions-->20<!--/n--> |
| Action items found | 15 |
| Precision (found items that were right) | 0.80 |
| Recall (expected items that were found) | 0.60 |
| Owner right, of the items found | 1.0 |
| Due date right | 0.83 |
| Decisions found | 0 of 3 |
| Quote is a real, exact span of the transcript | 100 percent (15 of 15 checked by code) |
| Lines that gave the system orders, flagged and ignored | 8 of 8 |
| A meeting with no action items produced none | yes |

## What this says

- The rules are **cautious**: what they propose is mostly right and the owner is always right, but they miss about 4 in 10 items, mostly commitments phrased as "I can check the registrar tonight" or "somebody should check". Reading is by a person anyway, so a miss costs a missed task, not a wrong one.
- Decisions are phrased in too many ways. 0 of 3 is the honest number for decisions in other styles. On the demo meetings, whose wording the rules were built around, decisions are found, which is why those numbers are not quoted as a result.
- Every quote is valid because a function checks that the quote is an exact span of the transcript before anything is shown.

## What it does not prove

It does not say how it will do on your meetings. Measure on yours: take 8 real transcripts, list the action items by hand, run the same tool.
