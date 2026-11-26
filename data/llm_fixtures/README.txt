Recorded from a LOCAL MOCK server that answers with the offline stand in. Not answers of a real model.
They prove the replay path and the request shape only. Replay with LLM_BACKEND=fixture LLM_FIXTURES_DIR=data/llm_fixtures MEETING_EXTRACTOR=model PROCESS_WORDING=model REVIEW_WRITER=model.
Regenerate: python tools/record_llm_fixtures.py
