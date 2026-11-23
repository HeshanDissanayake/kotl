"""kotl top: what the screen shows, and what its keys do (no terminal needed)."""
import io
import json
import time

import pytest

from kotl import slurm
from kotl.cli import top
from kotl.core.launcher import main as launch_main

from .fakes import FakeSlurm

pytestmark = pytest.mark.feature("top")
NOW = time.time()
SNAP = {
    "user": "alice", "when": "10:40:00",
    "boards": [{"name": "vcu118-pc1", "state": "busy", "job_id": 41, "host": "vcu118-pc1", "type": "vcu118"}],
    "queue": [
        {"job": "41", "user": "alice", "name": "kotl-run", "state": "RUNNING", "eta": "30:00", "used": "12:03", "start": "10:28", "reason": "None"},
        {"job": "42", "user": "bob", "name": "kotl-lease", "state": "PENDING", "eta": "1:00:00", "used": "0:00", "start": "10:52", "reason": "Licenses"},
    ],
    "mine": [
        {"job_id": 41, "mode": "run", "result": None, "started": NOW - 720, "ended": None, "command": "firesim runworkload -c x.yaml"},
        {"job_id": 40, "mode": "run", "result": "passed", "started": NOW - 3000, "ended": NOW - 2460, "command": "sleep 1"},
    ],
}


def test_screen_shows_boards_queue_and_my_jobs():
    text = "\n".join(top.render(SNAP, width=100, selected=0, now=NOW))
    assert "vcu118-pc1   busy" in text and "job 41" in text and "alice" in text and "ETA 30:00" in text
    assert "42 bob" in text and "~10:52 (Licenses)" in text
    assert ">    41 run    running" in text and "12m" in text
    assert "40 run    passed" in text and "9m" in text


def test_screen_fits_the_terminal():
    assert all(len(l) <= 50 for l in top.render(SNAP, width=50, now=NOW))


def test_empty_screen_explains_itself():
    text = "\n".join(top.render({"user": "a", "when": "x", "boards": [], "queue": [], "mine": []}))
    assert "kotl-users" in text and "nobody waiting" in text and "kotl run --eta" in text


@pytest.fixture
def fs(monkeypatch):
    f = FakeSlurm()
    monkeypatch.setattr(slurm, "cancel", f.cancel)
    return f


def test_keys_cancel_and_release_only_live_jobs(fs):
    assert top.action("c", SNAP["mine"][0]) == "job 41 cancelled" and fs.cancelled == [41]
    assert "already ended" in top.action("c", SNAP["mine"][1])
    assert "not a lease" in top.action("r", SNAP["mine"][0])
    assert top.action("r", dict(SNAP["mine"][0], mode="lease")) == "job 41 released"
    assert "pick one" in top.action("c", None)


def test_launcher_json_for_top(tmp_path, monkeypatch, capsys):
    from kotl.core import launcher
    from kotl.core.config import Config
    for d in ("var/lib/kotl", "srv/kotl/out", "etc/kotl"):
        (tmp_path / d).mkdir(parents=True)
    real = launcher.Launcher

    def make(*a, **k):
        k.setdefault("cfg", Config(prefix=str(tmp_path)))
        return real(*a, **k)
    monkeypatch.setattr(launcher, "Launcher", make)
    monkeypatch.setattr(launcher, "caller", lambda: "kotl")
    make(who="kotl").reg.add_board("vcu118-pc1", "vcu118-pc1", "vcu118")
    assert launch_main(["boards", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)[0]["name"] == "vcu118-pc1"
    assert launch_main(["history", "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_screen_shows_board_warnings():
    snap = dict(SNAP, boards=[dict(SNAP["boards"][0], warnings='["glibc differs: workstation A, PC B"]')])
    assert "! glibc differs: workstation A, PC B" in "\n".join(top.render(snap, width=100, now=NOW))
