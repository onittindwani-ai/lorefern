"""The web app never reads SESSION_SECRET, so no Vercel or web variable list may ask for it (round 4): the docs check finds such a line, and the files in this repo have none."""

import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("check_docs", ROOT / "tools" / "check_docs.py")
check_docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check_docs)


def test_the_check_finds_the_old_wording():
    old = "Vercel needs no file from this repo. Follow `docs/06-DEPLOY-VERCEL.md`: set the Root Directory to `apps/web` and set `API_BASE_URL` and `SESSION_SECRET`."
    assert check_docs.session_secret_on_web(old)
    assert check_docs.session_secret_on_web("- Integration depth (75): Needs API_BASE_URL and SESSION_SECRET. Not deployed.")
    assert check_docs.session_secret_on_web("In the Vercel project variables add SESSION_SECRET.")


def test_the_check_accepts_a_line_that_says_not_to_set_it():
    assert not check_docs.session_secret_on_web("Set nothing else: the web app never reads `SESSION_SECRET`, so never put it on Vercel.")
    assert not check_docs.session_secret_on_web("Set `SESSION_SECRET` (32 or more random characters) in the API service Variables tab.")


def test_no_file_of_this_repo_puts_the_session_secret_on_the_web_host():
    files = [*ROOT.glob("*.md"), *(ROOT / "docs").rglob("*.md"), *(ROOT / "deploy").rglob("*.md"), ROOT / "data" / "tool_scores.json", ROOT / "apps" / "web" / "next.config.ts"]
    for f in files:
        assert check_docs.session_secret_on_web(f.read_text(encoding="utf-8")) == [], f
    scores = json.loads((ROOT / "data" / "tool_scores.json").read_text(encoding="utf-8"))
    assert "SESSION_SECRET" not in json.dumps(scores).replace("never reads", "")  # the evidence lines name no signing key at all
