"""kotl: the one command for the lab's FPGA boards.

  kotl run --eta 30m [--max 1h] [--idle 10m] [--no-wait] -- CMD...   hold a board while CMD runs
  kotl lease --eta 1h [--max 2h]       hold a board until you release it
  kotl release [JOB]                   end your lease
  kotl status                          the queue, every board, and the Kotl daemon
  kotl daemon                          the Kotl daemon (kotld): running? its tasks
  kotl top                             the same, live, with your jobs (l logs, c cancel, r release, f fetch)
  kotl cancel JOB                      cancel your job (Slurm allows only the owner or root)
  kotl history | logs JOB [-f] | fetch JOB [--to DIR]
  kotl attach [JOB]                    FireSim's console on your job's PC (Ctrl-a d detaches)
  kotl notices [--all] [--peek]        ETA, start-time and board notices for you (--peek: don't mark read)
  kotl board list | add NAME TYPE HOST | drain NAME | resume NAME | check    (changes: admin only)

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


def from_shared(doc, user):
    """The Kotl daemon's shared status file, seen by one user (the same shape as status_json)."""
    queue = doc.get("queue", [])
    return {"user": user, "boards": doc.get("boards", []), "queue": queue,
            "running_mine": [{"job_id": int(q["job"]), "mode": q["name"].replace("kotl-", "")}
                             for q in queue if q["user"] == user and q["state"] == "RUNNING"],
            "unread": doc.get("unread", {}).get(user, 0), "problem": None,
            "daemon": {"updated": doc.get("updated")}}


def status_json():
    """Everything a status display needs, as one JSON document (kotl status --json).
    From the Kotl daemon's status file when it is fresh; otherwise asked directly."""
    import json
    import pwd
    from kotl.core.daemon import read_status
    doc = read_status()
    if doc:
        return from_shared(doc, pwd.getpwuid(os.getuid()).pw_name)

    problems = []

    def lj(*args):
        rc, out, err = launch(*args, "--json", capture=True)
        if rc != 0:
            if "password is required" in err:
                problems.append("this terminal can't reach Kotl: not in kotl-users yet (log in again, or restart tmux)")
            else:
                problems.append((err.strip().splitlines() or [f"launch {args[0]} failed"])[-1])
            return []
        try:
            return json.loads(out or b"[]")
        except ValueError:
            return []
    try:
        queue = [r for r in slurm.queue() if r["name"].startswith("kotl-")]
    except slurm.SlurmError:
        queue = []
    mine = [j for j in lj("history", "--limit", "10") if not j.get("result")]
    boards = lj("boards")
    unread = len(lj("notices", "--unread"))
    return {"user": pwd.getpwuid(os.getuid()).pw_name, "boards": boards, "queue": queue,
            "running_mine": mine, "unread": unread, "problem": problems[0] if problems else None,
            "daemon": None}


def daemon_line():
    from kotl.core.daemon import read_status
    doc = read_status(max_age=10)
    if not doc:
        return "Kotl daemon: not running (displays ask Kotl directly; admin: systemctl status kotl-daemon)"
    import time
    tasks = doc.get("daemon", {}).get("tasks", {})
    bad = [f"{n}: {t['error']}" for n, t in tasks.items() if t.get("error")]
    return (f"Kotl daemon: running, updated {max(0.0, time.time() - doc['updated']):.1f} s ago"
            + (f"; problems: {'; '.join(bad)}" if bad else ""))


def cmd_daemon(a):
    import json
    import time
    from kotl.core.daemon import read_status
    doc = read_status(max_age=10)
    print(daemon_line())
    if doc:
        d = doc.get("daemon", {})
        print(f"  pid {d.get('pid')}, up {time.time() - d.get('started', time.time()):.0f} s")
        for name, t in d.get("tasks", {}).items():
            ok = f"{time.time() - t['last_ok']:.1f} s ago" if t.get("last_ok") else "never"
            print(f"  task {name:8} every {t['every']:g} s · last ok {ok}" + (f" · error: {t['error']}" if t.get("error") else ""))
    return 0 if doc else 1


def cmd_status(a):
    if a.json:
        import json
        print(json.dumps(status_json()))
        return 0
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
    rc = launch("boards")
    print("\n" + daemon_line())
    n = unread_count()
    if n:
        print(f"\nkotl: {n} unread notice{'s' if n > 1 else ''}: kotl notices")
    return rc


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


def my_running_jobs():
    import json
    rc, out, _ = launch("history", "--limit", "20", "--json", capture=True)
    rows = json.loads(out or b"[]") if rc == 0 else []
    return [r["job_id"] for r in rows if not r.get("result")]


def cmd_attach(a):
    import pwd
    from kotl.core import attach
    job = a.job
    if not job:
        running = my_running_jobs()
        if len(running) != 1:
            die("give the job number (kotl attach JOB)" if running else "you have no running job", 1)
        job = running[0]
    argv, why = attach.argv_for(job_status(job, tries=1), pwd.getpwuid(os.getuid()).pw_name, job)
    if not argv:
        die(why, 1)
    print(f"kotl: attaching to job {job}'s console · Ctrl-a d detaches", file=sys.stderr)
    os.execvp(argv[0], argv)


def unread_count():
    import json
    rc, out, _ = launch("notices", "--unread", "--json", capture=True)
    return len(json.loads(out or b"[]")) if rc == 0 else 0


def cmd_board(a):
    if a.action == "list":
        return launch("boards")
    if a.action == "add":
        return launch("board-add", a.name, a.type, a.host)
    if a.action == "check":
        return launch("health")
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
    sub.add_parser("status").add_argument("--json", action="store_true", help="for status displays")
    sub.add_parser("top", help="live view of boards, queue and your jobs")
    sub.add_parser("daemon", help="the Kotl daemon: is it running, its tasks")
    sub.add_parser("cancel").add_argument("job", type=int)
    sub.add_parser("attach").add_argument("job", nargs="?", type=int)
    nt = sub.add_parser("notices"); nt.add_argument("--all", action="store_true")
    nt.add_argument("--peek", action="store_true", help="show unread notices without marking them read")
    sub.add_parser("history").add_argument("--limit", type=int, default=20)
    lg = sub.add_parser("logs"); lg.add_argument("job", type=int); lg.add_argument("-f", "--follow", action="store_true")
    fe = sub.add_parser("fetch"); fe.add_argument("job", type=int); fe.add_argument("--to", default="kotl-results")
    b = sub.add_parser("board"); bs = b.add_subparsers(dest="action", required=True)
    bs.add_parser("list")
    ba = bs.add_parser("add"); ba.add_argument("name"); ba.add_argument("type"); ba.add_argument("host")
    bs.add_parser("drain").add_argument("name"); bs.add_parser("resume").add_argument("name")
    bs.add_parser("check", help="run the health checks now (admin)")
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
    if a.cmd == "daemon":
        return cmd_daemon(a)
    if a.cmd == "top":
        from kotl.cli import top
        return top.main()
    if a.cmd == "cancel":
        return cmd_cancel(a)
    if a.cmd == "attach":
        return cmd_attach(a)
    if a.cmd == "notices":
        return launch("notices", *([] if a.all else ["--unread"]), *([] if a.peek else ["--read"]))
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
