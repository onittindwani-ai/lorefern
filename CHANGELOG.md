# Changelog

## 1.0.1 (2026-11-25)

Security and install hardening. No new screens, but every read and write path is stricter.

- **Visibility.** A document, transcript or file with no tag, or an unknown one, is now owner only instead of company wide. A document's own header, its folder's tag and the source's tag are combined and the narrowest wins. Meeting transcripts now read their own `Visibility` header. A retag can no longer widen a row, and it clears reviews, process evidence and stored answers that may quote what became restricted.
- **Deleted and unshared documents leave the index.** A finished read removes what it no longer sees. One bad file no longer stops a read. Folder sources read only their own folder; Drive and Notion sources read only the folders or pages in their path, and never trashed files.
- **Change routes** check the record's tag first and answer 404 like a missing record. The integrations page, settings, audit log and event payloads no longer show what a person may not see.
- **Demo shortcuts.** The demo password, the example accounts and the reset route work only in a real demo (no owner hash), and the reset refuses while a real source exists.
- **Sign in.** One cleaned email for the throttle and the lookup, a limit per address and per account, unknown accounts cost the same time as known ones.
- **Install.** Alembic and the worker read the same settings as the API. The app and the worker refuse an example secret, a placeholder company name or sender on a live install, and plain text mail to another host. Mail uses verified TLS. Company name, sender and time zone are settings. `.env.example` lists every setting and a test keeps the docs in step. The backup script copies the knowledge volume and refuses an empty dump. Docker compose pins Postgres, and the web service has a health check.
- **Web.** An error page and a not found page. The Sources page sets what untagged documents get, and the meeting import asks for a tag.
- **Docs.** Windows (WSL 2) and Ubuntu notes, the Docker prerequisites, honest CI wording, a private way to report a vulnerability.

## Unreleased

- Renamed from Cortex to Lorefern after a public name check. The Python package, environment variable prefix, interface text, documents, prompts, templates and screenshots all use the new name.

- The kill switch now stops changes and the background jobs, not only sends. Setting a source back to company restores the tags it had, and restricting the meetings source also hides the tasks and decisions found in them. The Slack and folder sources read their own path. A repeat import or a second decision on the same item is refused. Reminder drafts have a screen with an Ask to send button. Write controls follow the role, leader pages explain themselves, the phone top bar keeps Pause all and Sign out, the palette moves with the arrow keys and can run jobs, reset the demo and pause. The audit log uses plain words. Sign in returns to the page asked for. Details: round 5 test report.

## 1.0.0

First release. Cited answers with a groundedness check, a hard visibility boundary (five tags, four audiences), meetings turned into proposed tasks and decisions with exact quotes (a person approves each), reminders through a two person approval, stuck work detection, an SOP coverage map, a weekly review where every line links to a record, a decision log, the company folder template with a creator and a checker, folder, Slack export, Drive, Notion, Fireflies, Fathom and SMTP adapters (the vendor ones tested against local imitations only), an ask bar on every page, eleven pages, and guides 00 to 15.
