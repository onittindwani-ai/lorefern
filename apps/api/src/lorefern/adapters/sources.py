"""Knowledge sources: Google Drive and Notion (tier B, read only, tested against mocks). The local folder and the site crawl live in ingest.py and crawler.py."""

from __future__ import annotations

import re

import httpx

from lorefern.adapters.base import RemoteDoc, RemoteDocs, safe_base_url
from lorefern.adapters.drive_auth import DriveTokenProvider
from sendora_core.adapters import AdapterError


FOLDER_MIME = "application/vnd.google-apps.folder"
ID_PATTERN = re.compile(r"[A-Za-z0-9_-]{6,128}")


class DriveSource:
    """Google Drive, read only. Signs in with a service account or an OAuth refresh token and renews the access token itself (see drive_auth.py)."""

    MAX_PAGES = 50
    MAX_FOLDERS = 200  # folders one read walks
    MAX_DEPTH = 6
    MAX_BYTES = 2_000_000  # a file larger than this is left out
    FIELDS = "nextPageToken,files(id,name,mimeType,modifiedTime)"

    def __init__(self, settings, client: httpx.Client | None = None, auth: DriveTokenProvider | None = None, token_client: httpx.Client | None = None):
        self.settings = settings
        self.auth = auth or DriveTokenProvider(settings, client=token_client)
        self.client = client or httpx.Client(base_url=safe_base_url(settings.drive_base_url), timeout=30)
        self._partial = False  # set when the current read left something unseen

    def _get(self, path: str, **params):
        """GET with the current token. A 401 renews the token once and tries once more."""
        for attempt in (0, 1):
            r = self.client.get(path, params=params or None, headers={"Authorization": f"Bearer {self.auth.token()}"})
            if r.status_code == 401 and attempt == 0 and self.auth.can_refresh:
                self.auth.invalidate()
                continue
            return r
        return r  # pragma: no cover

    def _read_bounded(self, path: str, **params) -> tuple[int, str | None]:
        """GET a file's text without ever holding more than MAX_BYTES of it. Returns (status, text), and text is None when the file is over the limit (decided from the header first, then while reading)."""
        for attempt in (0, 1):
            with self.client.stream("GET", path, params=params or None, headers={"Authorization": f"Bearer {self.auth.token()}"}) as r:
                if r.status_code == 401 and attempt == 0 and self.auth.can_refresh:
                    self.auth.invalidate()
                    continue
                if r.status_code != 200:
                    return r.status_code, ""
                declared = r.headers.get("content-length", "")
                if declared.isdigit() and int(declared) > self.MAX_BYTES:
                    return 200, None
                buf = bytearray()
                for chunk in r.iter_bytes():
                    buf += chunk
                    if len(buf) > self.MAX_BYTES:
                        return 200, None
                return 200, bytes(buf).decode(r.encoding or "utf-8", errors="replace")
        return 401, ""  # pragma: no cover

    def _list(self, query: str) -> list[dict]:
        files, token = [], None
        for _ in range(self.MAX_PAGES):
            r = self._get("/drive/v3/files", q=query, fields=self.FIELDS, pageSize=100, **({"pageToken": token} if token else {}))
            if r.status_code in (401, 403):
                raise AdapterError("Google Drive refused the access. Check the sign in details, and that the files are shared with the service account or the consenting person (docs/03).")
            r.raise_for_status()
            body = r.json()
            files += body.get("files", [])
            token = body.get("nextPageToken")
            if not token:
                break
        else:
            self._partial = True  # the page limit was reached with more pages left
        return files

    def _walk(self, folder_ids: list[str]) -> list[dict]:
        """The files inside the named folders and the folders below them. A trashed file is never listed."""
        files: dict[str, dict] = {}
        queue, seen = [(fid, 0) for fid in folder_ids], set(folder_ids)
        while queue and len(seen) <= self.MAX_FOLDERS:
            fid, depth = queue.pop(0)
            for f in self._list(f"'{fid}' in parents and trashed = false"):
                if f["mimeType"] == FOLDER_MIME:
                    if f["id"] in seen:
                        continue
                    if depth < self.MAX_DEPTH:
                        seen.add(f["id"])
                        queue.append((f["id"], depth + 1))
                    else:
                        self._partial = True  # a folder below the depth limit is never walked
                else:
                    files[f["id"]] = f
        if queue:
            self._partial = True  # the folder limit was reached with folders left
        return list(files.values())

    def list_documents(self, scope: list[str] | None = None) -> RemoteDocs:
        """Documents the credential can read, or only those inside the folders named in `scope` (folder ids). Trashed files are left out.
        The answer says (`complete`) whether the read saw everything: a page, folder or depth limit, or a file that could not be read (a rate limit, a server error), makes it incomplete."""
        self._partial = False
        if scope:
            bad = [x for x in scope if not ID_PATTERN.fullmatch(x)]
            if bad:
                raise AdapterError("A Drive folder id may only hold letters, digits, dashes and underscores. Check the path of this source.")
            files = self._walk(scope)
        else:
            files = self._list("trashed = false")
        out = RemoteDocs()
        for f in files:
            mime = f["mimeType"]
            if mime.startswith("application/vnd.google-apps.document"):
                status, text = self._read_bounded(f"/drive/v3/files/{f['id']}/export", mimeType="text/plain")
            elif mime == "text/plain":
                status, text = self._read_bounded(f"/drive/v3/files/{f['id']}", alt="media")
            else:
                continue  # a kind of file that is never read is not a failure
            if status != 200:
                self._partial = True  # the file is there but could not be read this time: its old copy must stay
                continue
            if text is not None:  # None: over the size limit, left out on purpose
                out.append(RemoteDoc(f["id"], f["name"], text, str(f.get("modifiedTime", ""))[:10]))
        out.complete = not self._partial
        return out

    def healthcheck(self):
        """One small request (a page of one file), never a read of the whole Drive."""
        try:
            r = self._get("/drive/v3/files", q="trashed = false", fields="files(id)", pageSize=1)
            if r.status_code in (401, 403):
                raise AdapterError("Google Drive refused the access. Check the sign in details, and that the files are shared with the service account or the consenting person (docs/03).")
            r.raise_for_status()
            return True, "Connected."
        except Exception as exc:
            return False, str(exc) if isinstance(exc, AdapterError) else f"Could not reach Drive: {type(exc).__name__}."


class NotionSource:
    MAX_BLOCK_PAGES = 20  # block pages of 100 read for one page
    VERSION = "2026-03-11"  # the value the search page of the Notion docs names as the only allowed one (read 2026-11-23). UNVERIFIED live.
    MAX_PAGES = 20

    def __init__(self, settings, client: httpx.Client | None = None):
        self.settings = settings
        if not settings.notion_token:
            raise AdapterError("NOTION_TOKEN is empty.")
        self.client = client or httpx.Client(base_url=safe_base_url(settings.notion_base_url), timeout=30)

    def _h(self):
        return {"Authorization": f"Bearer {self.settings.notion_token}", "Notion-Version": self.VERSION}

    def _blocks(self, page_id: str) -> tuple[list[str] | None, bool]:
        """The text lines of one page, following the block pages up to MAX_BLOCK_PAGES. Returns (lines, ok): not ok when a request failed or the page is longer than the limit."""
        lines: list[str] = []
        cursor = None
        for _ in range(self.MAX_BLOCK_PAGES):
            b = self.client.get(f"/v1/blocks/{page_id}/children", headers=self._h(), params={"page_size": 100, **({"start_cursor": cursor} if cursor else {})})
            if b.status_code != 200:
                return None, False
            body = b.json()
            lines += ["".join(t.get("plain_text", "") for t in blk.get(blk["type"], {}).get("rich_text", [])) for blk in body.get("results", [])]
            cursor = body.get("next_cursor") if body.get("has_more") else None
            if not cursor:
                return lines, True
        return None, False

    def list_documents(self, scope: list[str] | None = None) -> RemoteDocs:
        """Pages the integration can read, or only the pages named in `scope` and the pages directly below them. `complete` is False when a page limit was reached or a page could not be read."""
        results, cursor, partial = [], None, False
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
        else:
            partial = True  # the search page limit was reached with more pages left
        if scope:
            wanted = {x.replace("-", "").lower() for x in scope}
            results = [p for p in results if p["id"].replace("-", "").lower() in wanted or str((p.get("parent") or {}).get("page_id", "")).replace("-", "").lower() in wanted]
        out = RemoteDocs()
        for p in results:
            title = "".join(t.get("plain_text", "") for t in (p.get("properties", {}).get("title", {}) or {}).get("title", [])) or "Untitled"
            lines, ok = self._blocks(p["id"])
            if not ok or lines is None:
                partial = True  # a page that could not be read in full keeps its old copy, and nothing is removed
                continue
            out.append(RemoteDoc(p["id"], title, "\n\n".join(x for x in lines if x), str(p.get("last_edited_time", ""))[:10]))
        out.complete = not partial
        return out

    def healthcheck(self):
        """One small request (a search page of one page), never a read of every page."""
        try:
            r = self.client.post("/v1/search", headers=self._h(), json={"filter": {"property": "object", "value": "page"}, "page_size": 1})
            if r.status_code in (401, 403):
                raise AdapterError("Notion refused the token. Share the pages with the integration first.")
            r.raise_for_status()
            return True, "Connected."
        except Exception as exc:
            return False, str(exc) if isinstance(exc, AdapterError) else f"Could not reach Notion: {type(exc).__name__}."
