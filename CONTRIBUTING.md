# Contributing

- Set up with `docs/05-RUN-LOCALLY.md` (on Windows use WSL 2 with Ubuntu; PowerShell and cmd are not supported).
- Run `make test`, `python3 tools/check_docs.py` and `python3 tools/scan_secrets.py` before a pull request.
- Do not edit `packages/` here. It is a shared base copied from the main source.
- Never add a real key, a real person's name or a private link. Examples are sample data and labelled so.
- Numbers in docs come from `data/counts.json`. Run `python3 tools/make_counts.py` then `python3 tools/check_docs.py --fix`.
- If you change the answer engine or the extractor, rerun `tools/eval_questions.py` and `tools/eval_extraction.py`, and keep the first run files as they are.
- Any new read path needs a visibility test (see `apps/api/tests/test_visibility.py` and `apps/api/tests/test_hardening_access.py`). Any new setting needs a line in `.env.example` and a section in `docs/04-ENVIRONMENT-VARIABLES.md`; a test fails when one is missing.
