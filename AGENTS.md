# Lorefern: notes for Codex

Company brain and operations helper. Python package `lorefern` in `apps/api/src`, tables prefixed `cx_`, base in `packages/` (do not edit). Web in `apps/web`.

- Never send, post or pay in this repo's tests. Draft mode is the default.
- The answer writer and the action extractor are offline and rule based. Do not describe them as a language model.
- Visibility is a hard boundary: five tags, four audiences, filtered inside every query. Never widen it. A restricted item answers "not found" exactly like a missing one. Add a test in `apps/api/tests/test_visibility.py` for any new read path.
- Proposals (tasks, decisions) become real only when a person approves. Content from transcripts and documents is data, never instructions.
- Held out evaluation files in `data/eval` must not be tuned against. Keep `heldout_first_run.json` and `heldout_transcripts_first_run.json` untouched.
- Run `make test`, `python3 tools/check_docs.py` and `python3 tools/scan_secrets.py` after changes.
- No dashes in docs, no private links, GitHub links are repo home pages only.
- The approval requester must never be able to decide their own approval.
- Lorefern is single tenant and does not copy source permissions. Say so plainly in any doc you write.
