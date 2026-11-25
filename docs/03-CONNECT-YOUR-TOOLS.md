# Connect your tools

Start with the company folder (doc 10). It needs no account and it is the best tested path. Add the rest one at a time.

| Source | How | Status |
| --- | --- | --- |
| Company folder (Markdown, text, PDF) | Set `KNOWLEDGE_DIR` to the folder. Press **Read again** on the Sources page. | Built and tested |
| Slack export (folder or zip) | Put the export under the seed or knowledge folder and map each channel to a visibility tag. | Built, tested on a made up export. The layout is UNVERIFIED against a real export |
| Google Drive | Add a source of kind Drive and put the folder ids (comma separated) in its path; an empty path reads everything the credential can reach, and only one source may do that. Trashed files are never read. `KNOWLEDGE_ADAPTER=drive` and a service account key (`DRIVE_SERVICE_ACCOUNT_JSON`) or a consent given once (`DRIVE_CLIENT_ID`, `DRIVE_CLIENT_SECRET`, `DRIVE_REFRESH_TOKEN`). Read only. Lorefern renews its own access token, so it keeps working past the first hour. | Sign in and renewal tested against a local fake token service and fake Drive only (UNVERIFIED against Google) |
| Notion | Add a source of kind Notion with page ids in its path (pages below them are read), or leave it empty for every shared page (one source). `KNOWLEDGE_ADAPTER=notion` and `NOTION_TOKEN`. Read only. | Tested against a local stand in only |
| Fireflies | `MEETINGS_ADAPTER=fireflies` and `FIREFLIES_TOKEN`. | Fields read from the vendor docs on 2026-11-23, tested against a stand in only |
| Fathom | `MEETINGS_ADAPTER=fathom` and `FATHOM_TOKEN`. | Fields read from the vendor docs on 2026-11-23, tested against a stand in only |
| Otter, Meetily, any recorder | Export the transcript as text and paste it on the Meetings page, or drop it in a folder. | Text layout UNVERIFIED |
| Email for reminders (SMTP) | `EMAIL_ADAPTER=smtp` and the `SMTP_` variables. Sending needs a second person's approval and is refused in draft mode. | Tested against a stand in only |

Steps for each variable, with the vendor page to open, are in `04-ENVIRONMENT-VARIABLES.md`. The Integrations page has a Test button for each adapter, and `python3 tools/doctor.py --live` tests them from a terminal.

## Google Drive: how the sign in works

Use this before any client's Drive is connected. An access token from Google lasts about an hour, so a single pasted token (`DRIVE_TOKEN`) is for a first try only. Two ways keep working:

1. **Service account (recommended for a company).** In the client's own Google Cloud project enable the Drive API, create a service account and a JSON key, and put the key's text in `DRIVE_SERVICE_ACCOUNT_JSON` (or its file path in `DRIVE_SERVICE_ACCOUNT_FILE`) in the host's secret settings. Share only the folders to be read with the service account's email address, as Viewer. It sees nothing else. Lorefern signs a short assertion with the key and trades it for an access token whenever the old one is about to expire.
2. **A consent given once.** Create an OAuth client, let the person consent once with the read only Drive scope to get a refresh token, and set `DRIVE_CLIENT_ID`, `DRIVE_CLIENT_SECRET` and `DRIVE_REFRESH_TOKEN`. Lorefern trades the refresh token for an access token when needed. This reads what that person can read, which is usually more than you want to show, so prefer the service account.

What the code does: it keeps the access token in memory, renews it two minutes before it expires, and if Drive answers 401 it renews once and tries once more. When Google refuses a renewal it says why in plain words (for example the key was disabled, or the person must consent again) and shows only Google's short error code, never a key or token. If the Google token service is down it says to try again and the next sync retries. Secrets come from environment variables only and are never printed or logged. A refresh token can stop working when the person revokes access or a company policy limits it, and then the consent must be repeated.

Written from Google's public documentation read on 2026-11-23 and tested against a local fake token service and a fake Drive. It has never been run against Google (UNVERIFIED). Run `python3 tools/doctor.py --live` once with the real settings before you rely on it.

## Read this before connecting Drive, Notion or Slack

Lorefern reads what its token can read, then applies **its own** visibility tags. It does not copy who may open each file in Drive, each page in Notion or each channel in Slack. Use a token or service account that can reach **only** the folders you want everyone with a given tag to see, and tag the source by the strictest rule that applies. See `13-SECURITY-AND-DATA.md`.

## A tool that is not listed

Use `prompts/04-recipes.md`. It has ready prompts for Claude Code or Codex that write a new reader, following the adapter pattern, with a local stand in and tests.
