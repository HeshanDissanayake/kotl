"""kotl: the one command for the lab's FPGA boards.

  kotl run --eta 30m [--max 1h] [--idle 10m] [--no-wait] -- CMD...   hold a board while CMD runs
  kotl lease --eta 1h [--max 2h]       hold a board until you release it
  kotl release [JOB]                   end your lease
  kotl status                          the queue and every board
  kotl cancel JOB                      cancel your job (Slurm allows only the owner or root)
  kotl history | logs JOB [-f] | fetch JOB [--to DIR]
  kotl board list | add NAME TYPE HOST | drain NAME | resume NAME    (changes: admin only)

The ETA is required. It's the queue's estimate and never kills a job; --max (default 2x ETA)
and --idle are hang guards that free the board.
"""
import argparse
import io
import math
import os
import shlex
import subprocess
import sys
import tarfile
import time

from kotl import slurm
from kotl.core.config import parse_duration

LICENSE = "vcu118:1"


def launch_cmd():
    return shlex.split(os.environ.get("KOTL_LAUNCH", "sudo -n -u kotl /opt/kotl/launch"))


def job_sh():
    return os.environ.get("KOTL_JOB_SH", "/opt/kotl/job.sh")


def launch(*args, capture=False, stdout=None, stdin_bytes=None):
    sys.stdout.flush()   # keep our own output in order with the launcher's
    cmd = launch_cmd() + [str(a) for a in args]
    if capture:
        r = subprocess.run(cmd, capture_output=True, input=stdin_bytes)
        return r.returncode, r.stdout, r.stderr.decode(errors="replace")
    return subprocess.run(cmd, stdout=stdout, input=stdin_bytes).returncode


def die(msg, code=2):
    print(f"kotl: {msg}", file=sys.stderr)
    sys.exit(code)


def seconds(text, what):
    try:
        return parse_duration(text)
    except ValueError as e:
        die(f"{what}: {e}")


def submit(mode, eta, max_, idle, command):
    eta_s = seconds(eta, "--eta")
    env = {"KOTL_MODE": mode, "KOTL_MAX": seconds(max_, "--max") if max_ else "",
           "KOTL_IDLE": seconds(idle, "--idle") if idle else ""}
    try:
        return slurm.submit(job_sh(), command, license=LICENSE, minutes=math.ceil(eta_s / 60),
                            name=f"kotl-{mode}", chdir=os.getcwd(), env=env)
    except slurm.SlurmError as e:
        die(str(e), 1)


def wait_running(job, poll=2):
    """Wait for Slurm to start the job. Returns False if it left the queue first."""
    last = None
    while True:
        st = slurm.state(job)
        if st == "RUNNING":
            return True
        if st in ("", "COMPLETED", "CANCELLED", "FAILED", "TIMEOUT", "NODE_FAIL"):
            # a short job can start and finish between two looks: did the launcher see it?
            return job_status(job, tries=3) is not None
        if st != last:
            q = [r for r in slurm.queue() if r["job"] == str(job)]
            why = f" ({q[0]['reason']}, est. start {q[0]['start']})" if q and st == "PENDING" else ""
            print(f"kotl: job {job} {st.lower()}{why}", file=sys.stderr)
            last = st
        time.sleep(poll)


def job_status(job, tries=30):
    import json
    for _ in range(tries):
        rc, out, _err = launch("status", job, capture=True)
        if rc == 0 and out.strip() not in (b"", b"null"):
            return json.loads(out)
        time.sleep(1)
    return None


def cmd_run(a):
    if not a.command:
        die("give the command after --, e.g. kotl run --eta 10m -- ./test.sh")
    job = submit("run", a.eta, a.max, a.idle, a.command)
    print(f"kotl: job {job} queued", file=sys.stderr)
    if a.no_wait:
        print(job)
        return 0
    try:
        if not wait_running(job):
            die(f"job {job} ended before it started (kotl history)", 1)
        launch("logs", job, "-f")
    except KeyboardInterrupt:
        slurm.cancel(job)
        print(f"\nkotl: cancelled job {job}", file=sys.stderr)
        return 130
    st = job_status(job) or {}
    print(f"kotl: job {job} {st.get('result') or st.get('state')} · {st.get('board')} freed", file=sys.stderr)
    return st.get("rc") if isinstance(st.get("rc"), int) else (0 if st.get("result") == "succeeded" else 1)


def cmd_lease(a):
    job = submit("lease", a.eta, a.max, None, ["sleep", "infinity"])
    print(f"kotl: lease {job} queued", file=sys.stderr)
    if not wait_running(job):
        die(f"lease {job} ended before it started (kotl history)", 1)
    st = job_status(job) or {}
    b = st.get("board")
    idle = f"{st['idle_s'] // 60}m" if st.get("idle_s") else "-"
    mx = f"{st['max_s'] // 60}m" if st.get("max_s") else "-"
    print(f"kotl: lease {job} on {b} ({st.get('pc_user')}@{st.get('pc_address')})\n"
          f"  ssh {b}                                  # plain ssh uses your job key\n"
          f"  ssh-add /tmp/kotl-keys-$USER/{b}         # for FireSim or other tools that use your ssh-agent\n"
          f"  kotl release                              # when you're done (idle {idle} or max {mx} free it otherwise)")
    return 0


def cmd_release(a):
    import pwd
    me = pwd.getpwuid(os.getuid()).pw_name
    mine = [r for r in slurm.queue() if r["user"] == me and r["name"] == "kotl-lease"]
    jobs = [str(a.job)] if a.job else [r["job"] for r in mine]
    if not jobs:
        die("you hold no lease", 1)
    for j in jobs:
        ok = slurm.cancel(j)
        print(f"kotl: lease {j} {'released' if ok else 'could not be released'}")
    return 0


def cmd_status(a):
    rows = [r for r in slurm.queue() if r["name"].startswith("kotl-")]
    print(f"{'JOB':>6}  {'USER':10} {'KIND':6} {'STATE':9} {'ETA':>9} {'USED':>9}  START / REASON")
    for r in rows:
        tail = r["start"] if r["state"] == "PENDING" else ""
        if r["state"] == "PENDING":
            tail = f"~{r['start']} ({r['reason']})"
        print(f"{r['job']:>6}  {r['user']:10} {r['name'][5:]:6} {r['state'].lower():9} {r['eta']:>9} {r['used']:>9}  {tail}")
    if not rows:
        print("(no Kotl jobs queued or running)")
    print()
    return launch("boards")


def cmd_cancel(a):
    if not slurm.cancel(a.job):
        die(f"could not cancel {a.job} (only its owner or root can)", 1)
    print(f"kotl: cancelled {a.job}")
    return 0


def cmd_fetch(a):
    rc, data, err = launch("fetch", a.job, capture=True)
    if rc != 0:
        die(err.strip() or f"fetch {a.job} failed", 1)
    os.makedirs(a.to, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as t:
        t.extractall(a.to, filter="data")
    print(f"kotl: results in {os.path.join(a.to, str(a.job))}/")
    return 0


def cmd_board(a):
    if a.action == "list":
        return launch("boards")
    if a.action == "add":
        return launch("board-add", a.name, a.type, a.host)
    return launch(f"board-{a.action}", a.name)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    command = []
    if "--" in argv:
        i = argv.index("--")
        argv, command = argv[:i], argv[i + 1:]
    ap = argparse.ArgumentParser(prog="kotl", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="hold a board while a command runs")
    r.add_argument("--eta", required=True); r.add_argument("--max"); r.add_argument("--idle")
    r.add_argument("--no-wait", action="store_true")
    le = sub.add_parser("lease", help="hold a board until kotl release")
    le.add_argument("--eta", required=True); le.add_argument("--max")
    sub.add_parser("release").add_argument("job", nargs="?", type=int)
    sub.add_parser("status")
    sub.add_parser("cancel").add_argument("job", type=int)
    sub.add_parser("history").add_argument("--limit", type=int, default=20)
    lg = sub.add_parser("logs"); lg.add_argument("job", type=int); lg.add_argument("-f", "--follow", action="store_true")
    fe = sub.add_parser("fetch"); fe.add_argument("job", type=int); fe.add_argument("--to", default="kotl-results")
    b = sub.add_parser("board"); bs = b.add_subparsers(dest="action", required=True)
    bs.add_parser("list")
    ba = bs.add_parser("add"); ba.add_argument("name"); ba.add_argument("type"); ba.add_argument("host")
    bs.add_parser("drain").add_argument("name"); bs.add_parser("resume").add_argument("name")
    a = ap.parse_args(argv)
    a.command = command

    if a.cmd == "run":
        return cmd_run(a)
    if a.cmd == "lease":
        return cmd_lease(a)
    if a.cmd == "release":
        return cmd_release(a)
    if a.cmd == "status":
        return cmd_status(a)
    if a.cmd == "cancel":
        return cmd_cancel(a)
    if a.cmd == "history":
        return launch("history", "--limit", a.limit)
    if a.cmd == "logs":
        return launch("logs", a.job, *(["-f"] if a.follow else []))
    if a.cmd == "fetch":
        return cmd_fetch(a)
    if a.cmd == "board":
        return cmd_board(a)
    return 2


if __name__ == "__main__":
    sys.exit(main())
