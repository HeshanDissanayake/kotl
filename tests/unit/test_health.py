"""Health checks: glibc on the workstation vs each PC, and reachability (fake ssh)."""
import json
import os
import subprocess
from pathlib import Path

import pytest

from kotl.core import health
from kotl.core.config import Config
from kotl.core.launcher import Launcher, Refused
from kotl.core.registry import Registry
from kotl.ssh import SSHError

pytestmark = pytest.mark.feature("health")
NEW = "ldd (Ubuntu GLIBC 2.39-0ubuntu8.12) 2.39\nCopyright (C) 2024 Free Software Foundation, Inc.\n"
OLD = "ldd (Ubuntu GLIBC 2.39-0ubuntu8.9) 2.39\n"


class FakeSSH:
    def __init__(self, answer=NEW, fail=False):
        self.answer, self.fail, self.calls = answer, fail, []

    def run(self, host, argv, timeout=60, check=True):
        self.calls.append((host, argv))
        if self.fail:
            raise SSHError(f"{host}: no answer within 20 s")
        return self.answer


@pytest.mark.parametrize("text,version", [
    (NEW, "2.39-0ubuntu8.12"), (OLD, "2.39-0ubuntu8.9"),
    ("ldd (GNU libc) 2.35\n", "2.35"), ("", ""),
])
def test_glibc_version(text, version):
    assert health.glibc_version(health.glibc_line(text)) == version


def test_same_glibc_is_healthy():
    assert health.check_board({"host": "pc"}, FakeSSH(NEW), here="2.39-0ubuntu8.12") == []


def test_job_47_case_is_a_warning():
    w = health.check_board({"host": "pc"}, FakeSSH(OLD), here="2.39-0ubuntu8.12")
    assert len(w) == 1 and "workstation 2.39-0ubuntu8.12, PC 2.39-0ubuntu8.9" in w[0] and "upgrade libc6" in w[0]


def test_unreachable_is_a_warning():
    assert health.check_board({"host": "pc"}, FakeSSH(fail=True), here="x")[0].startswith("unreachable")


def test_run_stores_warnings_and_last_healthy(tmp_path, monkeypatch):
    reg = Registry(str(tmp_path / "kotl.db"))
    reg.add_board("vcu118-pc1", "vcu118-pc1", "vcu118")
    monkeypatch.setattr(health, "local_glibc", lambda: "2.39-0ubuntu8.12")
    found = health.run(reg, ssh=FakeSSH(OLD), now=lambda: 0)
    assert found["vcu118-pc1"] and reg.warnings("vcu118-pc1") == found["vcu118-pc1"]
    assert reg.board("vcu118-pc1")["last_healthy"] and reg.board("vcu118-pc1")["state"] == "idle"   # warn, don't take it away
    health.run(reg, ssh=FakeSSH(NEW))
    assert reg.warnings("vcu118-pc1") == []


def test_registry_migrates_an_old_database(tmp_path):
    import sqlite3
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE boards (name TEXT PRIMARY KEY, host TEXT NOT NULL, type TEXT NOT NULL, "
                "state TEXT NOT NULL DEFAULT 'idle', job_id INTEGER, bitstream TEXT, driver_version TEXT, "
                "last_healthy TEXT, power_watts REAL)")
    con.execute("INSERT INTO boards(name, host, type) VALUES ('b', 'h', 'vcu118')")
    con.commit(); con.close()
    reg = Registry(str(db))
    reg.set_warnings("b", ["x"])
    assert reg.warnings("b") == ["x"]


@pytest.fixture
def launcher_for(tmp_path):
    for d in ("var/lib/kotl", "srv/kotl/out", "etc/kotl"):
        (tmp_path / d).mkdir(parents=True)
    (tmp_path / "etc/kotl/kotl.conf").write_text("admin = boss\n")
    cfg = Config(prefix=str(tmp_path))

    def make(who, ssh):
        return Launcher(cfg, who=who, ssh=ssh)
    make("kotl", FakeSSH()).reg.add_board("vcu118-pc1", "vcu118-pc1", "vcu118")
    return make


def test_only_kotl_or_admin_runs_checks(launcher_for, monkeypatch):
    monkeypatch.setattr(health, "local_glibc", lambda: "2.39-0ubuntu8.12")
    with pytest.raises(Refused):
        launcher_for("alice", FakeSSH()).health()
    assert launcher_for("boss", FakeSSH(OLD)).health()["vcu118-pc1"]
    assert "! glibc differs" in launcher_for("alice", FakeSSH()).boards_table()   # everyone sees the warning


def test_health_sh_always_exits_0():
    r = subprocess.run(["sh", str(Path(__file__).resolve().parents[2] / "deploy/health.sh")])
    assert r.returncode == 0
