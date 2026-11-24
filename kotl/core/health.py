"""Health checks for each board's PC. Runs as kotl: from Slurm every 5 minutes (health.sh),
or by the admin with `kotl board check`.

Generic: each run asks the PC, in one ssh call, whether it is reachable and whether the board
type's card is on PCI. The enabled adapters (kotl.conf `adapters =`) add their own lines to that
call and their own failures, warnings and one repair (e.g. the FireSim adapter's driver check
and reload).

  failures  unreachable, no card, or an adapter's failure
            -> on an IDLE board only, each adapter may try one repair; if it still fails, the board
               goes DOWN: a Slurm reservation holds its license so queued jobs wait, and the admin
               gets a notice. A board a job holds is never touched.
  warnings  an adapter's warnings; something runs as the PC account on an idle board (soft
            lockdown: warn only) -> shown on the board; the board stays in the pool.
  recovery  a DOWN board whose checks pass again goes back to idle, the hold is released,
            and the admin gets a notice.
"""
import time

from kotl import slurm as slurm_mod
from kotl import ssh as ssh_mod
from kotl.adapters import work_args

KEYS = "/usr/local/bin/kotl-keys"
# the card a board type has on PCI: lspci vendor id, and its name for messages
CARDS = {"vcu118": ("10ee", "Xilinx"), "u250": ("10ee", "Xilinx")}


def probe_script(board, adapters=()):
    lines = ['echo "host=$(hostname)"']
    if board.get("type") in CARDS:
        lines.append(f'echo "card=$(lspci -d {CARDS[board["type"]][0]}: 2>/dev/null | head -n 1)"')
    return "; ".join(lines + [a.probe for a in adapters if a.probe])


def probe(board, ssh=ssh_mod, adapters=()):
    """One ssh call: {'host', 'card', ...adapters' keys}, or {'error': ...} if unreachable."""
    try:
        out = ssh.run(board["host"], ["sh", "-c", probe_script(board, adapters)], timeout=30)
    except ssh_mod.SSHError as e:
        return {"error": str(e)}
    found = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            found[k.strip()] = v.strip()
    return found


def failures_of(board, p, adapters=()):
    if "error" in p:
        return [f"unreachable: {p['error']}"]
    out = []
    if board.get("type") in CARDS and not p.get("card"):
        vendor, name = CARDS[board["type"]]
        out.append(f"no {name} card on PCI (lspci -d {vendor}:)")
    for a in adapters:
        out += a.failures(p)
    return out


def warnings_of(p, adapters=()):
    return [] if "error" in p else [w for a in adapters for w in a.warnings(p)]


def check_board(board, ssh=ssh_mod, adapters=()):
    """Failures and warnings for one board, without changing anything."""
    p = probe(board, ssh, adapters)
    return failures_of(board, p, adapters) + warnings_of(p, adapters)


def outside_note(board, account, running, ssh=ssh_mod, connected=None):
    """The warning for work on an idle board's PC: who (from the workstation), how long, outside Kotl."""
    from kotl.core import outside
    what, _, age = running.partition("; for ")
    try:
        address = ssh.address(board["host"])
    except Exception:
        address = ""
    who = outside.describe(connected(address) if connected else outside.connected_users(address)) if address else ""
    how_long = f" for {outside.duration(int(age))}" if age.strip().isdigit() and int(age) > 0 else ""
    return (f"outside Kotl: work runs on the PC as {account}{how_long} with no Kotl job holding the board: {what}"
            + (f"; connected from the workstation now: {who}" if who else "; nobody connected from the workstation now"))


def pc_busy(board, account, ssh=ssh_mod, adapters=()):
    """'' when nothing of the account runs on the PC, else what runs ('screen, sshd x2; for 300'), or 'busy'."""
    try:
        out = ssh.run(board["host"], ["sudo", "-n", "-u", account, KEYS, "busy", *work_args(adapters)],
                      timeout=30).strip()
    except ssh_mod.SSHError:
        return ""
    if not out.startswith("busy"):
        return ""
    body, _, age = out.split(":", 1)[1].partition("; for ") if ":" in out else ("", "", "")
    names = [n.strip() for n in body.split(",") if n.strip()]
    text = ", ".join(names[:8]) + (f" and {len(names) - 8} more" if len(names) > 8 else "") if names else "busy"
    return text + (f"; for {age.strip()}" if age.strip() else "")


def run(registry, ssh=ssh_mod, slurm=slurm_mod, admin="", account="virtex-host", now=time.time, adapters=()):
    """Check every board, change states, hold or release licenses. Returns {board: [problems]}."""
    found = {}
    for b in registry.boards():
        name = b["name"]
        p = probe(b, ssh, adapters)
        fails = failures_of(b, p, adapters)
        notes = []
        # never repair while a job holds the board: the job's own tools may be mid-setup
        # (FireSim reloads its driver during infrasetup)
        held = b["state"] != "idle" or b["job_id"]
        if fails and "error" not in p and not held and registry.once(f"reload:{name}"):
            for a in adapters:
                note = a.repair(b, ssh, fails)
                if note:
                    notes.append(note)
            if notes:
                p = probe(b, ssh, adapters)
                fails = failures_of(b, p, adapters)
        warnings = warnings_of(p, adapters)
        running = (pc_busy(b, account, ssh, adapters)
                   if not fails and b["state"] == "idle" and not b["job_id"] else "")
        if running:
            warnings.append(outside_note(b, account, running, ssh))

        hold = f"kotl-down-{name}"
        if fails:
            if b["state"] == "idle" and not b["job_id"]:
                registry.set_state(name, "down")
                held = slurm.hold_license(hold, f"{b['type']}:1")
                text = (f"{name} is DOWN: {'; '.join(fails)}" + (f" ({'; '.join(notes)})" if notes else "") +
                        ("; queued jobs wait" if held else "; could not hold its license, queued jobs may fail"))
                if admin:
                    registry.notify(admin, text)
            elif b["state"] == "busy":
                warnings.append(f"failing ({'; '.join(fails)}): goes down when job {b['job_id']} ends")
        else:
            registry.forget(f"reload:{name}")
            if b["state"] == "down":
                registry.set_state(name, "idle")
                slurm.release_hold(hold)
                if admin:
                    registry.notify(admin, f"{name} is back UP: its checks pass again")
        registry.set_warnings(name, fails + notes + warnings, healthy_at=None if fails else now())
        found[name] = fails + notes + warnings
    return found
