# Run it on your own computer

`01-QUICK-DEMO.md` is the fast version. This is the full one, including real settings and Postgres.

## Install

Windows: use WSL 2 with Ubuntu and work inside it. PowerShell and cmd are not supported. On Ubuntu or Debian (and WSL) install the venv package first, or `python3 -m venv` fails with "ensurepip is not available": `sudo apt install python3-venv python3-pip` (for a specific version, `python3.12-venv`). `corepack enable` may need `sudo` with a system Node.

1. Python 3.12 or newer (or uv, which fetches it), Node 22 or newer, pnpm (`corepack enable` or `npm i -g pnpm`). `make install` picks uv or python3.12 for you.
2. `python3.12 -m venv .venv`, or with uv (no Python 3.12 needed first): `uv venv --python 3.12 .venv`
3. `.venv/bin/pip install -c constraints.txt -e packages/core-py -e "apps/api[dev]"`, or with uv: `uv pip install --python .venv/bin/python -c constraints.txt -e packages/core-py -e "apps/api[dev]"` (add `-e "apps/api[postgres]"` if you use Postgres).
4. `pnpm install` then `pnpm build`.

## Settings

`cp .env.example .env`, then follow `04-ENVIRONMENT-VARIABLES.md`. The example has `DEMO_MODE=false`, so the API will not start until you set a real `SESSION_SECRET` (32 or more random characters) and an `OWNER_PASSWORD_HASH`; to look around with the made up company set `DEMO_MODE=true` instead and leave the hash empty. Run `make check-env` (it needs only Python) and then `.venv/bin/python tools/doctor.py`. The first reads your file, the second tests the services. Neither prints a value.

## Database

- **SQLite** (default): tables are created on start. In demo mode the made up company is loaded when the database is empty.
- **Postgres**: set `DATABASE_URL=postgresql+psycopg://user:pass@host:5432/dbname`, then `cd apps/api && ../../.venv/bin/alembic upgrade head`. Alembic reads `DATABASE_URL` from the environment or from `.env` (or the file named by `ENV_FILE`, relative to the folder you run it in: `ENV_FILE=../../.env`) and stops with a message when it finds none. Do this on every update.

## Two programs, then the web app

Run each in its own terminal, from the project folder.

1. **API:** `.venv/bin/python -m uvicorn lorefern.api.app:app_from_env --factory --port 8000 --proxy-headers` (it refuses to start on unsafe settings and says which)
2. **Worker** (it reads the same settings file and refuses the same unsafe settings; it runs the jobs: read new transcripts, draft reminders, check stuck work, build the weekly review): `.venv/bin/python -m lorefern.worker`
3. **Web:** `pnpm --filter web start` after `pnpm build`, or `pnpm dev` while you change code.

Open http://localhost:3000.

## Tests

- Python: `.venv/bin/python -m pytest`. The last full run is in `data/counts.json`: <!--n:tests.passed-->416<!--/n--> passed, <!--n:tests.skipped-->1<!--/n--> skipped (one needs a Postgres, set `TEST_POSTGRES_URL`), coverage <!--n:tests.coverage_percent-->94.6<!--/n--> percent of the `lorefern` package.
- Evaluations: `.venv/bin/python tools/eval_extraction.py` and `tools/eval_questions.py --set dev` (see `EXTRACTION-EVAL.md` and `ANSWER-EVAL.md`).
- Browser tests: `pnpm e2e` (needs Google Chrome; it starts its own API and web server and a throwaway database). It tests the last build, so run `pnpm build` first. <!--n:e2e.tests-->30<!--/n--> tests.

## Stop everything

Press Ctrl+C in each terminal. Data stays in the database.
