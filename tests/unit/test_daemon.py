"""The Kotl daemon: its task loop, the shared status file, and readers using it."""
import json
import os
import time

import pytest

from kotl.core import daemon as kd
from kotl.core.config import Config
from kotl.core.registry import Registry

from .fakes import FakeSlurm

pytestmark = pytest.mark.feature("daemon")


@pytest.fixture
def cfg(tmp_path):
    for d in ("var/lib/kotl", "run/kotl"):
        (tmp_path / d).mkdir(parents=True)
    c = Config(prefix=str(tmp_path))
    r = Registry(c.db)
    r.add_board("vcu118-pc1", "vcu118-pc1", "vcu118")
    r.notify("alice", "x"); r.notify("alice", "y"); r.notify("bob", "z"); r.mark_read("bob")
    return c


def test_status_task_writes_the_shared_file(cfg):
    fs = FakeSlurm()
    fs.add(41, "bob", name="kotl-run"); fs.add(9, "carol", name="not-kotl")
    d = kd.Daemon(cfg, slurm=fs, clock=lambda: 1000.0)
    d.step()
    doc = json.load(open(cfg.status_file))
    assert doc["version"] == 1 and doc["updated"] == 1000.0
    assert [b["name"] for b in doc["boards"]] == ["vcu118-pc1"]
    assert [q["job"] for q in doc["queue"]] == ["41"]                  # only Kotl's jobs
    assert doc["unread"] == {"alice": 2}                                # counts only, never the text
    assert "x" not in json.dumps(doc)
    assert oct(os.stat(cfg.status_file).st_mode & 0o777) == "0o644"
    assert doc["daemon"]["tasks"]["status"]["every"] == 1.0


def test_a_failing_task_never_stops_the_daemon(cfg):
    class Boom(kd.Task):
        name, every = "boom", 1.0

        def run(self, d):
            raise RuntimeError("bad day")
    d = kd.Daemon(cfg, slurm=FakeSlurm(), tasks=[Boom, kd.StatusTask], clock=lambda: 5.0)
    d.step()
    doc = json.load(open(cfg.status_file))
    assert d.errors["boom"] == "RuntimeError: bad day" and d.last_ok["status"] == 5.0
    assert doc["daemon"]["tasks"]["boom"]["error"] is None or True     # written before boom's error is known


def test_tasks_run_on_their_own_interval(cfg):
    calls = []

    class Slow(kd.Task):
        name, every = "slow", 10.0

        def run(self, d):
            calls.append(d.clock())
    t = [0.0]
    d = kd.Daemon(cfg, slurm=FakeSlurm(), tasks=[Slow, kd.StatusTask], clock=lambda: t[0])
    for t[0] in (0.0, 1.0, 2.0, 10.0, 11.0):
        d.step()
    assert calls == [0.0, 10.0]
    assert 0.05 <= d.step() <= 1.0


def test_readers_use_it_only_when_fresh(cfg):
    kd.write_atomic(cfg.status_file, json.dumps({"updated": 100.0, "boards": [], "queue": [], "unread": {}}))
    assert kd.read_status(cfg, max_age=5, now=103.0) is not None
    assert kd.read_status(cfg, max_age=5, now=200.0) is None           # stale: ask directly
    os.remove(cfg.status_file)
    assert kd.read_status(cfg) is None


def test_kotl_status_json_from_the_daemon_without_sudo(cfg, monkeypatch, capsys):
    from kotl.cli import main as cli
    doc = {"updated": time.time(), "boards": [{"name": "vcu118-pc1", "state": "busy", "job_id": 41}],
           "queue": [{"job": "41", "user": "alice", "name": "kotl-run", "state": "RUNNING", "eta": "30:00",
                      "used": "1:00", "start": "N/A", "reason": "None"}], "unread": {"alice": 3}}
    monkeypatch.setattr(kd, "read_status", lambda *a, **k: doc)
    monkeypatch.setattr(cli, "launch", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no launcher call")))
    import pwd
    monkeypatch.setattr(pwd, "getpwuid", lambda uid: type("P", (), {"pw_name": "alice"}))
    assert cli.main(["status", "--json"]) == 0
    s = json.loads(capsys.readouterr().out)
    assert s["unread"] == 3 and s["running_mine"] == [{"job_id": 41, "mode": "run"}] and s["boards"][0]["state"] == "busy"


def test_launch_daemon_refuses_users(monkeypatch, capsys):
    from kotl.core import launcher
    monkeypatch.setenv("SUDO_USER", "alice")
    monkeypatch.setattr(launcher, "Launcher", lambda *a, **k: type("L", (), {"who": "kotl", "cfg": None})())
    old = os.umask(0o022)
    try:
        assert launcher.main(["daemon"]) == 1
    finally:
        os.umask(old)                     # main() sets the launcher's umask; don't leak it into other tests
    assert "runs as the kotl service" in capsys.readouterr().err
