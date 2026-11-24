import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

from lorefern import folder_tool

ROOT = Path(__file__).resolve().parents[3]
TEMPLATE = ROOT / "templates/company-folder"


def codes(rep):
    return {f.code for f in rep.findings}


def test_the_shipped_template_passes_its_own_check():
    rep = folder_tool.check(TEMPLATE, date.today())
    assert rep.ok and rep.documents >= 20, [f for f in rep.findings if f.severity == "error"]


def test_the_template_has_twelve_numbered_folders_each_with_a_readme_owner_and_cadence():
    names = sorted(p.name for p in TEMPLATE.iterdir() if p.is_dir())
    assert len(names) == 12 and names[0] == "00 Governance" and names[-1] == "11 Templates"
    for n in names:
        txt = (TEMPLATE / n / "README.md").read_text()
        assert "owner:" in txt and "## What belongs here" in txt and "## How often it is reviewed" in txt and "## Who owns it" in txt
    for need in ("INDEX.md", "SOURCE-REGISTER.md", "OWNERS-AND-REVIEW-CADENCE.md", "11 Templates/sop-template.md", "11 Templates/decision-record-template.md", "11 Templates/meeting-note-template.md", "11 Templates/client-brief-template.md"):
        assert (TEMPLATE / need).exists(), need


def test_examples_are_labelled_fictional():
    ex = list(TEMPLATE.rglob("EXAMPLE-*.md"))
    assert len(ex) == 4 and all("Fictional example" in p.read_text() for p in ex)


def test_instantiate_fills_the_company_and_owner_and_refuses_a_used_folder(tmp_path):
    out = tmp_path / "acme"
    folder_tool.instantiate(TEMPLATE, out, "Acme Studio", "Pat Lee", date(2027, 6, 1))
    assert "{{" not in "".join(p.read_text() for p in out.rglob("*.md"))
    assert "Pat Lee" in (out / "00 Governance/README.md").read_text()
    assert folder_tool.check(out, date(2027, 6, 2)).ok
    try:
        folder_tool.instantiate(TEMPLATE, out, "Acme", "Pat")
        raise AssertionError("should refuse")
    except FileExistsError:
        pass


def test_a_copy_made_later_is_not_born_overdue(tmp_path):
    out = tmp_path / "later"
    folder_tool.instantiate(TEMPLATE, out, "Acme", "Pat", date(2030, 1, 1))
    assert not [f for f in folder_tool.check(out, date(2030, 1, 2)).findings if f.code == "review_overdue"]


def _copy(tmp_path):
    out = tmp_path / "f"
    shutil.copytree(TEMPLATE, out)
    return out


def test_negative_controls_each_problem_is_caught(tmp_path):
    f = _copy(tmp_path)
    (f / "03 Clients and Customers/README.md").unlink()
    assert "readme_missing" in codes(folder_tool.check(f))
    f = _copy(tmp_path / "b")
    p = f / "04 Revenue/README.md"
    p.write_text(p.read_text().replace("owner:", "ownr:"))
    assert "folder_owner_missing" in codes(folder_tool.check(f))
    f = _copy(tmp_path / "c")
    (f / "09 Marketing/new-doc.md").write_text("---\nowner: Ann\nreview_by: 2030-01-01\nvisibility: company\n---\n# New\n\nbody\n")
    assert "not_in_index" in codes(folder_tool.check(f))
    f = _copy(tmp_path / "d")
    (f / "09 Marketing/x.md").write_text("---\nowner: Ann\nreview_by: 2020-01-01\nvisibility: company\n---\n# X\n\nSee [missing](nope.md).\n")
    folder_tool.reindex(f, "T", date(2026, 1, 1))
    c = codes(folder_tool.check(f, date(2026, 6, 1)))
    assert {"broken_link", "review_overdue"} <= c
    f = _copy(tmp_path / "e")
    (f / "09 Marketing/y.md").write_text("---\nvisibility: secret\n---\n# Y\n\nbody\n")
    folder_tool.reindex(f, "T", date(2026, 1, 1))
    assert {"bad_tag", "owner_missing", "review_missing"} <= codes(folder_tool.check(f))
    f = _copy(tmp_path / "g")
    (f / "INDEX.md").unlink()
    assert "index_missing" in codes(folder_tool.check(f))


def test_reindex_fixes_the_index(tmp_path):
    f = _copy(tmp_path)
    (f / "09 Marketing/z.md").write_text("---\nowner: Ann\nreview_by: 2031-01-01\nvisibility: company\n---\n# Z\n\nbody\n")
    folder_tool.reindex(f, "T", date(2026, 1, 1))
    assert "not_in_index" not in codes(folder_tool.check(f, date(2026, 1, 2)))


def test_the_command_line_tools_run(tmp_path):
    out = tmp_path / "cli"
    r = subprocess.run([sys.executable, str(ROOT / "tools/new_company_folder.py"), str(out), "--name", "Acme Studio", "--owner", "Pat Lee"], capture_output=True, text=True)
    assert r.returncode == 0 and "Created" in r.stdout
    assert subprocess.run([sys.executable, str(ROOT / "tools/new_company_folder.py"), str(out), "--name", "Acme"], capture_output=True, text=True).returncode == 2
    c = subprocess.run([sys.executable, str(ROOT / "tools/check_company_folder.py"), str(out), "--json"], capture_output=True, text=True)
    assert c.returncode == 0 and '"ok": true' in c.stdout
    (out / "00 Governance/README.md").unlink()
    assert subprocess.run([sys.executable, str(ROOT / "tools/check_company_folder.py"), str(out)], capture_output=True, text=True).returncode == 1


def test_the_demo_company_folder_has_the_planted_review_problems():
    rep = folder_tool.check(ROOT / "data/seed/company", date(2026, 12, 1))
    assert rep.ok and {f.path for f in rep.findings if f.code == "review_overdue"} == {"05 Operations/weekly-client-report-sop.md", "06 Product and Engineering/release-process-sop.md", "08 People/onboarding-a-new-hire-sop.md"}
