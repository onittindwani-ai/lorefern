# Operating and backups

## Backups

- **Database.** Postgres: `deploy/hetzner/backup.sh` or your host's managed backups. SQLite: copy the `.sqlite3` file while the API is stopped, or use `sqlite3 lorefern.sqlite3 ".backup backup.sqlite3"`.
- **Company folder.** It is the source of truth for most knowledge. Keep it in Git or in a backed up volume. `deploy/hetzner/backup.sh` also writes a compressed copy of the knowledge volume next to the database dump. Copy both off the server (`BACKUP_COPY_TO`): a backup on the same disk is not a backup.
- **Settings.** Keep the `.env` file in a password manager, never in Git.

## Test a restore

1. Make a new empty database.
2. Restore the dump into it. For Postgres: `pg_restore --no-owner -d NEWDB backup.dump` (or `psql` for a plain dump).
3. Start the API against it and sign in. Open Sources: the document counts must match.
4. Open the Audit log and press **Check the chain**. It must say intact.

## Daily checks

- The worker is running (the Sources page shows the last read time).
- The kill switch is off, and the banner shows the mode you expect.
- `.venv/bin/python tools/doctor.py` prints no FAIL.

## Logs

The API logs request lines without bodies. Tokens, passwords and document text are not logged. If you add logging, keep it that way.

## Stopping and restarting

Stop the web app, then the worker, then the API. Start in the reverse order. Nothing is lost because every change is in the database.
