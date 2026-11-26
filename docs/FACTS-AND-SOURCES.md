# Facts and sources

Anything marked UNVERIFIED must be checked against the vendor's current documentation before you depend on it. The seed company, people, documents and meetings are sample data.

| Fact | Source | Read on | Status |
| --- | --- | --- | --- |
| Fireflies: GraphQL endpoint `https://api.fireflies.ai/graphql`, key sent as a Bearer token, transcript fields `sentences` (speaker name, text, start time), `summary` action items, `date` | docs.fireflies.ai | 2026-11-23 | VERIFIED from the docs. Not run against Fireflies |
| Fathom: base `https://api.fathom.ai/external/v1`, key in the `X-Api-Key` header, `GET /meetings` with transcript and action items included on request | developers.fathom.ai | 2026-11-23 | VERIFIED from the docs. Not run against Fathom |
| Meetily: MIT licensed, runs locally, its free edition names no export format, Markdown, PDF and Word exports are in its paid edition | its GitHub repository | 2026-11-23 | VERIFIED from the repository text |
| Otter text export layout | Otter help page | 2026-11-23 | UNVERIFIED. The page refused the request, so the layout is assumed |
| Slack export folder layout (one folder per channel, one JSON file per day) | General knowledge | none | UNVERIFIED against a real export |
| Google service account sign in: signed RS256 assertion (claims iss, scope, aud, iat, exp up to one hour, optional sub), POST form `grant_type` `urn:ietf:params:oauth:grant-type:jwt-bearer` and `assertion` to `https://oauth2.googleapis.com/token`, answer `access_token` and `expires_in` | developers.google.com/identity/protocols/oauth2/service-account | 2026-11-23 | VERIFIED from the page. Not run against Google |
| Google refresh token grant: POST form `grant_type=refresh_token`, `client_id`, `client_secret`, `refresh_token` to the same address; `invalid_grant` when a token was revoked or expired | developers.google.com/identity/protocols/oauth2/web-server | 2026-11-23 | VERIFIED from the page. Not run against Google |
| Drive `files.list` paging (`pageToken`, `nextPageToken`, `pageSize` up to 1000, scope `drive.readonly`) and `files.export` (`GET /drive/v3/files/{id}/export?mimeType=`, 10 MB limit) | developers.google.com/workspace/drive/api/reference/rest/v3 | 2026-11-23 | VERIFIED from the pages. The `fields` parameter, the default fields and `alt=media` for plain text files were not on those pages: UNVERIFIED |
| Anthropic Messages API as used by the model path (`POST /v1/messages`, `x-api-key`, `anthropic-version`, JSON schema in `output_config.format`, models `claude-sonnet-5-5` and `claude-haiku-5-5`) | The shared base, from the vendor docs it read on 2026-11-23 | 2026-11-23 | UNVERIFIED live. Run only against a mock server on this machine and against recordings made by that mock server. Never run with a real key. See `facts/models.md` |
| Notion search request (`POST /v1/search`, `Notion-Version: 2026-03-11`, paging with `has_more` and `next_cursor`) | developers.notion.com/reference/post-search | 2026-11-23 | VERIFIED from the page text, not run. The blocks children endpoint was not read: UNVERIFIED |
| Vercel monorepo Root Directory steps | vercel.com/docs/monorepos (read for a sibling system) | 2026-11-23 | VERIFIED |
| Railway and Hetzner steps | Not read | none | UNVERIFIED |
| Vendor prices and free tiers | Not read | none | UNVERIFIED. No figures are quoted anywhere |
| Library versions (Next.js, React, TanStack Query, Playwright, FastAPI, SQLAlchemy and others) | Pinned by the shared base and its lock files | pinned at base 1.1.1 | Used as pinned. This system did not re check them against the registries |

More detail per vendor: `facts/models.md`, `facts/meetings.md`, `facts/knowledge-sources.md`, `facts/slack.md`.

## How the facts were used

- The Fireflies and Fathom adapters request only the fields listed above and are tested against `mock/meeting_mocks.py`, which imitates those shapes. If the real shape differs, the adapter's own healthcheck will say so before anything is read.
- Meetily and Otter text is handled by the same reader as any "Name: words" transcript. The Otter layout reader assumes a speaker name, a time and the words on the following lines.
