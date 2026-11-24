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
  start) [ -e {tmp_path}/refuse ] && {{ echo "kotl: refused" >&2; exit 1; }}; echo "board=vcu118-pc1"; echo "pc=virtex-host@192.168.1.2"; exit 0 ;;
esac
exit 0
""")
    script.chmod(0o755)
    keydir = tmp_path / "keys"
    env = dict(os.environ, SLURM_JOB_ID="42", KOTL_LAUNCH=str(script), KOTL_MODE="run", KOTL_MAX="600",
               KOTL_KEYDIR=str(keydir))
    return tmp_path, calls, log, env


def lines(p):
    return p.read_text().splitlines() if p.exists() else []


@pytest.mark.feature("launcher")
def test_runs_command_and_passes_exit_code(fake):
    tmp, calls, log, env = fake
    r = subprocess.run(["bash", str(DEPLOY / "job.sh"), "sh", "-c", "echo hi; echo oops >&2; exit 3"], env=env)
    assert r.returncode == 3
    c = lines(calls)
    assert c[0].startswith("start 42 --mode run --max 600 --command sh -c echo hi; echo oops >&2; exit 3 --pubkey ssh-ed25519 ")
    assert len(c[0].split("--pubkey ")[1].split()) == 2        # type and key only: no comment, no options
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


@pytest.mark.feature("access")
def test_job_key_made_and_removed(fake):
    tmp, calls, log, env = fake
    probe = tmp / "seen"
    r = subprocess.run(["bash", str(DEPLOY / "job.sh"), "sh", "-c",
                        f"ls -l {tmp}/keys > {probe}; stat -c %a {tmp}/keys >> {probe}"], env=env)
    assert r.returncode == 0
    seen = probe.read_text()
    assert "job-42" in seen and "vcu118-pc1 -> " in seen and seen.strip().endswith("700")
    assert list((tmp / "keys").iterdir()) == []          # key and link gone after the job


@pytest.mark.feature("access")
def test_refuses_someone_elses_key_folder(fake):
    tmp, calls, log, env = fake
    (tmp / "keys").mkdir()
    (tmp / "keys").chmod(0o755)             # explicit: not subject to the process umask
    r = subprocess.run(["bash", str(DEPLOY / "job.sh"), "true"], env=env, capture_output=True, text=True)
    assert r.returncode == 1 and "only you can use" in r.stderr
    assert not lines(calls)


@pytest.mark.feature("access")
def test_command_gets_agent_and_board_vars(fake):
    tmp, calls, log, env = fake
    r = subprocess.run(["bash", str(DEPLOY / "job.sh"), "sh", "-c",
                        'echo "$KOTL_JOB $KOTL_BOARD $KOTL_PC"; ssh-add -l'], env=env)
    assert r.returncode == 0
    out = log.read_text()
    assert "42 vcu118-pc1 virtex-host@192.168.1.2" in out
    assert "kotl-job-42 (ED25519)" in out                     # the agent holds exactly the job key
