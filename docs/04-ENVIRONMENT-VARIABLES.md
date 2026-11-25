# 04 Environment variables

Every variable, in plain words. Values are never printed by any tool in this repo. `.venv/bin/python tools/doctor.py` checks them and `make check-env` compares your file with `.env.example`.

The API, the worker and `alembic upgrade head` all read the same settings: the environment, then the file named by `ENV_FILE` (default `.env`, relative to the folder you run the command in, so `ENV_FILE=../../.env` from `apps/api`). They always run on the same settings. Docker also needs `POSTGRES_PASSWORD` (below).

Where to put them: **local** in a `.env` file at the repo root (copied from `.env.example`); **Vercel** in the project's Environment Variables (web variables only: `API_BASE_URL`. The web app never reads `SESSION_SECRET`, so never put it on Vercel: it is the key that signs owner sessions and belongs on the API server only); **Railway** in each service's Variables tab; **Hetzner** in the `.env` file next to `docker-compose.yml` on the server. Vendor steps were read from the vendor's own pages where a date is shown with VERIFIED. Steps marked UNVERIFIED come from general knowledge and must be checked against the vendor's current page before you rely on them.


## SESSION_SECRET

- Required: required
- What it does: Signs the login cookie. A long random string only you know.
- How to get it:
  1. Run `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`.
  2. Paste the result as the value. Use a different one for every install.
  3. With `DEMO_MODE=false` the API and the worker refuse to start when it is shorter than 32 characters or still looks like an example (`change-me`, `example`, `dev-only` and similar). Anyone who has read the public code could otherwise sign in as the owner.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: A short or reused value makes sessions guessable. `make check-env` warns if it is left on the placeholder.

## DATABASE_URL

- Required: required
- What it does: Where data is stored. A SQLite file for the demo, Postgres for real use.
- How to get it:
  1. Demo: leave `sqlite:///./lorefern.sqlite3`.
  2. Postgres: create a database, then use `postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME`.
  3. Run `cd apps/api && ../../.venv/bin/alembic upgrade head` once, and again after every update. Alembic reads this value from the environment or from `.env` (or the file named by `ENV_FILE`) and stops with a message when it finds none. It never creates a stray SQLite file by mistake.
- Cost: SQLite is free. Postgres is part of your hosting bill.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: `.venv/bin/python tools/doctor.py` prints `FAIL database` with the error type.

## MODE

- Required: optional
- What it does: `draft` (the default) sends nothing. `live` allows reminders to be sent after a second person approves.
- How to get it:
  1. Leave `draft` until the go live checklist (doc 09) is done. With `MODE=live` and `DEMO_MODE=false` the API and the worker refuse to start while `COMPANY_NAME` is still the demo company or `EMAIL_FROM` is still the example address.
  2. Change it to `live` on the server only. The app can never switch itself to live.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: In `live` with DEMO_MODE on, the doctor warns.

## DEMO_MODE

- Required: optional
- What it does: `true` loads the made up company, uses offline tools only and moves the clock. It also switches on the public demo password, the made up approver, finance and staff accounts and the button that erases the database, but only while no `OWNER_PASSWORD_HASH` is set: setting a hash turns every one of those off even if `DEMO_MODE` is still `true`. The API also refuses `DEMO_MODE=true` together with `KNOWLEDGE_DIR`, because real documents would sit behind a login anyone can read in the repository. Code default `true`; `.env.example` says `false`.
- How to get it:
  1. Set `false` on a real install (the example already does).
  2. Then set OWNER_PASSWORD_HASH.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: With demo off and no password hash the doctor says OWNER_PASSWORD_HASH is empty.

## KILL_SWITCH

- Required: optional
- What it does: `true` stops every send and every write at once.
- How to get it:
  1. Set `true` to pause from outside the app. The owner can also press Pause all in the app.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Nothing to get wrong. If the app seems read only, check this first.

## LLM_MODE

- Required: optional
- What it does: `fixture` (default) means no language model is called. Lorefern answers with rules.
- How to get it:
  1. Leave `fixture`. A model writer is not wired into the answer path in this release.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Other values are accepted by the base but change nothing in Lorefern.

## LLM_BACKEND

- Required: optional
- What it does: Where the model jobs would run. `offline` (the default) is a built in rules stand in, not a language model, and needs no account. `fixture` replays recorded answers from `LLM_FIXTURES_DIR`. `anthropic` calls a real model and needs `ANTHROPIC_API_KEY`; it has been run only against a fake server on the developer's machine and never against the real service (UNVERIFIED). An API key in the environment alone never turns it on: only `LLM_BACKEND` does. Whatever writes the sentences, the code checks on them do not change.
- How to get it:
  1. Leave it as `offline` to try the product.
  2. For `anthropic`, create a key in the Anthropic console and set `ANTHROPIC_API_KEY` in the host's secret settings only.
- Cost: `offline` and `fixture` are free. `anthropic` is charged per use by the provider.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top. The web host does not need it.
- Check it: `.venv/bin/python tools/doctor.py` prints a PROBLEM line when `anthropic` has no key.
- If it is wrong: The doctor names the missing key.

## ANSWER_WRITER

- Required: optional
- What it does: `model` (the default) writes answer sentences with the model whenever `LLM_BACKEND` is `fixture` or `anthropic`; `rules` keeps the extractive rules writer. With `LLM_BACKEND=offline` nothing is called either way. Every sentence still goes through the groundedness check.
- How to get it: Not needed. Set `rules` to switch the model writer off while testing other model jobs.
- Cost: Free with `rules`; per use with a live model.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top. The web host does not need it.
- Check it: `.venv/bin/python tools/doctor.py` prints the model jobs that are switched on.
- If it is wrong: Answers say in their reason which writer wrote them.

## MEETING_EXTRACTOR

- Required: optional
- What it does: `model` lets the model propose action items and decisions from a transcript (every quote is checked against the transcript, the date is worked out by code from the spoken words, a person approves every item). `rules` (the default) uses the rules reader. Needs `LLM_BACKEND` `fixture` or `anthropic`.
- How to get it: Set `model` only after you tested it on your own meetings.
- Cost: Free with `rules`; per transcript with a live model.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py`.
- If it is wrong: A model failure falls back to the rules reader and says so in the audit note of the extraction.

## PROCESS_WORDING

- Required: optional
- What it does: `model` lets the model give the recurring processes found by counting a plain name (kept only when its words come from the examples). `rules` (default) keeps the counted label.
- How to get it: Optional polish.
- Cost: Free with `rules`; a small call per process with a live model.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py`.
- If it is wrong: The counted label stays.

## REVIEW_WRITER

- Required: optional
- What it does: `model` adds two plain sentences at the top of the weekly review, written from the review's own numbers only (a number that is not in the facts makes Lorefern use its plain sentence). `rules` (default) adds nothing.
- How to get it: Optional polish.
- Cost: Free with `rules`; one small call per review with a live model.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py`.
- If it is wrong: The plain sentence is used.

## MEETINGS_MAX_REMOVALS

- Required: optional
- What it does: The most meetings one read may remove from the app (default 5). A meeting is removed when the recorder or the transcript folder no longer returns it, and removing it also removes its transcript, its indexed text and the decisions and tasks that are only proposals. A drop of more than this number in one read is held back: nothing is removed, the Sources page says how many are waiting, and the owner presses **Confirm removal** (or sends `POST /api/sources/{id}/sync?confirm_removals=true`) when it is real. A read that returns no meeting at all while meetings exist is also held until the next read says the same, whatever this number is.
- How to get it: Leave it at 5 for a normal company. Raise it only if you really delete many transcripts at once.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top. The web host does not need it.
- Check it: Delete more than this many transcript files from the meetings folder, read the Sources page, and the confirm button appears.
- If it is wrong: Too low and an honest clean up waits for the owner. Too high and a recorder that lost its key could empty the app before anyone looks.

## LOGIN_BURST

- Required: optional
- What it does: How many sign in tries one address and email may make in a row before a short wait (one more every 12 seconds). Leave it at 5 outside tests; the browser tests raise it because every test signs in from one address.
- How to get it: Not needed.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top. The web host does not need it.
- Check it: `.venv/bin/python tools/doctor.py`.
- If it is wrong: Sign in answers "too many tries" sooner than expected.

## COMPANY_NAME

- Required: optional
- What it does: The company name shown in the app and in the weekly review heading. The default, `Pinegate Works`, is the made up demo company, so with `DEMO_MODE=false` it is listed as a problem, and with `MODE=live` the app refuses to start on it.
- How to get it:
  1. Type the company's name.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: `.venv/bin/python tools/doctor.py` lists the demo name as a problem.

## KNOWLEDGE_DIR

- Required: optional
- What it does: The folder of Markdown, text and PDF files Lorefern reads (the company folder). Each folder source reads its own path inside it, and meeting transcripts in its `meetings` folder are read by the meetings reader with the visibility each one declares. A document gets its tag from its own `visibility:` line, then from its folder (a `.visibility` file or the folder's `README.md`), and with neither it is visible to the owner only until you choose another tag for that source on the Sources page.
- How to get it:
  1. Copy the template: `python3 tools/new_company_folder.py /path/to/folder --name "Client name"`.
  2. Fill it in with the client (doc 10).
  3. Set `KNOWLEDGE_DIR` to that folder and press Read again on the Sources page.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: If the folder is missing the Sources page shows an error that names the folder.

## SEED_DIR

- Required: optional
- What it does: Where the demo seed data lives. Only the demo uses it.
- How to get it:
  1. Leave it empty. In demo mode the repo's `data` folder is used.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Wrong path in demo mode gives an empty demo.

## OWNER_EMAIL

- Required: required
- What it does: The email the owner signs in with.
- How to get it:
  1. Type the owner's email address.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: A typo means the owner cannot sign in. Fix it and restart the API.

## OWNER_PASSWORD_HASH

- Required: required when demo is off
- What it does: A hash of the owner's password. The password itself is never stored.
- How to get it:
  1. Run `.venv/bin/python tools/hash_password.py` (a plain `python3` finds the shared code by itself, but it still needs the libraries that `make install` puts in `.venv`, and says which one is missing when they are not there). A server that has no virtual environment, such as the Hetzner one, does not need one: make the hash on the computer where you ran `make install` and paste it into the server's `.env`.
  2. Type the password when asked. Copy the hash it prints.
  3. Paste the hash as the value.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: `.venv/bin/python tools/doctor.py` says OWNER_PASSWORD_HASH is empty.

## APPROVER_EMAIL

- Required: recommended
- What it does: The second person, with leadership access, who approves what the owner asks for.
- How to get it:
  1. Type the second person's email address.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Without it nothing that needs a second approver can be approved.

## APPROVER_PASSWORD_HASH

- Required: recommended
- What it does: A hash of the second person's password.
- How to get it:
  1. Run `.venv/bin/python tools/hash_password.py` for that person (on the computer where you ran `make install`) and paste the hash.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Same as the owner hash.

## MEMBERS_JSON

- Required: optional
- What it does: Everyone besides the owner and the approver who may sign in, and as which audience (leadership, finance or staff).
- How to get it:
  1. For each person run `.venv/bin/python tools/hash_password.py` and copy the hash.
  2. Write one JSON object on one line, for example `{"lena@yourcompany.test": {"audience": "finance", "password_hash": "PASTE_HASH"}}`.
  3. A person with no password hash cannot sign in outside demo mode. A second owner cannot be added this way.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: A person who cannot sign in has a missing or wrong hash, or a typo in the email.

## KNOWLEDGE_ADAPTER

- Required: optional
- What it does: Where company documents come from: `seed` (offline), `drive` or `notion`. A folder is read through KNOWLEDGE_DIR.
- How to get it:
  1. Leave `seed` for the demo.
  2. For Drive or Notion set the value and the token below.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: The doctor says which token is missing.

## MEETINGS_ADAPTER

- Required: optional
- What it does: Where meeting transcripts come from: `seed`, `file`, `fireflies` or `fathom`.
- How to get it:
  1. Leave `seed` for the demo.
  2. `file` reads transcript files from a folder or from the paste form.
  3. For Fireflies or Fathom set the value and the token below.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: The doctor says which token is missing.

## EMAIL_ADAPTER

- Required: optional
- What it does: How reminders are sent: `seed` (drafted only) or `smtp`. Sending needs `MODE=live`, a second person's approval and the kill switch off, all three checked in the app's own settings.
- How to get it:
  1. Leave `seed` until you are ready to send.
  2. For `smtp` fill the SMTP variables below.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: The doctor says SMTP_HOST or SMTP_USER is empty.

## WORKING_DAYS

- Required: optional
- What it does: The days counted as working days when due dates like next Friday are read. Decided default, a starting point the implementer changes per client.
- How to get it:
  1. Type the days, for example `Mon,Tue,Wed,Thu,Fri`.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Wrong days move a due date by a day or two.

## STUCK_NO_UPDATE_DAYS

- Required: optional
- What it does: Days without any update before an open task counts as silent. Default 10. Decided default, a starting point the implementer changes per client.
- How to get it:
  1. Pick a number that matches how often your team really updates tasks.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Too low and everything looks stuck.

## STUCK_BLOCKED_DAYS

- Required: optional
- What it does: Days a task may stay blocked before it is flagged. Default 5. Decided default, a starting point the implementer changes per client.
- How to get it:
  1. Pick a number.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Same as above.

## OVERLOAD_OPEN_TASKS

- Required: optional
- What it does: Open tasks per person before they are flagged as overloaded. Default 8. Decided default, a starting point the implementer changes per client.
- How to get it:
  1. Pick a number.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Same as above.

## OVERLOAD_DUE_SOON

- Required: optional
- What it does: Tasks due within 7 days per person before they are flagged. Default 5. Decided default, a starting point the implementer changes per client.
- How to get it:
  1. Pick a number.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Same as above.

## SOP_REVIEW_DAYS

- Required: optional
- What it does: Days after which a procedure with no review date counts as needing review. Default 180.
- How to get it:
  1. Pick a number.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Too low and every procedure looks stale.

## WEEKLY_REVIEW_WEEKDAY

- Required: optional
- What it does: The weekday the weekly review is built, 0 for Monday.
- How to get it:
  1. Pick 0 to 6.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Out of range values are ignored.

## DRIVE_SERVICE_ACCOUNT_JSON, DRIVE_SERVICE_ACCOUNT_FILE

- Required: one of the three Drive sign in ways is required for `drive`
- What it does: The key of a Google service account that may read the folders shared with it. Lorefern signs in with it and renews its own access token (doc 03). Read only. UNVERIFIED: written from Google's public documentation (https://developers.google.com/identity/protocols/oauth2/service-account, read 2026-11-23) and tested against a local fake token service, not against Google.
- How to get it:
  1. In the client's Google Cloud console create a project and enable the Drive API.
  2. Create a service account, then create a JSON key for it and download the file once.
  3. Share only the folders to be read with the service account's email address, as Viewer.
  4. Put the file's text in `DRIVE_SERVICE_ACCOUNT_JSON` in the host's secret settings, or keep the file outside the repository and put its path in `DRIVE_SERVICE_ACCOUNT_FILE`. Never commit it and never send it by chat or email.
- Cost: The API has no charge at normal use. Check Google's page yourself.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top. Only the API needs it; the web host does not.
- Check it: `.venv/bin/python tools/doctor.py --live`. A key that is not valid fails at start with plain words and never prints the key.
- If it is wrong: "key is not valid" means a wrong or cut off file; "invalid_grant" means the key was disabled or deleted, or this server's clock is wrong; empty results mean the folders were not shared with the service account.

## DRIVE_CLIENT_ID, DRIVE_CLIENT_SECRET, DRIVE_REFRESH_TOKEN

- Required: optional, the second Drive sign in way
- What it does: A consent given once by a person, traded for a fresh access token whenever needed (https://developers.google.com/identity/protocols/oauth2/web-server, read 2026-11-23). Reads what that person can read, so prefer the service account. UNVERIFIED against Google.
- How to get it:
  1. Create an OAuth client in the client's Google Cloud console and enable the Drive API.
  2. Let the person consent once with the read only Drive scope, asking for offline access, and keep the refresh token you get.
  3. Put the three values in the host's secret settings.
- Cost: Free at normal use.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top. Only the API needs it.
- Check it: `.venv/bin/python tools/doctor.py --live`.
- If it is wrong: "invalid_grant" means the person revoked access or the token expired, and the consent must be repeated.

## DRIVE_TOKEN

- Required: optional, the third and weakest Drive sign in way
- What it does: One access token you paste. It expires after about an hour and cannot be renewed, so use it only to try Drive once.
- How to get it: Create one in Google's OAuth Playground or with your own consent flow, read only Drive scope.
- Cost: Free at normal use.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top. Only the API needs it.
- Check it: `.venv/bin/python tools/doctor.py --live`.
- If it is wrong: Drive answers "refused the access" once the hour is over. Switch to the service account.

## DRIVE_SUBJECT, DRIVE_SCOPE, DRIVE_TOKEN_URI

- Required: optional
- What it does: `DRIVE_SUBJECT` is a user's email to act as when the Google Workspace admin has granted the service account domain wide delegation (leave empty otherwise). `DRIVE_SCOPE` defaults to the read only Drive scope; do not widen it. `DRIVE_TOKEN_URI` defaults to Google's token address and exists so tests can point at a local fake. It must be https and public.
- How to get it: Leave all three alone unless you know you need delegation.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py`.
- If it is wrong: Google answers "invalid_grant" or "unauthorized_client".

## NOTION_TOKEN

- Required: required for `notion`
- What it does: An internal integration token. Read only. UNVERIFIED: written from the vendor's public docs and not run against Notion.
- How to get it:
  1. Open https://developers.notion.com/ (not re-read on 2026-11-23, UNVERIFIED).
  2. Create an internal integration in your workspace and copy its token.
  3. Share the pages you want read with that integration. It sees only pages shared with it.
- Cost: The integration is free. Plan prices are on Notion's own page.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: A page not shared with the integration is simply missing.

## FIREFLIES_TOKEN

- Required: required for `fireflies`
- What it does: A Fireflies API key. Read only.
- How to get it:
  1. Open https://docs.fireflies.ai/ (read on 2026-11-23, VERIFIED).
  2. In Fireflies, open Integrations, then Fireflies API, and copy your API key. The key is sent as a Bearer token to https://api.fireflies.ai/graphql.
  3. Paste it as the value. Plan limits on API use are on Fireflies' own page.
- Cost: Depends on your Fireflies plan. Not read today, no figures quoted.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: An invalid key returns an error that Lorefern shows without the key.

## FATHOM_TOKEN

- Required: required for `fathom`
- What it does: A Fathom API key. Read only.
- How to get it:
  1. Open https://developers.fathom.ai/ (read on 2026-11-23, VERIFIED).
  2. In Fathom, open your settings, then API Access, and create a key. It is sent in the X-Api-Key header to https://api.fathom.ai/external/v1.
  3. Paste it as the value.
- Cost: Depends on your Fathom plan. Not read today, no figures quoted.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: An invalid key returns an error that Lorefern shows without the key.

## SMTP_HOST

- Required: required for `smtp`
- What it does: The mail server that sends reminders.
- How to get it:
  1. Ask your email provider for its SMTP host name (the provider's help page names it).
  2. Paste it as the value.
- Cost: Included in most email plans.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: `FAIL email/smtp` in the doctor with the error type.

## SMTP_PORT

- Required: optional
- What it does: The mail server port. Default 587 with TLS. The connection checks the server's certificate against the system's trusted list.
- How to get it:
  1. Use the port your provider names.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: A wrong port times out.

## SMTP_USER

- Required: required for `smtp`
- What it does: The mail account that sends the reminders.
- How to get it:
  1. Use a dedicated address such as reminders@yourcompany.test.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Login fails with an authentication error.

## SMTP_PASSWORD

- Required: required for `smtp`
- What it does: That account's password or app password.
- How to get it:
  1. Create an app password in the mail provider's security settings if it offers one.
  2. Paste it as the value. Never paste it in chat or in a file you commit.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Login fails with an authentication error.

## EMAIL_FROM

- Required: optional
- What it does: The From address on reminders. The default is a placeholder on `example.test`, so with `DEMO_MODE=false` it is listed as a problem, and with `MODE=live` the app refuses to start on it.
- How to get it:
  1. Use an address you control.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Mail may be rejected if the domain is not set up for sending.

## ALLOWED_EMAIL_DOMAINS

- Required: yes, outside demo mode (empty is listed as a problem by `tools/doctor.py` and the settings page)
- What it does: The email domains a task owner's address may be on, and the only domains task reminders are sent to. Comma separated, for example `yourcompany.com,yourcompany.co.uk`. A sub domain of a listed domain counts. While it is empty, no reminder is sent and no task owner can be given an address: the domains people sign in with are not used as a guess, because an owner who signs in with a free mail address would then allow every address at that provider. Do not list a free mail provider (gmail.com, outlook.com): the settings list it as a problem. Each address must be exactly one plain address: `a,b@company.com`, a name with angle brackets, a space or a line break inside it is refused, and the mail sender refuses it again before it connects. A person added with an address outside the list is refused, and a reminder to such an address is never sent, even if it was approved.
- How to get it:
  1. List your own company domains, with no spaces needed.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top. The web host does not need it.
- Check it: `POST /api/owners` with an outside address answers that the address is not on the company's domains, and with the setting empty it says the setting is not set.
- If it is wrong: Reminders to a real colleague are skipped. List the domain.

## SMTP_USE_TLS

- Required: optional
- What it does: `true` (the default) starts an encrypted connection and checks the mail server's certificate and host name before the password is sent. `false` is allowed only for a mail server on this same computer (`localhost`); for any other host nothing is sent and the settings list it as a problem.
- How to get it: Leave it `true`.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py --live`.
- If it is wrong: "The mail server's certificate could not be verified" means the server's certificate is not valid for the host name you gave. Use the host name on the certificate.

## TIMEZONE

- Required: optional
- What it does: The time zone in which "today" is worked out: due dates, reminders, which tasks are overdue and the weekly review. Default `UTC`. A demo uses its own fixed clock.
- How to get it:
  1. Use a zone name such as `Europe/Berlin` or `America/Chicago`.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` lists a name it does not know.
- If it is wrong: A zone behind or ahead of yours moves "today" by a day for part of the day.

## APP_NAME

- Required: optional
- What it does: The name used in logs and on `/health`. Default `lorefern`.
- How to get it: Leave it.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: Open `/health`.
- If it is wrong: Nothing breaks.

## ALLOW_DEMO_SERVER

- Required: optional
- What it does: The API refuses `DEMO_MODE=true` on a Postgres database, because a demo has a button that erases every table. `true` allows it for a throw away trial on a private network.
- How to get it: Leave it `false` on a real install.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py`.
- If it is wrong: The API stops at start and says why.

## MAX_BODY_BYTES

- Required: optional
- What it does: The largest request the API reads, in bytes. A larger one is refused before it is read. Default `26214400` (25 MB), which is more than a pasted transcript needs.
- How to get it: Leave it.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top. Caddy has its own limit in `deploy/hetzner/Caddyfile`.
- Check it: Send a request over the limit: the answer is 413.
- If it is wrong: Too low and a long transcript is refused.

## POSTGRES_PASSWORD

- Required: required for Docker, not read by the app itself
- What it does: The password of the Postgres container. `docker-compose.yml` puts it inside `DATABASE_URL`, so use letters and digits only (or percent encode it).
- How to get it:
  1. Run `openssl rand -hex 24` and paste the result.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: only the Docker path (doc 08). `docker compose up` stops with a message when it is empty.
- Check it: `docker compose up -d --build`.
- If it is wrong: A character such as `@` or `/` breaks the database address: the API says it cannot connect.

## ENV_FILE

- Required: optional, not a line inside the file
- What it does: Names the settings file the API, the worker and alembic read. Set it in the shell, for example `ENV_FILE=/etc/lorefern/prod.env`. Default `.env`.
- How to get it: Not needed with one file.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `make check-env` reads `.env`; pass `--env` for another file.
- If it is wrong: The API starts on defaults and the refusal checks tell you which setting is missing.

## LLM_MODEL, LLM_HARD_MODEL, LLM_BULK_MODEL

- Required: optional
- What it does: The model names used when `LLM_BACKEND` is `anthropic`. `LLM_MODEL` sets one name for both jobs. Defaults `claude-sonnet-5-5` and `claude-haiku-5-5`. Not used with `offline`.
- How to get it: Leave them unless you use `anthropic` and want another model.
- Cost: Charged per use by the provider with `anthropic`.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top. The web host does not need them.
- Check it: `.venv/bin/python tools/doctor.py`.
- If it is wrong: The provider answers with an unknown model error, shown in plain words.

## ANTHROPIC_API_KEY, ANTHROPIC_BASE_URL, ANTHROPIC_VERSION

- Required: the key is required for `LLM_BACKEND=anthropic`
- What it does: The key, the address (default `https://api.anthropic.com`, plain `http` only for `localhost` tests) and the version header. A key in the environment alone never turns the model on.
- How to get it:
  1. Create a key in the Anthropic console and set it in the host's secret settings only.
  2. Leave the address and the version alone.
- Cost: Charged per use by the provider.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top. Only the API needs them.
- Check it: `.venv/bin/python tools/doctor.py` prints a PROBLEM line when `anthropic` has no key.
- If it is wrong: The doctor names what is missing.

## LLM_TIMEOUT, LLM_MAX_TOKENS, LLM_MAX_RETRIES, LLM_THINKING

- Required: optional
- What it does: Seconds per request (default 120), the reply limit (default 4096), retries after a failed try (default 2) and `default` or `off` for the lowest thinking setting. Only used with a model backend.
- How to get it: Leave them.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py`.
- If it is wrong: Model jobs time out or run short.

## LLM_CALL_BUDGET, LLM_BUDGET_USD

- Required: optional
- What it does: The most live model calls per process, and the most tracked spend in US dollars. Empty means no limit. A job over the limit stops with a plain message and the rules writer is used.
- How to get it: Set a number if you use `anthropic` and want a ceiling.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py`.
- If it is wrong: The limit is reached sooner than you expect.

## LLM_FIXTURES_DIR, LLM_RECORD, LLM_REDACT, LLM_LOG_PROMPTS

- Required: `LLM_FIXTURES_DIR` is required for `LLM_BACKEND=fixture` and for `LLM_RECORD`
- What it does: The folder recorded answers are read from, whether every live answer is saved there, whether prompts and keys are hidden from logs and fixtures (default on), and whether a shortened, redacted prompt is logged (default off).
- How to get it: Used by developers. Leave them alone on a real install.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` says when `LLM_FIXTURES_DIR` is empty while it is needed.
- If it is wrong: The doctor names the setting.

## DRIVE_BASE_URL, NOTION_BASE_URL, FIREFLIES_BASE_URL, FATHOM_BASE_URL

- Required: optional
- What it does: The web address each service is read from. The defaults are the real services. They are checked: only `https` and only public addresses are accepted. They exist so the tests can point at a local fake.
- How to get it: Leave them.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py`.
- If it is wrong: The source says the address is refused.

## Which Drive folders or Notion pages a source reads

This is not a setting. On the Sources page the path of a Drive source is the Drive folder ids (separated by commas) and the path of a Notion source is the page ids. A source that names its own folders or pages reads only those (Drive also walks the folders below them) and takes its files from any other source of the same kind, so each file belongs to one source and one tag. Only one Drive source and one Notion source may leave the field empty (everything the sign in can reach). Trashed files are never listed.

## API_BASE_URL

- Required: required on the web host
- What it does: Where the web app finds the API.
- How to get it:
  1. Local: `http://127.0.0.1:8000`.
  2. Hosted: your API address with no trailing slash, for example `https://api.example.com`.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: The web app shows a clear error when it cannot reach the API.

## INSECURE_COOKIES

- Required: demo only
- What it does: `1` lets the demo sign in over plain http on localhost. Never set it on a real site.
- How to get it:
  1. Set `1` only for local demos and the browser tests.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: On a real site a cookie without the secure flag is a risk.

## NEXT_PUBLIC_DEMO_HINT

- Required: demo only
- What it does: `1` shows the demo password hint on the sign in page. Next.js copies this value into the page when the web app is built, so it only works when it is set for `pnpm build` (`NEXT_PUBLIC_DEMO_HINT=1 pnpm build`). Setting it only when the web app starts has no effect.
- How to get it:
  1. Set `1` at build time, only for local demos.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `.venv/bin/python tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Leave it unset on a real site.
