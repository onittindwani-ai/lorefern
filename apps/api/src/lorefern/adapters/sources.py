"""Knowledge sources: Google Drive and Notion (tier B, read only, tested against mocks). The local folder and the site crawl live in ingest.py and crawler.py."""

from __future__ import annotations

import httpx

from lorefern.adapters.base import RemoteDoc, safe_base_url
from lorefern.adapters.drive_auth import DriveTokenProvider
from sendora_core.adapters import AdapterError


class DriveSource:
    """Google Drive, read only. Signs in with a service account or an OAuth refresh token and renews the access token itself (see drive_auth.py)."""

    MAX_PAGES = 50
    FIELDS = "nextPageToken,files(id,name,mimeType,modifiedTime)"

    def __init__(self, settings, client: httpx.Client | None = None, auth: DriveTokenProvider | None = None, token_client: httpx.Client | None = None):
        self.settings = settings
        self.auth = auth or DriveTokenProvider(settings, client=token_client)
        self.client = client or httpx.Client(base_url=safe_base_url(settings.drive_base_url), timeout=30)

    def _get(self, path: str, **params):
        """GET with the current token. A 401 renews the token once and tries once more."""
        for attempt in (0, 1):
            r = self.client.get(path, params=params or None, headers={"Authorization": f"Bearer {self.auth.token()}"})
            if r.status_code == 401 and attempt == 0 and self.auth.can_refresh:
                self.auth.invalidate()
                continue
            return r
        return r  # pragma: no cover

    def list_documents(self) -> list[RemoteDoc]:
        files, token = [], None
        for _ in range(self.MAX_PAGES):
            r = self._get("/drive/v3/files", fields=self.FIELDS, pageSize=100, **({"pageToken": token} if token else {}))
            if r.status_code in (401, 403):
                raise AdapterError("Google Drive refused the access. Check the sign in details, and that the files are shared with the service account or the consenting person (docs/03).")
            r.raise_for_status()
            body = r.json()
            files += body.get("files", [])
            token = body.get("nextPageToken")
            if not token:
                break
        out = []
        for f in files:
            mime = f["mimeType"]
            if mime.startswith("application/vnd.google-apps.document"):
                e = self._get(f"/drive/v3/files/{f['id']}/export", mimeType="text/plain")
            elif mime == "text/plain":
                e = self._get(f"/drive/v3/files/{f['id']}", alt="media")
            else:
                continue
            if e.status_code == 200:
                out.append(RemoteDoc(f["id"], f["name"], e.text, str(f.get("modifiedTime", ""))[:10]))
        return out

    def healthcheck(self):
        try:
            self.list_documents()
            return True, "Connected."
        except Exception as exc:
            return False, str(exc) if isinstance(exc, AdapterError) else f"Could not reach Drive: {type(exc).__name__}."


class NotionSource:
    VERSION = "2026-03-11"  # the value the search page of the Notion docs names as the only allowed one (read 2026-11-23). UNVERIFIED live.
    MAX_PAGES = 20

    def __init__(self, settings, client: httpx.Client | None = None):
        self.settings = settings
        if not settings.notion_token:
            raise AdapterError("NOTION_TOKEN is empty.")
        self.client = client or httpx.Client(base_url=safe_base_url(settings.notion_base_url), timeout=30)

    def _h(self):
        return {"Authorization": f"Bearer {self.settings.notion_token}", "Notion-Version": self.VERSION}

    def list_documents(self) -> list[RemoteDoc]:
        results, cursor = [], None
        for _ in range(self.MAX_PAGES):
            r = self.client.post("/v1/search", headers=self._h(), json={"filter": {"property": "object", "value": "page"}, "page_size": 100, **({"start_cursor": cursor} if cursor else {})})
            if r.status_code in (401, 403):
                raise AdapterError("Notion refused the token. Share the pages with the integration first.")
            r.raise_for_status()
            body = r.json()
            results += body.get("results", [])
            cursor = body.get("next_cursor") if body.get("has_more") else None
            if not cursor:
                break
        out = []
        for p in results:
            title = "".join(t.get("plain_text", "") for t in (p.get("properties", {}).get("title", {}) or {}).get("title", [])) or "Untitled"
            b = self.client.get(f"/v1/blocks/{p['id']}/children", headers=self._h())
            if b.status_code != 200:
                continue
            lines = ["".join(t.get("plain_text", "") for t in blk.get(blk["type"], {}).get("rich_text", [])) for blk in b.json().get("results", [])]
            out.append(RemoteDoc(p["id"], title, "\n\n".join(x for x in lines if x), str(p.get("last_edited_time", ""))[:10]))
        return out

    def healthcheck(self):
        try:
            self.list_documents()
            return True, "Connected."
        except Exception as exc:
            return False, str(exc) if isinstance(exc, AdapterError) else f"Could not reach Notion: {type(exc).__name__}."
