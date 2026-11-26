"""The tools the docs tell a person to run work (or say what is missing) with a plain `python3` on a fresh clone: the shared package is found without `make install`, and a missing library
is named in one line with the command that uses the project's own environment, never a traceback about `sendora_core`."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run_without_site_packages(tool: str) -> subprocess.CompletedProcess:
    """`-S` leaves out every installed package, as on a server that has nothing but Python."""
    return subprocess.run([sys.executable, "-S", f"tools/{tool}"], cwd=ROOT, capture_output=True, text=True, input="", timeout=60)


def test_hash_password_and_doctor_say_what_is_missing_instead_of_failing_on_the_shared_package():
    for tool in ("hash_password.py", "doctor.py"):
        r = run_without_site_packages(tool)
        assert r.returncode != 0
        assert "sendora_core" not in r.stderr and "Traceback" not in r.stderr, (tool, r.stderr)
        assert "A library is missing" in r.stderr and f".venv/bin/python tools/{tool}" in r.stderr, (tool, r.stderr)


def test_the_tool_path_helper_finds_the_shared_package_and_the_app_without_an_install():
    code = "import sys; sys.path.insert(0, 'tools'); import _common; print('\\n'.join(sys.path[:3]))"
    r = subprocess.run([sys.executable, "-S", "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    assert str(ROOT / "packages" / "core-py" / "src") in r.stdout and str(ROOT / "apps" / "api" / "src") in r.stdout
