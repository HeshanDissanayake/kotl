"""kotl top: a live terminal view of the boards, the queue and your jobs.

Keys: up/down pick one of your jobs; l logs, c cancel, r release (a lease), f fetch; q quits.
Read-only for everyone else's jobs. It reads through the same launcher checks as the kotl command.
"""
import curses
import json
import os
import pwd
import subprocess
import time

from kotl import slurm
from kotl.cli import main as cli

REFRESH = 2.0


def me():
    return pwd.getpwuid(os.getuid()).pw_name


def launch_json(*args):
    rc, out, _err = cli.launch(*args, "--json", capture=True)
    if rc != 0:
        return []
    try:
        return json.loads(out or b"[]")
    except ValueError:
        return []


def snapshot():
    """Everything the screen shows, gathered once per refresh."""
    try:
        queue = [r for r in slurm.queue() if r["name"].startswith("kotl-")]
    except slurm.SlurmError:
        queue = []
    return {"user": me(), "boards": launch_json("boards"), "queue": queue,
            "mine": launch_json("history", "--limit", "8"), "when": time.strftime("%H:%M:%S"),
            "notices": launch_json("notices", "--unread")}


def wrap(text, width, first, rest):
    """Wrap a long line to the screen instead of cutting it off."""
    import textwrap
    return textwrap.wrap(text, max(20, width - 1), initial_indent=first, subsequent_indent=rest) or [first]


def ago(seconds):
    seconds = int(max(0, seconds))
    return f"{seconds // 3600}h{seconds % 3600 // 60:02d}m" if seconds >= 3600 else f"{seconds // 60}m"


def render(snap, width=80, selected=0, now=None):
    """The screen as plain lines (no curses), so it can be tested."""
    now = now or time.time()
    q = {r["job"]: r for r in snap["queue"]}
    lines = [f" Kotl top · {snap['user']}".ljust(width - 26) + f"{snap['when']} · q quit"[:26], ""]
    lines.append(" BOARDS")
    if not snap["boards"]:
        lines.append("  (no boards, or Kotl can't be reached: are you in kotl-users?)")
    for b in snap["boards"]:
        row = f"  {b['name']:12} {b['state']:12}"
        if b.get("job_id"):
            r = q.get(str(b["job_id"]), {})
            row += f" job {b['job_id']:<6} {r.get('user', '?'):10} {r.get('name', 'kotl-?')[5:]:6} " \
                   f"used {r.get('used', '-'):>8}  ETA {r.get('eta', '-')}"
        lines.append(row)
        for w in json.loads(b.get("warnings") or "[]"):
            lines += wrap(w, width, "    ! ", "      ")
    lines += ["", " QUEUE"]
    pending = [r for r in snap["queue"] if r["state"] == "PENDING"]
    if not pending:
        lines.append("  (nobody waiting)")
    for r in pending:
        lines.append(f"  {r['job']:>6} {r['user']:10} {r['name'][5:]:6} waiting  ~{r['start']} ({r['reason']})  ETA {r['eta']}")
    lines += ["", " YOUR JOBS"]
    if not snap["mine"]:
        lines.append("  (none yet: kotl run --eta 30m -- <command>, or kotl lease --eta 1h)")
    for i, j in enumerate(snap["mine"]):
        took = ago((j["ended"] or now) - j["started"]) if j.get("started") else "-"
        state = j["result"] or "running"
        mark = ">" if i == selected else " "
        lines.append(f" {mark}{j['job_id']:>6} {j['mode']:6} {state:10} {took:>6}  {(j.get('command') or '')[:max(10, width - 40)]}")
    unread = snap.get("notices") or []
    if unread:
        lines += ["", f" NOTICES ({len(unread)} unread · kotl notices)"]
        for n in unread[:3]:
            lines.append(f"  {time.strftime('%H:%M', time.localtime(n['at']))}  {n['text']}")
    lines += ["", " [l] logs  [a] attach  [c] cancel  [r] release  [f] fetch  [up/down] pick"]
    return [ln[:width] for ln in lines]


def action(key, job):
    """Run one key's command for the selected job (outside curses). Returns a status line."""
    if not job:
        return "pick one of your jobs first"
    jid = str(job["job_id"])
    if key == "l":
        subprocess.run(cli.launch_cmd() + ["logs", jid, "-f"] if not job["result"] else cli.launch_cmd() + ["logs", jid])
        input("\n-- end of log · Enter to go back --")
        return ""
    if key == "a":
        if job["result"]:
            return f"job {jid} has already ended"
        subprocess.run(["kotl", "attach", jid])
        return ""
    if key == "f":
        r = subprocess.run(["kotl", "fetch", jid], capture_output=True, text=True)
        return (r.stdout or r.stderr).strip()
    if job["result"]:
        return f"job {jid} has already ended"
    if key == "r" and job["mode"] != "lease":
        return f"job {jid} is a {job['mode']}, not a lease; use c to cancel"
    ok = slurm.cancel(jid)
    return f"job {jid} {'released' if key == 'r' else 'cancelled'}" if ok else f"could not stop job {jid}"


def loop(scr):
    try:
        curses.curs_set(0)      # some terminals can't hide the cursor; that's fine
    except curses.error:
        pass
    scr.timeout(int(REFRESH * 1000))
    selected, note, snap = 0, "", snapshot()
    last = time.time()
    while True:
        if time.time() - last >= REFRESH:
            snap, last = snapshot(), time.time()
        h, w = scr.getmaxyx()
        scr.erase()
        lines = render(snap, w - 1, selected)
        if note:
            lines.append(" " + note)
        for y, ln in enumerate(lines[:h - 1]):
            scr.addstr(y, 0, ln)
        scr.refresh()
        k = scr.getch()
        if k in (ord("q"), 27):
            return
        if k == curses.KEY_DOWN:
            selected = min(selected + 1, max(0, len(snap["mine"]) - 1))
        elif k == curses.KEY_UP:
            selected = max(selected - 1, 0)
        elif k in (ord("l"), ord("a"), ord("c"), ord("r"), ord("f")):
            job = snap["mine"][selected] if selected < len(snap["mine"]) else None
            if chr(k) in "cr" and job and not job["result"]:
                scr.addstr(min(len(lines), h - 1), 0, f" {'release' if chr(k) == 'r' else 'cancel'} job {job['job_id']}? y/n ")
                scr.timeout(-1)
                ok = scr.getch() == ord("y")
                scr.timeout(int(REFRESH * 1000))
                if not ok:
                    continue
            curses.def_prog_mode(); curses.endwin()
            note = action(chr(k), job)
            curses.reset_prog_mode(); scr.refresh()
            snap, last = snapshot(), time.time()


def main():
    curses.wrapper(loop)
    return 0
