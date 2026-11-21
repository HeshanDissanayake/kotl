"""The firesim wrapper: installed first on PATH as /opt/kotl/bin/firesim.

Users type plain FireSim commands from their own Chipyard. Board commands go through the queue:

  firesim infrasetup    no board held: take a lease (waits in the queue), then run your real
                        infrasetup inside the job, with a copy of your config aimed at the board
  firesim runworkload   needs the lease; when it returns, the job's result is read from the
                        uartlog (KOTL RESULT: PASS/FAIL) and the lease ends: the board is freed
  firesim kill          runs your kill, then ends the lease
  anything else         passed straight to your real firesim

The ETA is required: export KOTL_ETA=1h, or put "eta" in kotl.json next to your config.
"""
import glob
import json
import os
import pwd
import re
import shutil
import subprocess
import sys
import time

from kotl import slurm
from kotl.cli import main as cli

BOARD_TASKS = ("infrasetup", "runworkload", "kill")
HOLD = ["sleep", "infinity"]
MARK = re.compile(rb"KOTL RESULT: (PASS|FAIL)")
HERE = os.path.dirname(os.path.realpath(sys.argv[0])) if sys.argv and sys.argv[0] else ""


def me():
    return pwd.getpwuid(os.getuid()).pw_name


def say(msg):
    print(f"kotl: {msg}", file=sys.stderr, flush=True)


def die(msg, code=2):
    say(msg)
    sys.exit(code)


def real_firesim(skip_dirs=None):
    """Your own firesim: the next one on PATH after Kotl's wrapper."""
    skip = {os.path.realpath(d) for d in (skip_dirs or [HERE, "/opt/kotl/bin"]) if d}
    for d in os.environ.get("PATH", "").split(os.pathsep):
        if d and os.path.realpath(d) not in skip:
            p = os.path.join(d, "firesim")
            if os.path.isfile(p) and os.access(p, os.X_OK):
                return p
    return None


def settings(cwd="."):
    """ETA and guards: environment first, then kotl.json in the current folder."""
    conf = {}
    path = os.path.join(cwd, "kotl.json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            conf = json.load(f)
    return {"eta": os.environ.get("KOTL_ETA") or conf.get("eta"),
            "max": os.environ.get("KOTL_MAX") or conf.get("max")}


def my_lease(user=None):
    """Your current FireSim lease (job id), if any."""
    user = user or me()
    for r in slurm.queue():
        if r["user"] == user and r["name"] == "kotl-firesim" and r["state"] in ("RUNNING", "PENDING", "CONFIGURING"):
            return int(r["job"])
    return None


def config_arg(args):
    """(index of the value, value) of -c/--runtimeconfigfile, or (None, default)."""
    for i, a in enumerate(args):
        if a in ("-c", "--runtimeconfigfile") and i + 1 < len(args):
            return i + 1, args[i + 1]
        if a.startswith("--runtimeconfigfile="):
            return i, a.split("=", 1)[1]
    return None, "config_runtime.yaml"


def aim_config(text, host):
    """Point run_farm_hosts_to_use at host (user@address); keep everything else as written."""
    out, inside, indent, changed = [], False, 0, 0
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        cur = len(line) - len(stripped)
        if inside and stripped and not stripped.startswith("#") and cur <= indent:
            inside = False
        if inside:
            m = re.match(r"(\s*-\s*)([^:#\s]+)(\s*:.*)", line, re.S)
            if m:
                if changed == 0:
                    out.append(f"{m.group(1)}{host}{m.group(3)}")
                changed += 1
                continue
        if stripped.startswith("run_farm_hosts_to_use:"):
            inside, indent = True, cur
        out.append(line)
    if changed == 0:
        raise ValueError("no run_farm_hosts_to_use entry in your runtime config")
    return "".join(out)


def with_config(args, path):
    i, _ = config_arg(args)
    args = list(args)
    if i is None:
        return args + ["-c", path]
    if args[i].startswith("--runtimeconfigfile="):
        args[i] = f"--runtimeconfigfile={path}"
    else:
        args[i] = path
    return args


def start_agent(key):
    out = subprocess.run(["ssh-agent", "-s"], capture_output=True, text=True, check=True).stdout
    env = dict(os.environ)
    for k in ("SSH_AUTH_SOCK", "SSH_AGENT_PID"):
        m = re.search(rf"{k}=([^;]+);", out)
        env[k] = m.group(1)
    subprocess.run(["ssh-add", "-q", key], env=env, check=True)
    return env


def collect(job, started, deploy="."):
    """Find this run's uartlogs, save them with the job's results, and read the marker."""
    logs = [p for p in glob.glob(os.path.join(deploy, "results-workload", "*", "**", "uartlog"), recursive=True)
            if os.path.getmtime(p) >= started - 5]
    verdict = None
    for i, p in enumerate(sorted(logs)):
        with open(p, "rb") as f:
            data = f.read()
        cli.launch("put", job, "uartlog" if i == 0 else f"uartlog.{i}", stdin_bytes=data)
        for m in MARK.finditer(data):
            verdict = "failed" if m.group(1) == b"FAIL" or verdict == "failed" else "passed"
    return verdict, logs


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    real = real_firesim()
    if not real:
        die("can't find your firesim: source your Chipyard's env.sh and FireSim's sourceme-manager.sh first")
    if not argv or argv[0] not in BOARD_TASKS:
        os.execv(real, [real, *argv])
    task = argv[0]

    job = my_lease()
    if job is None:
        if task != "infrasetup":
            die(f"you hold no board: run 'firesim infrasetup' first (it waits for one in the queue)")
        s = settings()
        if not s["eta"]:
            die("give an ETA: export KOTL_ETA=1h (or \"eta\" in kotl.json). It never kills the job.")
        job = cli.submit("firesim", s["eta"], s["max"], None, HOLD)
        say(f"waiting for a VCU118 (job {job}) ...")
        if not cli.wait_running(job):
            die(f"job {job} ended before it started (kotl history)", 1)
    st = cli.job_status(job)
    if not st or not st.get("pc_address"):
        die(f"job {job} has no board access yet (kotl history; kotl logs {job})", 1)
    say(f"job {job} holds {st['board']}. Type poweroff in the sim, or run 'firesim kill', to free it.")

    keydir = os.environ.get("KOTL_KEYDIR", f"/tmp/kotl-keys-{me()}")
    key = os.path.join(keydir, f"job-{job}")
    _, cfg = config_arg(argv)
    try:
        with open(cfg, encoding="utf-8") as f:
            aimed = aim_config(f.read(), f"{st['pc_user']}@{st['pc_address']}")
    except (OSError, ValueError) as e:
        die(f"{cfg}: {e}")
    copy = os.path.join(keydir, f"job-{job}-{os.path.basename(cfg)}")
    with open(copy, "w", encoding="utf-8") as f:
        f.write(aimed)
    args = with_config(argv, copy)

    env = start_agent(key)
    started = time.time()
    try:
        rc = slurm.run_in_job(job, [real, *args], env=env)
    finally:
        subprocess.run(["ssh-agent", "-k"], env=env, capture_output=True)

    if task == "infrasetup":
        if rc != 0:
            say(f"infrasetup failed (exit {rc}); the board stays yours. Fix and retry, or: firesim kill")
        return rc
    if task == "runworkload":
        verdict, logs = collect(job, started)
        result = verdict or ("done" if rc == 0 else "failed")
    else:
        result = "done"
    cli.launch("result", job, result)
    slurm.cancel(job)
    for _ in range(60):
        s = cli.job_status(job, tries=1) or {}
        if s.get("state") == "done":
            break
        time.sleep(1)
    say(f"job {job} {result} · {st['board']} freed · kotl fetch {job}")
    return rc if rc else (0 if result in ("passed", "done") else 1)


if __name__ == "__main__":
    sys.exit(main())
