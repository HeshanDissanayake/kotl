"""deploy/job.sh and deploy/epilog.sh, with a fake launcher that records its calls."""
import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

DEPLOY = Path(__file__).resolve().parents[2] / "deploy"


@pytest.fixture
def fake(tmp_path):
    calls = tmp_path / "calls"
    log = tmp_path / "output.log"
    script = tmp_path / "launch"
    script.write_text(f"""#!/bin/bash
echo "$*" >> {calls}
case "$1" in
  log) cat >> {log} ;;
  start) [ -e {tmp_path}/refuse ] && {{ echo "kotl: refused" >&2; exit 1; }}; exit 0 ;;
esac
exit 0
""")
    script.chmod(0o755)
    env = dict(os.environ, SLURM_JOB_ID="42", KOTL_LAUNCH=str(script), KOTL_MODE="run", KOTL_MAX="600")
    return tmp_path, calls, log, env


def lines(p):
    return p.read_text().splitlines() if p.exists() else []


@pytest.mark.feature("launcher")
def test_runs_command_and_passes_exit_code(fake):
    tmp, calls, log, env = fake
    r = subprocess.run(["bash", str(DEPLOY / "job.sh"), "sh", "-c", "echo hi; echo oops >&2; exit 3"], env=env)
    assert r.returncode == 3
    c = lines(calls)
    assert c[0] == "start 42 --mode run --max 600 --command sh -c echo hi; echo oops >&2; exit 3"
    assert "log 42" in c and c[-1] == "end 42 --rc 3"
    assert "hi" in log.read_text() and "oops" in log.read_text()


@pytest.mark.feature("launcher")
def test_refused_start_runs_nothing(fake):
    tmp, calls, log, env = fake
    (tmp / "refuse").touch()
    r = subprocess.run(["bash", str(DEPLOY / "job.sh"), "touch", str(tmp / "ran")], env=env)
    assert r.returncode == 1 and not (tmp / "ran").exists()
    assert not any(l.startswith("end") for l in lines(calls))


@pytest.mark.feature("launcher")
def test_cancel_runs_end_step(fake):
    tmp, calls, log, env = fake
    p = subprocess.Popen(["bash", str(DEPLOY / "job.sh"), "sleep", "30"], env=env)
    for _ in range(50):
        if "start" in "".join(lines(calls)):
            break
        time.sleep(0.1)
    time.sleep(0.3)
    p.send_signal(signal.SIGTERM)       # what Slurm sends on scancel or a tripped guard
    p.wait(timeout=10)
    assert lines(calls)[-1] == "end 42 --signal"


@pytest.mark.feature("starter")
def test_epilog_never_fails(tmp_path):
    r = subprocess.run(["sh", str(DEPLOY / "epilog.sh")], env=dict(os.environ, SLURM_JOB_ID="1"))
    assert r.returncode == 0
