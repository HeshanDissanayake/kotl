"""M0: the status tooling refuses bad commits and turns tested features green."""
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
pytestmark = pytest.mark.feature("tooling")


def run(cwd, *args, check=True):
    return subprocess.run(args, cwd=cwd, capture_output=True, text=True, check=check)


@pytest.fixture
def repo(tmp_path):
    """A throwaway git repo with the shipped tooling and the hook enabled."""
    for rel in ("tools/status.py", ".githooks/pre-commit",
                "docs/architecture/architecture.json", "docs/architecture/status.json"):
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / rel, tmp_path / rel)
    run(tmp_path, "git", "init", "-q")
    run(tmp_path, "git", "config", "user.email", "test@example.invalid")
    run(tmp_path, "git", "config", "user.name", "test")
    run(tmp_path, "git", "config", "core.hooksPath", ".githooks")
    run(tmp_path, "git", "add", "-A")
    run(tmp_path, "git", "commit", "-q", "-m", "base")
    return tmp_path


def commit(repo, *paths):
    run(repo, "git", "add", *paths)
    return run(repo, "git", "commit", "-q", "-m", "change", check=False)


def test_check_passes_on_this_repo():
    r = run(ROOT, sys.executable, "tools/status.py", "check", check=False)
    assert r.returncode == 0, r.stdout


def test_code_change_without_status_is_refused(repo):
    (repo / "tools/status.py").write_text((repo / "tools/status.py").read_text() + "\n# edit\n")
    r = commit(repo, "tools/status.py")
    assert r.returncode != 0
    assert "status.json isn't staged" in r.stdout + r.stderr


def test_code_change_with_status_is_accepted(repo):
    (repo / "tools/status.py").write_text((repo / "tools/status.py").read_text() + "\n# edit\n")
    st = json.loads((repo / "docs/architecture/status.json").read_text())
    st["features"]["tooling"]["log"].append({"date": "2026-11-21", "text": "edit"})
    (repo / "docs/architecture/status.json").write_text(json.dumps(st, indent=2))
    r = commit(repo, "tools/status.py", "docs/architecture/status.json")
    assert r.returncode == 0, r.stdout


def test_unowned_file_is_refused(repo):
    (repo / "kotl").mkdir()
    (repo / "kotl/orphan.py").write_text("x = 1\n")
    r = commit(repo, "kotl/orphan.py", "docs/architecture/status.json")
    assert r.returncode != 0
    assert "'kotl/orphan.py' belongs to no feature" in r.stdout + r.stderr


def test_init_files_need_no_owner(repo):
    (repo / "kotl").mkdir()
    (repo / "kotl/__init__.py").write_text("")
    assert commit(repo, "kotl/__init__.py").returncode == 0


def _refresh(repo, feature, status, outcome):
    st_path = repo / "docs/architecture/status.json"
    st = json.loads(st_path.read_text())
    st["features"][feature]["status"] = status
    st_path.write_text(json.dumps(st))
    results = repo / "results.json"
    results.write_text(json.dumps({"ran_at": "2026-11-21T00:00:00Z", "results": [
        {"nodeid": "t::a", "features": [feature], "hw": False, "outcome": outcome}]}))
    run(repo, sys.executable, "tools/status.py", "refresh", "--results", str(results), "--no-git")
    return json.loads(st_path.read_text())["features"][feature]


def test_refresh_turns_built_feature_tested(repo):
    f = _refresh(repo, "registry", "built", "passed")
    assert f["status"] == "tested"
    assert f["tests"]["unit"]["passed"] == 1


def test_refresh_marks_failing(repo):
    assert _refresh(repo, "registry", "built", "failed")["status"] == "failing"


def test_refresh_leaves_in_progress_alone(repo):
    assert _refresh(repo, "registry", "in_progress", "passed")["status"] == "in_progress"


def test_agent_cannot_claim_tested(repo):
    st_path = repo / "docs/architecture/status.json"
    st = json.loads(st_path.read_text())
    st["features"]["registry"]["status"] = "tested"
    st_path.write_text(json.dumps(st))
    r = run(repo, sys.executable, "tools/status.py", "check", check=False)
    assert r.returncode != 0 and "only 'refresh' may set that" in r.stdout + r.stderr
