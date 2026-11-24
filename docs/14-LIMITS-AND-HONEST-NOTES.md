# Limits and honest notes

Read this before you promise a client anything.

## The answer writer is rules, not a language model

Answers are made by code that picks the sentences of your documents that best cover the question, then checks that each sentence is backed by its source. That is why it never invents. It is also why it misses questions worded differently from the document. On 56 held out questions written after the rules, the first run got **22 right (39 percent)** and the version tuned afterwards **32 (57 percent)**, with **no leak of restricted text** and every citation pointing at the right characters. See `ANSWER-EVAL.md`. On two independent sets written by people who never saw the code the first runs got 42 of 79 and 65 of 87, still with no real leak of restricted text; see `INDEPENDENT-EVAL.md`, which also lists the weak spots (reworded questions, questions that need two documents, answering when it should say not found). A language model writer exists behind the same checks (next section) but has never run with a real key.

## Meeting extraction is rules too

On 8 held out transcripts in other styles the first run found **60 percent of the action items (recall) with 80 percent of its proposals right (precision)**, and **0 of 3 decisions** because the decisions were phrased in ways the rules do not know. Every quote it shows is real (100 percent). See `EXTRACTION-EVAL.md`. On two independent sets of 10 transcripts each the first runs found **64 percent (set A) and 71 percent (set B)** of the action items, with a strict precision of **0.62 and 0.54** (extra proposals were mostly vague "someone should" lines, which are flagged as unowned), every owner it found right, and **6 of 10 and 8 of 10** decisions (`INDEPENDENT-EVAL.md`). That is why every item waits for a person, and why a missed item is more likely than a false one.

## The model path exists and is UNVERIFIED live

With `LLM_BACKEND=anthropic` (or `fixture`) four jobs can run on a language model instead of the rules: the answer writer (`ANSWER_WRITER`, on by default whenever a model backend is on), the meeting reader (`MEETING_EXTRACTOR=model`), plain names for recurring processes (`PROCESS_WORDING=model`) and a two sentence intro for the weekly review (`REVIEW_WRITER=model`). The default `LLM_BACKEND=offline` calls nothing, even when an API key is in the environment. What is tested: the request shape against a fake server on this machine, recorded answers made by that fake server (not by a model), and the checks around the model. What is **not** known, because it has never run with a real key: how well a real model reads your documents and your meetings, what it costs per question and per meeting, and how often it fails.

What the code does around the model, and tests prove: document text, questions and transcripts go in marked data blocks that the system prompt says to treat as data; sentences of a passage that give orders and lines of a transcript that give orders are never sent; a model only ever sees passages the asker may see; every sentence goes through the groundedness check and unsupported ones are removed; a meeting quote is accepted only when it is the transcript's own characters, the date is worked out by code from the spoken words, and an owner must exist in your owners table; a model cannot set a visibility tag, a status, an owner id or approve anything, because its answer has no such fields and this code has no access to those functions; a bad answer, the kill switch or a spent call budget falls back to the rules. Measure it on your own documents and meetings before you promise a client anything (`tools/eval_questions.py`, `tools/eval_independent.py`).

## Things that are not built or not verified

- **Per user source permissions are not mirrored** (doc 13). Tags are the only visibility rule.
- **Single tenant.** One company per install.
- **Real vendors were never called.** Drive, Notion, Fireflies, Fathom and SMTP were tested only against local stand ins. The Fireflies and Fathom fields were read from their current docs on 2026-11-23. Otter's and Meetily's export layouts and the Slack export layout are UNVERIFIED.
- **Drive sign in renewal is UNVERIFIED.** The adapter signs in with a service account key or a refresh token and renews its own access token, with expiry handling and one retry on a refused request. That was written from Google's public documentation and tested against a local fake token service and a fake Drive only. It has never run against Google. A single pasted `DRIVE_TOKEN` still expires after about an hour. Revoked or disabled credentials stop the sync with a plain message until someone fixes them.
- **Onboarding a new client** was not found by the process detector in the demo data (6 of 7 planted processes were found).
- **A reworded question can return a wrong visible answer** (a limit of word matching, not a leak). Example: "Did anyone make an offer to buy the company?" can hit an unrelated sentence. Always read the passage.
- **Dates.** "Friday" means the next Friday after the meeting, "next Friday" the Friday of the following week, "end of week" Friday. Check this matches how the company speaks.
- **Docker, hosting guides and CI** were written but never run (no Docker daemon, no accounts).
- **Postgres** was used for the migration cycle only. The full tests and the browser tests ran on SQLite.
- **Screen reader use** was not tested. Axe finds no serious or critical problem and the keyboard path works.
- **Task board by keyboard.** Each board card is a labelled group with a real Open button inside it. Focus a card and press Enter (or Tab to its Open button) to open the task, approve it from the sheet, and use the keyboard lift (Space, arrows, Space) to move it between columns. A browser test covers the open path. The Table view is still there for large lists.

## Numbers in the demo are for made up data

The fictional company, its documents and its meetings were written by us. Scores on your own documents will differ, usually lower. Measure them (doc 09).
