# Security

## Built in

- **Visibility:** every document, passage, meeting, task, decision and review has one tag. The filter runs inside every query. A restricted item answers "not found" exactly like a missing one. A source with a stricter tag fixes the tag of everything in it, and a missing or unknown tag becomes `people` (owner only), never `company`. A document's own tag, its folder's tag and the source's tag are combined and the narrowest wins. Deleted or unshared documents leave the index on the next read.
- **A preview can narrow, never widen,** and cannot change anything.
- **Content is data.** Instruction like lines in a transcript or a document are flagged and never become tasks, decisions or answer text.
- **Proposals need a person.** Nothing becomes a task without an owner or leadership approval.
- **Sending needs two people.** Reminders are drafted. A different person approves. Execution is idempotent and blocked in draft mode and by the kill switch. The requester cannot approve their own request.
- **Fetch guard:** outbound requests refuse private and local addresses.
- **Files:** the folder reader skips links that leave the folder, files over 10 MB and damaged PDFs. The Slack zip reader limits member sizes and refuses paths that leave the folder. Source paths must be inside `KNOWLEDGE_DIR`.
- **Login:** password hashes only, rate limited, cookie flags set, a required header on every change so another site cannot make the browser change data.
- **Audit log** with a hash chain. **Kill switch.** No webhooks are exposed.
- Secrets are read from the environment and never printed. `tools/scan_secrets.py` runs in CI.

## Checked

`pip-audit` (on the installed Python packages) and `pnpm audit` found no known vulnerabilities on 2026-11-23. The secret scan found nothing. The migration cycle (up, down, up) passed on a throwaway local Postgres 17 as well as on SQLite.

Tests cover the visibility boundary for four audiences (search, lists, counts, evidence lines, reviews, trees, direct links), injection lines in transcripts and documents, self approval refusal, path guards, sign in, and the migration cycle. See `data/counts.json` for the counts. A real leak was found by these tests during the build (the folder index listed restricted titles) and fixed.

## Not tested or not done

- **Per user source permissions are not mirrored.** Tags are the only rule. Read `docs/13-SECURITY-AND-DATA.md`.
- **Single tenant.** One company per install.
- No penetration test. No real vendor was contacted.
- CI builds the Docker images and starts the compose stack on GitHub. The deploy files were not run on a real host.
- Rate limits are per process. Behind several processes they are not shared.
- The injection detector is a list of patterns. Safety does not rest on it alone, because nothing can become a task or decision without a person.
- If you connect a language model later, document text and questions go to that vendor.

## Report a problem

Use the repository's **Security** tab, then **Report a vulnerability**, which is private. We aim to acknowledge within 5 working days. Do not post keys or company documents in a public issue.

## Two risks to know

- **Demo mode.** `DEMO_MODE=true` with no owner password hash switches on a public demo password, example accounts and a route that wipes the database. The app refuses to start with that on a server database, and refuses `DEMO_MODE=false` with an example secret. Never run a demo on a real company's documents.
- **Secrets.** `SESSION_SECRET`, password hashes, the Drive key, tokens and the SMTP password live only in the environment. Use a random `SESSION_SECRET` of 32 or more characters, rotate anything that was ever pasted into a chat or a ticket, and never commit a `.env` file.
