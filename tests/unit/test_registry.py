"""Board registry: atomic claim and release, and board states."""
import subprocess
import sys
from pathlib import Path

import pytest

from kotl.core.registry import Registry, RegistryError

pytestmark = pytest.mark.feature("registry")
ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def reg(tmp_path):
    r = Registry(str(tmp_path / "kotl.db"))
    r.add_board("vcu118-pc1", "vcu118-pc1", "vcu118")
    return r


def test_claim_and_release(reg):
    b = reg.claim(1, "vcu118")
    assert b["name"] == "vcu118-pc1" and b["state"] == "busy" and b["job_id"] == 1
    assert reg.claim(2, "vcu118") is None          # only one board
    assert reg.claim(1, "vcu118")["name"] == "vcu118-pc1"   # same job again: same board
    reg.release(1)
    assert reg.board("vcu118-pc1")["state"] == "idle"
    assert reg.claim(2, "vcu118")["job_id"] == 2


def test_wrong_type_or_not_idle(reg):
    assert reg.claim(1, "u250") is None
    reg.set_state("vcu118-pc1", "down")
    assert reg.claim(1, "vcu118") is None
    with pytest.raises(RegistryError):
        reg.set_state("vcu118-pc1", "broken")


def test_drain(reg):
    reg.claim(1, "vcu118")
    reg.drain("vcu118-pc1")
    assert reg.board("vcu118-pc1")["state"] == "draining"
    reg.release(1)
    assert reg.board("vcu118-pc1")["state"] == "maintenance"   # not back in the pool
    assert reg.claim(2, "vcu118") is None


def test_two_processes_never_share_a_board(tmp_path):
    db = tmp_path / "kotl.db"
    Registry(str(db)).add_board("vcu118-pc1", "h", "vcu118")
    code = ("import sys; sys.path.insert(0, %r); from kotl.core.registry import Registry; "
            "b = Registry(%r).claim(int(sys.argv[1]), 'vcu118'); print(b['name'] if b else '-')") % (str(ROOT), str(db))
    procs = [subprocess.Popen([sys.executable, "-c", code, str(i)], stdout=subprocess.PIPE, text=True)
             for i in range(1, 13)]
    outs = [p.communicate()[0].strip() for p in procs]
    assert outs.count("vcu118-pc1") == 1 and outs.count("-") == 11


def test_job_records(reg):
    reg.start_job(5, "alice", "run", "vcu118-pc1", 600, 1200, None, "sleep 1")
    with pytest.raises(RegistryError):
        reg.start_job(5, "alice", "run", "vcu118-pc1", 600, 1200, None)
    reg.set_reason(5, "over_max")
    reg.set_reason(5, "cancelled")                    # first reason wins
    assert reg.job(5)["reason"] == "over_max"
    assert reg.finish(5, "over_max", None) is True
    assert reg.finish(5, "succeeded", 0) is False      # ends once
    assert [j["job_id"] for j in reg.jobs("alice")] == [5] and reg.jobs("bob") == []
