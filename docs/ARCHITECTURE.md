# Architecture

Lorefern is a Python API and worker over a database, with a Next.js web app in front. It sits on a shared base (`packages/core-py`, `packages/ui-kit`) that every Sendora system uses. The base is copied into this repo and never edited here.

```
Sources                      Lorefern API (FastAPI)                  Web (Next.js)
 company folder  ----+        ingest -> documents -> passages        Ask, Tasks, Meetings,
 Slack export    ----+---->   index (FTS + word vector)  ------>     SOP map, Review, Decisions,
 Drive / Notion  ----+        qa (rules, groundedness)               Sources, Folder, Approvals
 recorders / text ---+        meetings -> proposals -> tasks
                              stuck, reminders, SOPs, review
                              approvals, audit, kill switch
```

## Layers

1. **Adapters** (`apps/api/src/lorefern/adapters/`): one small class per tool, all with `list_documents` or `list_meetings` and `healthcheck`. Tier A adapters are built and tested offline. Tier B were written from vendor docs and tested only against the local stand ins in `mock/`. The registry (`registry.py`) lists every adapter and what it needs.
2. **Ingest** (`ingest.py`, `chunking.py`): reads a source, resolves the visibility tag, splits documents by heading into passages that keep their own character offsets, and stores them. `INDEX.md` is never read.
3. **Search** (`search.py`): SQLite full text (FTS5) and a hashed word vector, merged by reciprocal rank fusion. Word weights (IDF) are computed per tag set so restricted passages never influence weights seen by others. Every query filters on tag first.
4. **Answers** (`qa.py`): decline instructions and off topic questions, search visible tags only, detect conflicts between documents, choose sentences with a rules writer, run the groundedness check, and cite the passage with exact characters.
5. **Meetings and tasks** (`actions.py`, `dates.py`, `tasks.py`): a rules extractor proposes action items and decisions with an exact quote that code validates; a due date parser reads phrases such as "by Friday". Proposals become tasks only when a person approves. Every change is an event, so it can be undone.
6. **Operations** (`stuck.py`, `reminders.py`, `sops.py`, `review.py`): stuck work rules, drafted reminders (sending goes through the approval queue), recurring work detection and SOP coverage, and the weekly review, where `check_sources` proves every line has a link to an in scope record.
7. **Safety** (base): `guard_write` and `@write_action` refuse writes in draft mode and with the kill switch on; the approval queue; the audit hash chain; rate limits.
8. **API** (`api/`): routes for reading, writing, admin and the demo. Every route that reads applies the viewer's audience. Writes need an owner or leadership audience.
9. **Web** (`apps/web`): server side proxy to the API (cookie session, required header on changes), pages, the ask bar, and the shared kit.

## Visibility is a layer, not a feature

`visibility.py` defines the tags and audiences. `api/deps.py` resolves who is asking (and the owner's preview). Reads pass the allowed tags into the query. Nothing filters after the fact, because a count or a title computed before filtering would leak.

## Data model (tables, prefix `cx_`)

state, owner, source, document, chunk (carries a copy of its tag), meeting, transcript, task, task_event, reminder, decision, process, question, weekly_review. See `apps/api/src/lorefern/models.py` and `apps/api/alembic/versions/`.

## Jobs

The worker runs `read` (read sources and new transcripts, propose tasks, detect processes, draft reminders) every two minutes and `review` hourly (builds last week's review once, for both scopes, on the configured weekday).

## The model path

`model_tasks.py` holds the four jobs a language model may do (answer sentences, meeting reading, process names, the review intro) behind the shared wrapper. `offline_llm.py` is the rules stand in that speaks the same JSON, so recorded fixtures and the fake server (`mock/anthropic_mock.py`) use the same shapes as a real model would. Order of safety: marked data blocks, sentences and lines that give orders never sent, a fixed schema with no field for a tag, status, owner id or approval, then code that checks every quote, citation and number before anything is stored, and approval by a person. Live use is UNVERIFIED; see `facts/models.md`.

## What is not here

No language model in the answer path, no per user source permissions, no multi tenant, no webhooks (Lorefern only pulls).
