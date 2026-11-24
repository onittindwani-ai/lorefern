from fastapi.testclient import TestClient

from mock.meeting_mocks import FathomMock, FirefliesMock
from mock.source_mocks import DriveMock, NotionMock


def test_fireflies_needs_its_bearer_token():
    assert TestClient(FirefliesMock().app).post("/graphql", json={"query": "{ transcripts { id } }"}).status_code == 401


def test_fathom_pages_and_hides_the_transcript_unless_asked():
    m = FathomMock(page=1)
    m.meetings = [{"recording_id": 1, "title": "A", "created_at": "2026-11-02T10:00:00Z", "transcript": [{"speaker": {"display_name": "Ann"}, "text": "Hi", "timestamp": "00:00:01"}], "action_items": []}] * 2
    c = TestClient(m.app)
    h = {"X-Api-Key": m.token}
    first = c.get("/external/v1/meetings", headers=h).json()
    assert first["items"][0]["transcript"] is None and first["next_cursor"] == "1"
    second = c.get("/external/v1/meetings?cursor=1&include_transcript=true", headers=h).json()
    assert second["items"][0]["transcript"][0]["text"] == "Hi" and second["next_cursor"] is None


def test_drive_and_notion_mocks_refuse_a_wrong_token():
    assert TestClient(DriveMock().app).get("/drive/v3/files").status_code == 401
    assert TestClient(NotionMock().app).post("/v1/search").status_code == 401
