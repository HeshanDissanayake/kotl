"""M2 end to end through real Slurm on the workstation. No FPGA: the PC is never touched.

Runs only where Kotl is installed (/usr/local/bin/kotl). Each test holds the board's
license for a few seconds, like any small Kotl job.
"""
import json
import os
import shutil
import subprocess
import time

import pytest

KOTL = shutil.which("kotl") if os.path.exists("/opt/kotl/launch") else None
pytestmark = pytest.mark.skipif(not KOTL, reason="Kotl is not installed here (deploy/kotl/install.sh)")


def kotl(*args, timeout=300):
    return subprocess.run([KOTL, *args], capture_output=True, text=True, timeout=timeout)


def launch(*args):
    return subprocess.run(["sudo", "-n", "-u", "kotl", "/opt/kotl/launch", *args],
                          capture_output=True, text=True)


def status(job):
    r = launch("status", str(job))
    return json.loads(r.stdout) if r.returncode == 0 else None


def squeue_state(job):
    return subprocess.run(["squeue", "-h", "-j", str(job), "-o", "%T"], capture_output=True, text=True).stdout.strip()


def submit(*args):
    r = kotl("run", "--no-wait", *args)
    assert r.returncode == 0, r.stderr
    return int(r.stdout.strip())


def wait_for(pred, timeout=180, step=1):
    end = time.time() + timeout
    while time.time() < end:
        v = pred()
        if v:
            return v
        time.sleep(step)
    raise AssertionError("timed out")


def wait_done(job, timeout=240):
    return wait_for(lambda: (s := status(job)) and s["state"] == "done" and s, timeout)


def board_idle():
    return "idle" in launch("boards").stdout


@pytest.mark.feature("launcher")
def test_run_goes_queued_running_done(tmp_path):
    os.chdir(tmp_path)
    r = kotl("run", "--eta", "5m", "--", "sh", "-c", "echo hello from $(hostname); sleep 3")
    assert r.returncode == 0, r.stderr
    assert "hello from" in r.stdout
    assert "succeeded" in r.stderr
    assert board_idle()


@pytest.mark.feature("launcher")
def test_exit_code_and_failed(tmp_path):
    os.chdir(tmp_path)
    r = kotl("run", "--eta", "5m", "--", "sh", "-c", "exit 3")
    assert r.returncode == 3 and "failed" in r.stderr


@pytest.mark.feature("cli")
def test_cancel_stops_cleanly(tmp_path):
    os.chdir(tmp_path)
    job = submit("--eta", "5m", "--", "sleep", "300")
    wait_for(lambda: (s := status(job)) and s["state"] == "running")
    assert kotl("cancel", str(job)).returncode == 0
    s = wait_done(job, 150)
    assert s["result"] == "cancelled"
    wait_for(board_idle, 30)


@pytest.mark.feature("launcher")
def test_max_guard_trips(tmp_path):
    os.chdir(tmp_path)
    job = submit("--eta", "2m", "--max", "15s", "--", "sleep", "300")
    s = wait_done(job, 200)
    assert s["result"] == "over_max"
    wait_for(board_idle, 30)


@pytest.mark.feature("registry")
def test_two_jobs_never_share_the_board(tmp_path):
    os.chdir(tmp_path)
    a = submit("--eta", "5m", "--", "sleep", "20")
    b = submit("--eta", "5m", "--", "sleep", "1")
    wait_for(lambda: squeue_state(a) == "RUNNING")
    time.sleep(3)
    assert squeue_state(b) == "PENDING"
    reasons = subprocess.run(["squeue", "-h", "-j", str(b), "-o", "%r"], capture_output=True, text=True).stdout
    assert "Licenses" in reasons
    sa, sb = wait_done(a), wait_done(b)
    assert sa["result"] == sb["result"] == "succeeded"
    assert sb["started"] >= sa["ended"] - 1     # b only ran after a let go


@pytest.mark.feature("cli")
def test_lease_and_release(tmp_path):
    os.chdir(tmp_path)
    r = kotl("lease", "--eta", "5m")
    assert r.returncode == 0 and "vcu118-pc1" in r.stdout, r.stderr
    job = int(r.stderr.split("lease ")[1].split()[0])
    assert kotl("release").returncode == 0
    assert wait_done(job, 150)["result"] == "released"


@pytest.mark.feature("results")
def test_fetch_and_history(tmp_path):
    os.chdir(tmp_path)
    job = submit("--eta", "5m", "--", "sh", "-c", "echo result-line")
    wait_done(job)
    assert kotl("fetch", str(job), "--to", str(tmp_path / "res")).returncode == 0
    d = tmp_path / "res" / str(job)
    assert json.loads((d / "status.json").read_text())["result"] == "succeeded"
    assert "result-line" in (d / "output.log").read_text()
    assert str(job) in kotl("history").stdout
