"""M3 on the real PC. These hold the board through Kotl like any job. Run them only when
the admin says so:   pytest -m hw tests/hw
"""
import json
import os
import pwd
import shutil
import subprocess
import time

import pytest

ME = pwd.getpwuid(os.getuid()).pw_name
KOTL = shutil.which("kotl") if os.path.exists("/opt/kotl/launch") else None
pytestmark = [pytest.mark.hw,
              pytest.mark.skipif(not KOTL, reason="Kotl is not installed here")]


def run(*cmd, timeout=300):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def status(job):
    r = run("sudo", "-n", "-u", "kotl", "/opt/kotl/launch", "status", str(job))
    return json.loads(r.stdout) if r.returncode == 0 else None


def wait_done(job, timeout=180):
    end = time.time() + timeout
    while time.time() < end:
        s = status(job)
        if s and s["state"] == "done":
            return s
        time.sleep(1)
    raise AssertionError(f"job {job} did not finish")


def ssh_with(key, address, user):
    return run("ssh", "-o", "BatchMode=yes", "-o", "IdentitiesOnly=yes", "-o", "IdentityAgent=none",
               "-o", "PasswordAuthentication=no", "-o", "ConnectTimeout=10", "-i", key,
               f"{user}@{address}", "hostname", timeout=60)


@pytest.mark.feature("access")
def test_job_key_works_only_during_the_lease(tmp_path):
    r = run(KOTL, "lease", "--eta", "10m")
    assert r.returncode == 0, r.stderr
    job = int(r.stderr.split("lease ")[1].split()[0])
    try:
        st = status(job)
        key = f"/tmp/kotl-keys-{ME}/job-{job}"
        copy = tmp_path / "key"
        shutil.copy(key, copy)
        os.chmod(copy, 0o600)
        ok = ssh_with(str(copy), st["pc_address"], st["pc_user"])
        assert ok.returncode == 0 and ok.stdout.strip(), ok.stderr
    finally:
        run(KOTL, "release", str(job))
    s = wait_done(job)
    assert s["result"] == "released"
    assert not os.path.exists(f"/tmp/kotl-keys-{ME}/job-{job}")
    gone = ssh_with(str(copy), st["pc_address"], st["pc_user"])
    assert gone.returncode != 0 and "Permission denied" in gone.stderr


@pytest.mark.feature("fsmod")
@pytest.mark.skipif(not os.environ.get("KOTL_SMOKE_JOB"), reason="set KOTL_SMOKE_JOB to the smoke test's job id")
def test_firesim_smoke_job_passed(tmp_path):
    job = os.environ["KOTL_SMOKE_JOB"]
    s = status(job)
    assert s and s["state"] == "done" and s["mode"] == "firesim"
    assert s["result"] in ("passed", "done"), s
    r = run(KOTL, "fetch", job, "--to", str(tmp_path))
    assert r.returncode == 0, r.stderr
    uart = (tmp_path / job / "outputs" / "uartlog").read_text(errors="replace")
    assert "Power down" in uart or "poweroff" in uart.lower()
