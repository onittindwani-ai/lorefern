# Meeting recorders: what was read

Read on 2026-11-23 from the vendors' own pages. Nothing was run against a real account.

## Fireflies (VERIFIED from docs, not run)

- Endpoint: `https://api.fireflies.ai/graphql`. Header `Authorization: Bearer <key>`.
- Transcript fields Lorefern asks for: `id`, `title`, `date`, `participants`, `sentences { speaker_name text }` (the docs also list a start time, which Lorefern does not use) and `summary { action_items }`.
- Fireflies' own action items are kept for comparison only. They never become tasks. Lorefern reads the transcript itself, so every task has a quote.
- The key comes from the account's integrations settings (doc 04).

## Fathom (VERIFIED from docs, not run)

- Base URL `https://api.fathom.ai/external/v1`. Header `X-Api-Key: <key>`.
- `GET /meetings` accepts options to include the transcript and the action items.
- Same rule: its action items are compared, never turned into tasks.

## Contract tests (2026-11-23)

`mock/contracts/fireflies` and `mock/contracts/fathom` hold the fields and the example read from the vendors' pages; `mock/tests/test_contracts.py` asserts the requests (endpoint, auth header, requested fields, query parameters, cursor paging) and the parsing of the documented example. No machine readable schema exists on either page. The Fireflies page does not say what type the output `date` has; the adapter reads digits as milliseconds (UNVERIFIED). Fathom's transcript field is not available to OAuth connected apps (they use `/recordings`), which this adapter does not support (it uses an API key).

## Otter (UNVERIFIED)

- The export help page refused the request (HTTP 403), so no layout was read. Lorefern has a reader for lines shaped like a speaker name and a time followed by words, and for plain "Name: words" lines. Test it on a real export before you promise anything.

## Meetily (VERIFIED from its repository)

- Open source, MIT licensed, local transcription. The free edition names no export format. Markdown, PDF and Word exports belong to its paid edition. Use its transcript as text, pasted or saved as a file.
