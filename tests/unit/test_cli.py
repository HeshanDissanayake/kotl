"""The kotl command, with a fake Slurm and no launcher."""
import pytest

from kotl import slurm
from kotl.cli import main as cli

from .fakes import FakeSlurm

pytestmark = pytest.mark.feature("cli")


@pytest.fixture
def fs(monkeypatch):
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
