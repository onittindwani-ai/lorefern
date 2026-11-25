# Updating

1. Back up the database (doc 11).
2. Pull the new version and read `../CHANGELOG.md`.
3. `make install`, or `.venv/bin/pip install -c constraints.txt -e packages/core-py -e "apps/api[dev]"` and `pnpm install`. If your environment was made with uv, use `uv pip install --python .venv/bin/python -c constraints.txt -e packages/core-py -e "apps/api[dev]"` instead of pip.
4. Postgres: `cd apps/api && ../../.venv/bin/alembic upgrade head`. SQLite creates missing tables by itself.
5. `pnpm build`, restart the API, worker and web app.
6. Run `.venv/bin/python tools/doctor.py`, open the Sources page, and run `python3 tools/check_company_folder.py <folder>`.

## Docker (the Hetzner or Railway way)

There is no virtual environment on the server, so steps 3 and 5 become: back up (doc 11), `git pull`, read `../CHANGELOG.md`, then `docker compose up -d --build`. The API runs the Postgres migrations itself when it starts and refuses to start when one fails, so look at `docker compose logs api` after the update; `docker compose exec api alembic upgrade head` runs them by hand. UNVERIFIED: this path was started in CI but not run against a real host. To go back, check out the older version and run the same command (a migration that already ran is not undone: restore the backup if the older version cannot read the database).

A send approval that was waiting when you updated from a version before the recipient check cannot be approved (it has no record of who it would send to): reject it and ask again from the Tasks page.

The shared `packages/` folders are copies of a base kept in the hub. Do not edit them in this repo. A needed change goes to the hub as a new base version.

## Pinned packages

`constraints.txt` pins every third party Python package to the version the tests ran against, so an install today gives the same set as the one that was tested (`make install`, the Docker image and CI all use it). After a deliberate upgrade of a package, install the new version, run the tests, then rewrite the file with `tools/make_constraints.py` from the hub repository (`sendora-ai-systems`).
