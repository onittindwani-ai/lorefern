# Drive and Notion: what was and was not read

The Google sign in and the Drive paging and export calls were checked against Google's public pages on 2026-11-23 (see `FACTS-AND-SOURCES.md` for what each page did and did not say). Notion was not read from vendor pages. All adapters are tested only against `mock/source_mocks.py`.

- **Google Drive:** the adapter lists files in a folder and reads Google Docs as plain text, and ordinary text files. It signs in with a service account key or an OAuth refresh token, keeps the access token in memory, renews it before it expires and once after a refused request (`adapters/drive_auth.py`, doc 03). The fake token service in `mock/source_mocks.py` checks the signature, issuer, audience, scope and lifetime of the assertion, and the tests move a fake clock past the expiry.
- **Notion:** the adapter searches pages the integration can see and reads their blocks as plain text. It reads only pages shared with the integration.
- **Permissions:** neither adapter reads or copies who may open a file or page. See `13-SECURITY-AND-DATA.md`.

## Contract tests (2026-11-23)

`mock/contracts/google_drive` holds the documented service account and refresh token request shapes (endpoint, form fields, RS256 header, claims, one hour limit, response fields) and `mock/tests/test_contracts.py` asserts the adapter sends exactly those (the assertion signature is verified with the public key). The Drive files.list and files.export parameters stay UNVERIFIED there. `mock/contracts/notion`: the search page names `Notion-Version: 2026-03-11` as the only allowed value, and returns `has_more` and `next_cursor`; the adapter sent an older version and read only the first page, both fixed. The blocks children endpoint was not fetched (UNVERIFIED). No machine readable spec was available for either vendor.

Check each request shape against the vendor's current developer docs before the first real run, and run `.venv/bin/python tools/doctor.py --live`.
