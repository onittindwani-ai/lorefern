"""Record the model answers for the seed world into data/llm_fixtures/, so the demo can replay them with LLM_BACKEND=fixture and no account.

IMPORTANT: these are NOT answers of a real model. The recording goes through the real anthropic code path (request building, schema, response parsing, the checks by code)
against a local fake server that answers with the offline stand in. So the fixtures prove the replay path and the request shape, not model quality. Replace them with a
recording from a real key (LLM_RECORD=true, LLM_BACKEND=anthropic) when you have one. Never commit recordings made from real company data.

What is recorded: the meeting reader (MEETING_EXTRACTOR=model), the process names (PROCESS_WORDING=model), the review intro (REVIEW_WRITER=model) and the answer writer for the
first questions of the development set. Replay with the same three settings.

Run: python tools/record_llm_fixtures.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "apps" / "api" / "src"))
sys.path.insert(0, str(ROOT))

from lorefern import demo, qa  # noqa: E402
from lorefern.config import Settings  # noqa: E402
from lorefern.context import Ctx  # noqa: E402
from lorefern.offline_llm import OfflineBackend  # noqa: E402
from mock.anthropic_mock import FakeAnthropic  # noqa: E402
from sendora_core import models as _core  # noqa: E402,F401
from sendora_core.db import Base, make_engine, make_session_factory  # noqa: E402
from sendora_core.llm import reset_budgets  # noqa: E402

OUT = ROOT / "data" / "llm_fixtures"
MODEL_SETTINGS = {"meeting_extractor": "model", "process_wording": "model", "review_writer": "model"}
QUESTIONS = 12


def stand_in(body: dict) -> str:
    return OfflineBackend().complete(model=body["model"], system=body.get("system", ""), prompt=body["messages"][0]["content"], max_tokens=body["max_tokens"]).text


def replay_settings(tmp: str, fixtures: Path, **kw) -> Settings:
    return Settings(database_url=f"sqlite:///{tmp}/rep.sqlite3", session_secret="record-secret-record-secret", seed_dir=str(ROOT / "data"), llm_backend="fixture", llm_fixtures_dir=str(fixtures),
                    anthropic_api_key=None, _env_file=None, **MODEL_SETTINGS, **kw)


def record(out: Path = OUT, work: Path | None = None) -> dict:
    out = Path(out)
    if out.exists():
        shutil.rmtree(out)
    if work is not None:
        Path(work).mkdir(parents=True, exist_ok=True)
    qs = json.loads((ROOT / "data/eval/dev_questions.json").read_text())["questions"][:QUESTIONS]
    with tempfile.TemporaryDirectory(dir=work) as tmp, FakeAnthropic(stand_in) as fake:
        settings = Settings(database_url=f"sqlite:///{tmp}/rec.sqlite3", session_secret="record-secret-record-secret", seed_dir=str(ROOT / "data"), llm_backend="anthropic",
                            anthropic_api_key="fake-key-for-local-server", anthropic_base_url=fake.url, llm_record=True, llm_fixtures_dir=str(out), _env_file=None, **MODEL_SETTINGS)
        eng = make_engine(settings.database_url)
        Base.metadata.create_all(eng)
        ctx = Ctx(settings, make_session_factory(eng))
        reset_budgets()
        with ctx.factory() as s:
            info = demo.reset(s, ctx)
            for q in qs:
                qa.ask(s, ctx, q["question"], q["audience"])
            s.commit()
    files = len(list(out.glob("*.json")))
    (out / "README.txt").write_text(
        "Recorded from a LOCAL FAKE server that answers with the offline stand in. Not answers of a real model.\n"
        "They prove the replay path and the request shape only. Replay with LLM_BACKEND=fixture LLM_FIXTURES_DIR=data/llm_fixtures MEETING_EXTRACTOR=model PROCESS_WORDING=model REVIEW_WRITER=model.\n"
        "Regenerate: python tools/record_llm_fixtures.py\n", encoding="utf-8")
    return {"documents": info["seed"]["documents"], "questions": len(qs), "files": files, "requests_to_fake_server": len(fake.requests)}


if __name__ == "__main__":
    print(json.dumps(record()))
