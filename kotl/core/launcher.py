"""The launcher: Kotl's board lease. Installed as /opt/kotl/launch and run as kotl.

Users reach it only through sudo (deploy/sudoers/kotl), from job.sh inside their own Slurm job
or from the kotl CLI. Every subcommand checks who is asking:

  start JOB --mode M [--max S] [--idle S] [--command C]   claim a board for the caller's running job
  log JOB                    append stdin to the job's output.log (the owner's command output)
  end JOB [--rc N | --signal] [--epilog]    the end step; safe to run twice
  watch JOB                  (kotl only) the guards: --max and --idle cancel the job
  logs JOB [-f]   fetch JOB   history   status JOB      read your own jobs
  boards                     every board's state
  board-add NAME TYPE HOST | board-drain NAME | board-resume NAME    admin only
"""
import argparse
import json
import os
import subprocess
import sys
import time

from kotl import slurm as slurm_mod
from kotl.core import results
from kotl.core.config import Config, caller, fmt_duration
from kotl.core.registry import Registry, RegistryError

RUNNING = {"RUNNING", "CONFIGURING", "COMPLETING", "SUSPENDED", "STOPPED"}


class Refused(Exception):
    """The request isn't allowed or can't be done; the message says why."""


def time_limit_seconds(text):
    """Slurm TimeLimit ('30:00', '1:00:00', '1-02:00:00', 'UNLIMITED') -> seconds or None."""
    if not text or text in ("UNLIMITED", "Partition_Limit", "NOT_SET"):
        return None
    days = 0
    if "-" in text:
        d, text = text.split("-", 1)
        days = int(d)
    parts = [int(x) for x in text.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts
    return ((days * 24 + h) * 60 + m) * 60 + s


class Launcher:
    def __init__(self, cfg=None, slurm=slurm_mod, who=None, clock=time.time, sleep=time.sleep):
        self.cfg = cfg or Config()
        self.slurm = slurm
        self.who = who or caller()
        self.clock, self.sleep = clock, sleep
        self.reg = Registry(self.cfg.db)

    # --- who may do what
    def is_admin(self):
        return self.who in ("root", "kotl") or self.who == self.cfg.get("admin")

    def own_job(self, job_id):
        j = self.reg.job(job_id)
        if not j:
            raise Refused(f"job {job_id} is not a Kotl job (or hasn't started)")
        if j["user"] != self.who and not self.is_admin():
            raise Refused(f"job {job_id} belongs to {j['user']}")
        return j

    def dir_for(self, j):
        return results.job_dir(self.cfg.out, j["user"], j["job_id"])

    # --- the lease
    def start(self, job_id, mode, max_=None, idle=None, command=""):
        info = self.slurm.job_info(job_id)
        if not info:
            raise Refused(f"Slurm has no job {job_id}")
        if info.get("User") != self.who:
            raise Refused(f"job {job_id} belongs to {info.get('User')}, not {self.who}")
        if info.get("JobState") not in RUNNING:
            raise Refused(f"job {job_id} is {info.get('JobState')}, not running")
        btype = self.cfg.get("board_type")
        if f"{btype}:" not in info.get("Licenses", ""):
            raise Refused(f"job {job_id} holds no {btype} license; submit it through kotl")
        eta = time_limit_seconds(info.get("TimeLimit"))
        max_ = max_ if max_ is not None else (2 * eta if eta else None)
        board = self.reg.claim(job_id, btype)
        if not board:
            raise Refused(f"no idle {btype} board, although Slurm gave a license; "
                          "a board may be down or in maintenance (kotl board list)")
        try:
            self.reg.start_job(job_id, self.who, mode, board["name"], eta, max_, idle or None, command)
        except RegistryError as e:
            raise Refused(str(e)) from None
        d = results.job_dir(self.cfg.out, self.who, job_id, create=True)
        results.purge(self.cfg.out, int(self.cfg.get("keep_days") or 30))
        results.write_status(d, self.status_doc(self.reg.job(job_id), state="running"))
        results.log(d, f"start: {mode} job {job_id} for {self.who} on {board['name']}; "
                       f"eta {fmt_duration(eta) if eta else '-'}, max {fmt_duration(max_) if max_ else 'off'}, "
                       f"idle {fmt_duration(idle) if idle else 'off'}")
        self.grant_access(job_id, board)
        self.spawn_watcher(job_id)
        print(f"kotl: job {job_id} has {board['name']}")
        return board

    def grant_access(self, job_id, board):
        """M3: add this job's key to the board's PC. M2 has no PC access yet."""

    def revoke_access(self, job_id, board_name):
        """M3: remove the job key, end its sessions and processes."""

    def spawn_watcher(self, job_id):
        # the watcher is Kotl's own process, not the user's: drop sudo's caller variables,
        # or watch() would refuse it as a user request
        env = {k: v for k, v in os.environ.items() if not k.startswith("SUDO_")}
        subprocess.Popen([sys.executable, "-I", os.path.abspath(sys.argv[0]), "watch", str(job_id)],
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True, env=env)

    def append_log(self, job_id, stream):
        j = self.own_job(job_id)
        path = os.path.join(self.dir_for(j), "output.log")
        with open(path, "ab", buffering=0) as f:
            for chunk in iter(lambda: stream.read1(65536) if hasattr(stream, "read1") else stream.read(65536), b""):
                f.write(chunk)

    def end(self, job_id, rc=None, signal=False, epilog=False):
        j = self.reg.job(job_id)
        if not j:
            return None  # not a Kotl job (the epilog runs after every Slurm job)
        if not epilog:
            self.own_job(job_id)
        if j["ended"]:
            self.reg.release(job_id)  # make sure, then nothing more
            return j["result"]
        if signal or epilog:
            result = j["reason"] or ("released" if j["mode"] == "lease" else "cancelled")
            if epilog and not signal and not j["reason"]:
                result = "killed"
        else:
            result = "succeeded" if rc == 0 else "failed"
        d = self.dir_for(j)
        self.revoke_access(job_id, j["board"])
        if self.reg.finish(job_id, result, rc):
            self.reg.release(job_id)
            j = self.reg.job(job_id)
            os.makedirs(d, exist_ok=True)
            results.write_status(d, self.status_doc(j, state="done"))
            results.log(d, f"end: {result}" + (f" (exit {rc})" if rc is not None else "") +
                        (" [epilog]" if epilog else "") + f"; {j['board']} freed")
        return result

    # --- guards
    def watch(self, job_id, poll=5):
        if os.environ.get("SUDO_USER"):
            raise Refused("watch is started by Kotl itself")
        j = self.reg.job(job_id)
        if not j:
            return
        d, tripped = self.dir_for(j), False
        out = os.path.join(d, "output.log")
        while self.slurm.state(job_id) in RUNNING:
            now = self.clock()
            reason = None
            if j["max"] and now - j["started"] > j["max"]:
                reason = "over_max"
            elif j["idle"]:
                last = os.path.getmtime(out) if os.path.exists(out) else j["started"]
                if now - last > j["idle"]:
                    reason = "idle"
            if reason and not tripped:
                tripped = True
                self.reg.set_reason(job_id, reason)
                results.log(d, f"guard: {reason}; cancelling job {job_id}")
                self.slurm.cancel(job_id)
            self.sleep(poll)

    # --- reading
    def status_doc(self, j, state):
        return {"job": j["job_id"], "user": j["user"], "mode": j["mode"], "board": j["board"],
                "state": state, "result": j["result"], "rc": j["rc"], "reason": j["reason"],
                "eta_s": j["eta"], "max_s": j["max"], "idle_s": j["idle"],
                "started": j["started"], "ended": j["ended"], "command": j["command"]}

    def logs(self, job_id, follow=False, out=sys.stdout.buffer):
        j = self.own_job(job_id)
        path = os.path.join(self.dir_for(j), "output.log")
        pos = 0
        while True:
            if os.path.exists(path):
                with open(path, "rb") as f:
                    f.seek(pos)
                    data = f.read()
                    pos += len(data)
                    if data:
                        out.write(data)
                        out.flush()
            if not follow or self.reg.job(job_id)["ended"]:
                if follow and os.path.exists(path) and os.path.getsize(path) > pos:
                    continue
                return
            self.sleep(1)

    def fetch(self, job_id, out=sys.stdout.buffer):
        j = self.own_job(job_id)
        out.write(results.tar_bytes(self.dir_for(j), job_id))
        out.flush()

    def history(self, limit=20):
        rows = self.reg.jobs(None if self.is_admin() and self.who in ("root", "kotl") else self.who, limit)
        lines = [f"{'JOB':>6}  {'USER':10} {'MODE':6} {'BOARD':11} {'RESULT':10} {'TIME':>7}  STARTED"]
        for r in rows:
            took = fmt_duration((r["ended"] or self.clock()) - r["started"]) if r["started"] else "-"
            when = time.strftime("%m-%d %H:%M", time.localtime(r["started"])) if r["started"] else "-"
            lines.append(f"{r['job_id']:>6}  {r['user']:10} {r['mode']:6} {r['board'] or '-':11} "
                         f"{r['result'] or 'running':10} {took:>7}  {when}")
        return "\n".join(lines)

    def boards_table(self):
        lines = [f"{'BOARD':12} {'TYPE':7} {'STATE':12} {'JOB':>6}  HOST"]
        for b in self.reg.boards():
            lines.append(f"{b['name']:12} {b['type']:7} {b['state']:12} {b['job_id'] or '-':>6}  {b['host']}")
        return "\n".join(lines)

    # --- admin
    def need_admin(self):
        if not self.is_admin():
            raise Refused("only the admin can do that")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="launch", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("start"); s.add_argument("job", type=int); s.add_argument("--mode", default="run")
    s.add_argument("--max", type=int); s.add_argument("--idle", type=int); s.add_argument("--command", default="")
    sub.add_parser("log").add_argument("job", type=int)
    e = sub.add_parser("end"); e.add_argument("job", type=int); e.add_argument("--rc", type=int)
    e.add_argument("--signal", action="store_true"); e.add_argument("--epilog", action="store_true")
    sub.add_parser("watch").add_argument("job", type=int)
    lg = sub.add_parser("logs"); lg.add_argument("job", type=int); lg.add_argument("-f", "--follow", action="store_true")
    sub.add_parser("fetch").add_argument("job", type=int)
    sub.add_parser("status").add_argument("job", type=int)
    sub.add_parser("history").add_argument("--limit", type=int, default=20)
    sub.add_parser("boards")
    ba = sub.add_parser("board-add"); ba.add_argument("name"); ba.add_argument("type"); ba.add_argument("host")
    sub.add_parser("board-drain").add_argument("name")
    sub.add_parser("board-resume").add_argument("name")
    a = ap.parse_args(argv)
    os.umask(0o077)   # everything the launcher writes is kotl's alone

    try:
        if a.cmd == "end" and a.epilog:
            # the epilog runs after every Slurm job, Kotl's or not: never fail it
            try:
                Launcher().end(a.job, signal=False, epilog=True)
            except Exception as ex:  # noqa: BLE001
                print(f"kotl: epilog end step for {a.job}: {ex}", file=sys.stderr)
            return 0
        L = Launcher()
        if a.cmd == "start":
            L.start(a.job, a.mode, a.max, a.idle, a.command)
        elif a.cmd == "log":
            L.append_log(a.job, sys.stdin.buffer)
        elif a.cmd == "end":
            print(f"kotl: job {a.job}: {L.end(a.job, rc=a.rc, signal=a.signal)}")
        elif a.cmd == "watch":
            L.watch(a.job)
        elif a.cmd == "logs":
            L.logs(a.job, a.follow)
        elif a.cmd == "fetch":
            L.fetch(a.job)
        elif a.cmd == "status":
            j = L.own_job(a.job)
            print(json.dumps(results.read_status(L.dir_for(j)), indent=2))
        elif a.cmd == "history":
            print(L.history(a.limit))
        elif a.cmd == "boards":
            print(L.boards_table())
        elif a.cmd == "board-add":
            L.need_admin(); L.reg.add_board(a.name, a.host, a.type); print(L.boards_table())
        elif a.cmd == "board-drain":
            L.need_admin(); L.reg.drain(a.name); print(L.boards_table())
        elif a.cmd == "board-resume":
            L.need_admin()
            b = L.reg.board(a.name)
            if b and b["job_id"]:
                raise Refused(f"{a.name} is held by job {b['job_id']}; it returns by itself when that job ends")
            L.reg.set_state(a.name, "idle"); print(L.boards_table())
    except (Refused, RegistryError, slurm_mod.SlurmError) as ex:
        print(f"kotl: {ex}", file=sys.stderr)
        return 1
    return 0
