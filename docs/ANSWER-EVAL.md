# Answer results

What was measured, how, and what it does not prove.

## Method

- A **dev** set of 38 questions (`data/eval/dev_questions.json`) was used while building. The answer rules were tuned on it, so its score is not a result.
- A **held out** set of 56 questions (`data/eval/heldout_questions.json`) was written in different words from the documents and from the dev set, with an answer key (which document, which text must appear, whether the answer should be an answer, a conflict, a refusal or not found, and which audience asks).
- The first run on the held out set is saved untouched as `data/eval/heldout_first_run.json`. After that run the rules were tuned on the failures, so the later run (`heldout_after_tuning.json`) is **no longer held out**. Both are reported.
- The answer writer is **rules, not a language model**.
- A question is right when the outcome is the expected one, a cited document is an expected one, and every required text is in the answer. A restricted fact appearing anywhere in a response for an audience that may not see it counts as a **leak** and is counted on its own.

## Results

| Run | Right | Leaks | Citations that point at the right characters |
| --- | --- | --- | --- |
| Held out, first run (saved untouched) | 22 of 56 (39.3 percent) | 0 | 32 of 40 |
| Held out, after tuning on its failures | 32 of 56 (57.1 percent) | 0 | 51 of 51 |
| Dev set (tuned on it) | 33 of 38 (86.8 percent) | 0 | 41 of 41 |

Held out by question kind, first run then after tuning:

| Kind | Questions | First run | After tuning |
| --- | --- | --- | --- |
| Single document | 22 | 10 | 8 |
| Two documents needed | 5 | 1 | 1 |
| Documents that disagree | 3 | 1 | 3 |
| Decision questions | 7 | 2 | 5 |
| About a meeting | 4 | 1 | 1 |
| Restricted from this audience | 6 | 1 | 5 |
| Not written anywhere | 6 | 3 | 6 |
| Off topic or an instruction | 3 | 3 | 3 |

## What this says

- **Never a leak, never an uncited answer.** That is the part the design guarantees.
- **Single document questions are the weak spot** (8 of 22). The matcher needs words the document uses. Reworded questions miss. The first run's 10 of 22 fell to 8 after tuning on other classes, because stricter "not found" rules cost a few answers. That is a real trade off.
- Tuning raised the total mostly by fixing conflicts, restricted questions and "not written anywhere", which are about when to refuse.
- One key item (h24, two documents) is arguably wrong: the disagreement between the two documents is real, so Lorefern's "documents disagree" is a fair answer.
- Three held out wordings (salary, offer, expense) were typed into a quick check before the first run. Nothing was tuned on them.

## What it does not prove

It does not say how Lorefern will do on your documents, or with a language model writer. Write 50 or more real questions with the right document for each, run `tools/eval_questions.py` on them, and read the misses before you go live (doc 09).
