"""The kotl command, with a fake Slurm and no launcher."""
import pytest

from kotl import slurm
from kotl.cli import main as cli

from .fakes import FakeSlurm

pytestmark = pytest.mark.feature("cli")


@pytest.fixture
def fs(monkeypatch):
    # the live Kotl daemon's file must not leak into these tests: they test asking directly
    from kotl.core import daemon
    monkeypatch.setattr(daemon, "read_status", lambda *a, **k: None)
    f = FakeSlurm()
    for name in ("submit", "cancel", "state", "queue", "job_info"):
        monkeypatch.setattr(slurm, name, getattr(f, name))
    return f


def test_eta_is_required(fs, capsys):
    with pytest.raises(SystemExit) as e:
        cli.main(["run", "--", "true"])
    assert e.value.code == 2 and "--eta" in capsys.readouterr().err


def test_run_submits_with_license_and_guards(fs, monkeypatch):
    monkeypatch.setenv("KOTL_JOB_SH", "/opt/kotl/job.sh")
    assert cli.main(["run", "--eta", "90s", "--max", "10m", "--idle", "2m", "--no-wait", "--", "./t.sh", "a b"]) == 0
    s = fs.submitted[0]
    assert s["script"] == "/opt/kotl/job.sh" and s["args"] == ["./t.sh", "a b"]
    assert s["license"] == "vcu118:1" and s["minutes"] == 2 and s["name"] == "kotl-run"
    assert s["env"] == {"KOTL_MODE": "run", "KOTL_MAX": 600, "KOTL_IDLE": 120}


def test_run_needs_a_command(fs, capsys):
    with pytest.raises(SystemExit):
        cli.main(["run", "--eta", "5m"])


def test_bad_eta(fs, capsys):
    with pytest.raises(SystemExit):
        cli.main(["run", "--eta", "soon", "--", "true"])
    assert "can't read duration" in capsys.readouterr().err


def test_lease_holds_with_sleep(fs, monkeypatch):
    monkeypatch.setattr(cli, "wait_running", lambda job: True)
    monkeypatch.setattr(cli, "job_status", lambda job: {"board": "vcu118-pc1"})
    assert cli.main(["lease", "--eta", "1h"]) == 0
    s = fs.submitted[0]
    assert s["args"] == ["sleep", "infinity"] and s["name"] == "kotl-lease" and s["minutes"] == 60
    assert s["env"]["KOTL_MODE"] == "lease"


def test_release_only_my_leases(fs, monkeypatch):
    import pwd, os
    me = pwd.getpwuid(os.getuid()).pw_name
    fs.add(1, me, name="kotl-lease"); fs.add(2, "someone-else", name="kotl-lease"); fs.add(3, me, name="kotl-run")
    assert cli.main(["release"]) == 0
    assert fs.cancelled == [1]


def test_release_without_lease(fs, capsys):
    with pytest.raises(SystemExit):
        cli.main(["release"])
    assert "no lease" in capsys.readouterr().err


def test_fast_job_counts_as_started(fs, monkeypatch):
    # the job came and went between two looks at the queue: the launcher's record decides
    monkeypatch.setattr(cli, "job_status", lambda job, tries=3: {"state": "done"})
    assert cli.wait_running(5) is True
    monkeypatch.setattr(cli, "job_status", lambda job, tries=3: None)
    assert cli.wait_running(5) is False


def test_status_json_for_displays(fs, monkeypatch, capsys):
    import json as _json
    fs.add(41, "alice", name="kotl-run"); fs.add(9, "bob", name="other-job")
    answers = {"boards": [{"name": "vcu118-pc1", "state": "busy", "job_id": 41}],
               "history": [{"job_id": 41, "result": None}, {"job_id": 40, "result": "passed"}],
               "notices": [{"text": "x"}]}
    monkeypatch.setattr(cli, "launch", lambda *a, **k: (0, _json.dumps(answers[a[0]]).encode(), ""))
    assert cli.main(["status", "--json"]) == 0
    s = _json.loads(capsys.readouterr().out)
    assert [q["job"] for q in s["queue"]] == ["41"]                # only Kotl's jobs
    assert [j["job_id"] for j in s["running_mine"]] == [41] and s["unread"] == 1
    assert s["boards"][0]["state"] == "busy"


def test_status_json_says_why_it_cant_reach_kotl(fs, monkeypatch, capsys):
    import json as _json
    monkeypatch.setattr(cli, "launch", lambda *a, **k: (1, b"", "sudo: a password is required\n"))
    assert cli.main(["status", "--json"]) == 0
    s = _json.loads(capsys.readouterr().out)
    assert s["boards"] == [] and "not in kotl-users" in s["problem"]
