# Slack export: what was assumed

The reader expects an export folder (or zip) with one folder per channel and one JSON file per day, each file a list of messages with a user, a time and text. This was written from general knowledge and tested on a sample export. It is **UNVERIFIED against a real export**.

- Only text of ordinary messages is read. Threads, files, reactions and edits are not rebuilt.
- Each channel is mapped to a visibility tag in a file named `slack_channels.json` next to the export. A channel not in the map takes the source's tag.
- A zip is read with guards: member size limits, no paths that leave the folder, and a limit on the number of files.
- Never import private channels or direct messages unless every member has said yes in writing.

## Contract test (2026-11-23)

`mock/contracts/slack_export` holds the message record and file names the Slack help page documents (channels.json, groups.json, dms.json, users.json, one folder per conversation, one file per date; message fields type, user, text, ts). The page does not give the day file name format, so `YYYY-MM-DD.json` stays UNVERIFIED, and direct messages and private channels are not read.
