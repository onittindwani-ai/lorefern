"""Fake Fireflies and Fathom servers. Shapes follow the vendors' public docs read on 2026-11-23 (fields named in docs/facts/meetings.md). Never run against the real services: UNVERIFIED live."""

from __future__ import annotations

from fastapi import FastAPI, Header, Request
from fastapi.responses import JSONResponse


class FirefliesMock:
    def __init__(self, token="ff-mock-token"):
        self.token, self.transcripts = token, []  # each: {"id","title","date" (ms),"sentences":[{"speaker_name","text"}],"summary":{"action_items": str},"participants":[]}
        self.app = FastAPI()

        @self.app.post("/graphql")
        async def gql(request: Request, authorization: str | None = Header(default=None)):
            if authorization != f"Bearer {self.token}":
                return JSONResponse({"errors": [{"message": "Unauthorized", "code": "auth_failed"}]}, 401)
            body = await request.json()
            if "transcripts" not in body.get("query", ""):
                return {"errors": [{"message": "unknown query"}]}
            return {"data": {"transcripts": self.transcripts}}


class FathomMock:
    def __init__(self, token="fa-mock-token", page=2):
        self.token, self.meetings, self.page = token, [], page  # each: {"recording_id","title","created_at","transcript":[{"speaker":{"display_name"},"text","timestamp"}],"action_items":[{"description"}]}
        self.app = FastAPI()

        @self.app.get("/external/v1/meetings")
        def lst(cursor: str | None = None, include_transcript: bool = False, include_action_items: bool = False, x_api_key: str | None = Header(default=None)):
            if x_api_key != self.token:
                return JSONResponse({"error": "unauthorized"}, 401)
            start = int(cursor or 0)
            items = []
            for m in self.meetings[start:start + self.page]:
                m = dict(m)
                if not include_transcript:
                    m["transcript"] = None
                if not include_action_items:
                    m["action_items"] = None
                items.append(m)
            nxt = str(start + self.page) if start + self.page < len(self.meetings) else None
            return {"limit": self.page, "next_cursor": nxt, "items": items}
