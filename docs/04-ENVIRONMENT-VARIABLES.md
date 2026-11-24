# 04 Environment variables

Every variable, in plain words. Values are never printed by any tool in this repo. `python3 tools/doctor.py` checks them and `make check-env` compares your file with `.env.example`.

Where to put them: **local** in a `.env` file at the repo root (copied from `.env.example`); **Vercel** in the project's Environment Variables (web variables only: `API_BASE_URL` and `SESSION_SECRET`); **Railway** in each service's Variables tab; **Hetzner** in the `.env` file next to `docker-compose.yml` on the server. Vendor steps were read from the vendor's own pages where a date is shown with VERIFIED. Steps marked UNVERIFIED come from general knowledge and must be checked against the vendor's current page before you rely on them.


## SESSION_SECRET

- Required: required
- What it does: Signs the login cookie. A long random string only you know.
- How to get it:
  1. Run `python3 -c "import secrets; print(secrets.token_urlsafe(48))"`.
  2. Paste the result as the value. Use a different one for every install.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: A short or reused value makes sessions guessable. `make check-env` warns if it is left on the placeholder.

## DATABASE_URL

- Required: required
- What it does: Where data is stored. A SQLite file for the demo, Postgres for real use.
- How to get it:
  1. Demo: leave `sqlite:///./lorefern.sqlite3`.
  2. Postgres: create a database, then use `postgresql+psycopg://USER:PASSWORD@HOST:5432/DBNAME`.
  3. Run `cd apps/api && ../../.venv/bin/alembic upgrade head` once, and again after every update.
- Cost: SQLite is free. Postgres is part of your hosting bill.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: `python3 tools/doctor.py` prints `FAIL database` with the error type.

## MODE

- Required: optional
- What it does: `draft` (the default) sends nothing. `live` allows reminders to be sent after a second person approves.
- How to get it:
  1. Leave `draft` until the go live checklist (doc 09) is done.
  2. Change it to `live` on the server only. The app can never switch itself to live.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: In `live` with DEMO_MODE on, the doctor warns.

## DEMO_MODE

- Required: optional
- What it does: `true` loads the made up company and uses offline tools only. Turn it off for a real client.
- How to get it:
  1. Set `false` on a real install.
  2. Then set OWNER_PASSWORD_HASH.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: With demo off and no password hash the doctor says OWNER_PASSWORD_HASH is empty.

## KILL_SWITCH

- Required: optional
- What it does: `true` stops every send and every write at once.
- How to get it:
  1. Set `true` to pause from outside the app. The owner can also press Pause all in the app.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Nothing to get wrong. If the app seems read only, check this first.

## LLM_MODE

- Required: optional
- What it does: `fixture` (default) means no language model is called. Lorefern answers with rules.
- How to get it:
  1. Leave `fixture`. A model writer is not wired into the answer path in this release.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Other values are accepted by the base but change nothing in Lorefern.

## LLM_BACKEND

- Required: optional
- What it does: Where the model jobs would run. `offline` (the default) is a built in rules stand in, not a language model, and needs no account. `fixture` replays recorded answers from `LLM_FIXTURES_DIR`. `anthropic` calls a real model and needs `ANTHROPIC_API_KEY`; it has been run only against a fake server on the developer's machine and never against the real service (UNVERIFIED). An API key in the environment alone never turns it on: only `LLM_BACKEND` does. Whatever writes the sentences, the code checks on them do not change.
- How to get it:
  1. Leave it as `offline` to try the product.
  2. For `anthropic`, create a key in the Anthropic console and set `ANTHROPIC_API_KEY` in the host's secret settings only.
- Cost: `offline` and `fixture` are free. `anthropic` is charged per use by the provider.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top. The web host does not need it.
- Check it: `python3 tools/doctor.py` prints a PROBLEM line when `anthropic` has no key.
- If it is wrong: The doctor names the missing key.

## ANSWER_WRITER

- Required: optional
- What it does: `model` (the default) writes answer sentences with the model whenever `LLM_BACKEND` is `fixture` or `anthropic`; `rules` keeps the extractive rules writer. With `LLM_BACKEND=offline` nothing is called either way. Every sentence still goes through the groundedness check.
- How to get it: Not needed. Set `rules` to switch the model writer off while testing other model jobs.
- Cost: Free with `rules`; per use with a live model.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top. The web host does not need it.
- Check it: `python3 tools/doctor.py` prints the model jobs that are switched on.
- If it is wrong: Answers say in their reason which writer wrote them.

## MEETING_EXTRACTOR

- Required: optional
- What it does: `model` lets the model propose action items and decisions from a transcript (every quote is checked against the transcript, the date is worked out by code from the spoken words, a person approves every item). `rules` (the default) uses the rules reader. Needs `LLM_BACKEND` `fixture` or `anthropic`.
- How to get it: Set `model` only after you tested it on your own meetings.
- Cost: Free with `rules`; per transcript with a live model.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py`.
- If it is wrong: A model failure falls back to the rules reader and says so in the audit note of the extraction.

## PROCESS_WORDING

- Required: optional
- What it does: `model` lets the model give the recurring processes found by counting a plain name (kept only when its words come from the examples). `rules` (default) keeps the counted label.
- How to get it: Optional polish.
- Cost: Free with `rules`; a small call per process with a live model.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py`.
- If it is wrong: The counted label stays.

## REVIEW_WRITER

- Required: optional
- What it does: `model` adds two plain sentences at the top of the weekly review, written from the review's own numbers only (a number that is not in the facts makes Lorefern use its plain sentence). `rules` (default) adds nothing.
- How to get it: Optional polish.
- Cost: Free with `rules`; one small call per review with a live model.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py`.
- If it is wrong: The plain sentence is used.

## LOGIN_BURST

- Required: optional
- What it does: How many sign in tries one address and email may make in a row before a short wait (one more every 12 seconds). Leave it at 5 outside tests; the browser tests raise it because every test signs in from one address.
- How to get it: Not needed.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top. The web host does not need it.
- Check it: `python3 tools/doctor.py`.
- If it is wrong: Sign in answers "too many tries" sooner than expected.

## COMPANY_NAME

- Required: optional
- What it does: The company name shown in the app and in the weekly review heading.
- How to get it:
  1. Type the company's name.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: An empty value falls back to the demo name.

## KNOWLEDGE_DIR

- Required: optional
- What it does: The folder of Markdown, text and PDF files Lorefern reads (the company folder).
- How to get it:
  1. Copy the template: `python3 tools/new_company_folder.py /path/to/folder --name "Client name"`.
  2. Fill it in with the client (doc 10).
  3. Set `KNOWLEDGE_DIR` to that folder and press Read again on the Sources page.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: If the folder is missing the Sources page shows an error that names the folder.

## SEED_DIR

- Required: optional
- What it does: Where the demo seed data lives. Only the demo uses it.
- How to get it:
  1. Leave it empty. In demo mode the repo's `data` folder is used.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Wrong path in demo mode gives an empty demo.

## OWNER_EMAIL

- Required: required
- What it does: The email the owner signs in with.
- How to get it:
  1. Type the owner's email address.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: A typo means the owner cannot sign in. Fix it and restart the API.

## OWNER_PASSWORD_HASH

- Required: required when demo is off
- What it does: A hash of the owner's password. The password itself is never stored.
- How to get it:
  1. Run `python3 tools/hash_password.py`.
  2. Type the password when asked. Copy the hash it prints.
  3. Paste the hash as the value.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: `python3 tools/doctor.py` says OWNER_PASSWORD_HASH is empty.

## APPROVER_EMAIL

- Required: recommended
- What it does: The second person, with leadership access, who approves what the owner asks for.
- How to get it:
  1. Type the second person's email address.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Without it nothing that needs a second approver can be approved.

## APPROVER_PASSWORD_HASH

- Required: recommended
- What it does: A hash of the second person's password.
- How to get it:
  1. Run `python3 tools/hash_password.py` for that person and paste the hash.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Same as the owner hash.

## MEMBERS_JSON

- Required: optional
- What it does: Everyone besides the owner and the approver who may sign in, and as which audience (leadership, finance or staff).
- How to get it:
  1. For each person run `python3 tools/hash_password.py` and copy the hash.
  2. Write one JSON object on one line, for example `{"lena@yourcompany.test": {"audience": "finance", "password_hash": "PASTE_HASH"}}`.
  3. A person with no password hash cannot sign in outside demo mode. A second owner cannot be added this way.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: A person who cannot sign in has a missing or wrong hash, or a typo in the email.

## KNOWLEDGE_ADAPTER

- Required: optional
- What it does: Where company documents come from: `seed` (offline), `drive` or `notion`. A folder is read through KNOWLEDGE_DIR.
- How to get it:
  1. Leave `seed` for the demo.
  2. For Drive or Notion set the value and the token below.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
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
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: The doctor says which token is missing.

## EMAIL_ADAPTER

- Required: optional
- What it does: How reminders are sent: `seed` (drafted only) or `smtp`.
- How to get it:
  1. Leave `seed` until you are ready to send.
  2. For `smtp` fill the SMTP variables below.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: The doctor says SMTP_HOST or SMTP_USER is empty.

## WORKING_DAYS

- Required: optional
- What it does: The days counted as working days when due dates like next Friday are read. Decided default, a starting point the implementer changes per client.
- How to get it:
  1. Type the days, for example `Mon,Tue,Wed,Thu,Fri`.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Wrong days move a due date by a day or two.

## STUCK_NO_UPDATE_DAYS

- Required: optional
- What it does: Days without any update before an open task counts as silent. Default 10. Decided default, a starting point the implementer changes per client.
- How to get it:
  1. Pick a number that matches how often your team really updates tasks.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Too low and everything looks stuck.

## STUCK_BLOCKED_DAYS

- Required: optional
- What it does: Days a task may stay blocked before it is flagged. Default 5. Decided default, a starting point the implementer changes per client.
- How to get it:
  1. Pick a number.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Same as above.

## OVERLOAD_OPEN_TASKS

- Required: optional
- What it does: Open tasks per person before they are flagged as overloaded. Default 8. Decided default, a starting point the implementer changes per client.
- How to get it:
  1. Pick a number.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Same as above.

## OVERLOAD_DUE_SOON

- Required: optional
- What it does: Tasks due within 7 days per person before they are flagged. Default 5. Decided default, a starting point the implementer changes per client.
- How to get it:
  1. Pick a number.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Same as above.

## SOP_REVIEW_DAYS

- Required: optional
- What it does: Days after which a procedure with no review date counts as needing review. Default 180.
- How to get it:
  1. Pick a number.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Too low and every procedure looks stale.

## WEEKLY_REVIEW_WEEKDAY

- Required: optional
- What it does: The weekday the weekly review is built, 0 for Monday.
- How to get it:
  1. Pick 0 to 6.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
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
- Check it: `python3 tools/doctor.py --live`. A key that is not valid fails at start with plain words and never prints the key.
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
- Check it: `python3 tools/doctor.py --live`.
- If it is wrong: "invalid_grant" means the person revoked access or the token expired, and the consent must be repeated.

## DRIVE_TOKEN

- Required: optional, the third and weakest Drive sign in way
- What it does: One access token you paste. It expires after about an hour and cannot be renewed, so use it only to try Drive once.
- How to get it: Create one in Google's OAuth Playground or with your own consent flow, read only Drive scope.
- Cost: Free at normal use.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top. Only the API needs it.
- Check it: `python3 tools/doctor.py --live`.
- If it is wrong: Drive answers "refused the access" once the hour is over. Switch to the service account.

## DRIVE_SUBJECT, DRIVE_SCOPE, DRIVE_TOKEN_URI

- Required: optional
- What it does: `DRIVE_SUBJECT` is a user's email to act as when the Google Workspace admin has granted the service account domain wide delegation (leave empty otherwise). `DRIVE_SCOPE` defaults to the read only Drive scope; do not widen it. `DRIVE_TOKEN_URI` defaults to Google's token address and exists so tests can point at a local fake. It must be https and public.
- How to get it: Leave all three alone unless you know you need delegation.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py`.
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
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
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
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
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
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: An invalid key returns an error that Lorefern shows without the key.

## SMTP_HOST

- Required: required for `smtp`
- What it does: The mail server that sends reminders.
- How to get it:
  1. Ask your email provider for its SMTP host name (the provider's help page names it).
  2. Paste it as the value.
- Cost: Included in most email plans.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: `FAIL email/smtp` in the doctor with the error type.

## SMTP_PORT

- Required: optional
- What it does: The mail server port. Default 587 with TLS.
- How to get it:
  1. Use the port your provider names.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: A wrong port times out.

## SMTP_USER

- Required: required for `smtp`
- What it does: The mail account that sends the reminders.
- How to get it:
  1. Use a dedicated address such as reminders@yourcompany.test.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Login fails with an authentication error.

## SMTP_PASSWORD

- Required: required for `smtp`
- What it does: That account's password or app password.
- How to get it:
  1. Create an app password in the mail provider's security settings if it offers one.
  2. Paste it as the value. Never paste it in chat or in a file you commit.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Login fails with an authentication error.

## EMAIL_FROM

- Required: optional
- What it does: The From address on reminders.
- How to get it:
  1. Use an address you control.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Mail may be rejected if the domain is not set up for sending.

## API_BASE_URL

- Required: required on the web host
- What it does: Where the web app finds the API.
- How to get it:
  1. Local: `http://127.0.0.1:8000`.
  2. Hosted: your API address with no trailing slash, for example `https://api.example.com`.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: The web app shows a clear error when it cannot reach the API.

## INSECURE_COOKIES

- Required: demo only
- What it does: `1` lets the demo sign in over plain http on localhost. Never set it on a real site.
- How to get it:
  1. Set `1` only for local demos and the browser tests.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: On a real site a cookie without the secure flag is a risk.

## NEXT_PUBLIC_DEMO_HINT

- Required: demo only
- What it does: `1` shows the demo password hint on the sign in page.
- How to get it:
  1. Set `1` only for local demos.
- Cost: Free.
- Local, Vercel, Railway, Hetzner: see the paragraph at the top.
- Check it: `python3 tools/doctor.py` (add `--live` to test the real connection).
- If it is wrong: Leave it unset on a real site.
