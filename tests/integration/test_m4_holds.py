"""M4 through real Slurm: draining a board holds its license, so queued jobs wait; resuming
lets them run. The waiting job is cancelled before it starts: nothing touches the PC."""
import os
import shutil
import subprocess
import time

import pytest

KOTL = shutil.which("kotl") if os.path.exists("/opt/kotl/launch") else None


def _can_launch():
    return subprocess.run(["sudo", "-n", "-u", "kotl", "/opt/kotl/launch", "boards"], capture_output=True).returncode == 0


pytestmark = [pytest.mark.skipif(not KOTL, reason="Kotl is not installed here"),
              pytest.mark.skipif(bool(KOTL) and not _can_launch(), reason="this session can't sudo to kotl")]


def run(*a):
    return subprocess.run(a, capture_output=True, text=True)


def reservations():
    return run("scontrol", "show", "reservation").stdout


@pytest.mark.feature("health")
def test_drain_holds_and_resume_releases(tmp_path):
    os.chdir(tmp_path)
    if "idle" not in run(KOTL, "board", "list").stdout:
        pytest.skip("the board is busy; try again when it's idle")
    r = run(KOTL, "board", "drain", "vcu118-pc1")
    assert r.returncode == 0, r.stderr
    job = None
    try:
        assert "kotl-maint-vcu118-pc1" in reservations()
        job = run(KOTL, "run", "--no-wait", "--eta", "5m", "--", "true").stdout.strip()
        time.sleep(5)
        state = run("squeue", "-h", "-j", job, "-o", "%T %r").stdout.split()
        assert state and state[0] == "PENDING", state            # held: it waits, it doesn't fail
    finally:
        if job:
            run(KOTL, "cancel", job)                              # before it starts: no PC touched
        run(KOTL, "board", "resume", "vcu118-pc1")
    assert "kotl-maint-vcu118-pc1" not in reservations()
    assert "idle" in run(KOTL, "board", "list").stdout
