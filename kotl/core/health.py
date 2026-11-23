"""Health checks for each board's PC. Runs as kotl: from Slurm every 5 minutes (health.sh),
or by the admin with `kotl board check`.

Each run asks the PC, in one ssh call: is it reachable, is the Xilinx card on PCI, is the XDMA
driver loaded, which glibc does it have.

  failures  unreachable, no Xilinx card, no XDMA driver
            -> one driver reload is tried (kotl-xdma-reload, via sudo on the PC); if it still
               fails and the board is idle, it goes DOWN: a Slurm reservation holds its license
               so queued jobs wait, and the admin gets a notice. A busy board is left alone
               until its job ends.
  warnings  glibc differs from the workstation's (FireSim's bundled libc won't start there);
            something runs as the PC account on an idle board (soft lockdown: warn only)
            -> shown on the board (kotl board list, kotl top); the board stays in the pool.
  recovery  a DOWN board whose checks pass again goes back to idle, the hold is released,
            and the admin gets a notice.
"""
import re
import subprocess
import time

from kotl import slurm as slurm_mod
from kotl import ssh as ssh_mod

PROBE = ('echo "host=$(hostname)"; '
         'echo "card=$(lspci -d 10ee: 2>/dev/null | head -n 1)"; '
         'echo "xdma=$(lsmod 2>/dev/null | grep -o "^xdma ")"; '
         'echo "glibc=$(ldd --version 2>/dev/null | head -n 1)"')
RELOAD = "/usr/local/bin/kotl-xdma-reload"
KEYS = "/usr/local/bin/kotl-keys"


def glibc_line(text):
    """First line of `ldd --version`, e.g. 'ldd (Ubuntu GLIBC 2.39-0ubuntu8.12) 2.39'."""
    return (text or "").strip().splitlines()[0].strip() if (text or "").strip() else ""


def glibc_version(line):
    """The distro's full glibc version from that line ('2.39-0ubuntu8.12'), or the plain version."""
    m = re.search(r"GLIBC ([^)\s]+)\)", line)       # Ubuntu/Debian: the full package version
    if m:
        return m.group(1)
    return line.split()[-1] if line else ""


def local_glibc():
    r = subprocess.run(["ldd", "--version"], capture_output=True, text=True)
    return glibc_version(glibc_line(r.stdout))


def glibc_warning(here, there):
    if not there or there == here:
        return None
    base_here, base_there = here.split("-")[0], there.split("-")[0]
    if base_here != base_there:
        fix = (f"the PC has an older glibc release ({base_there} vs {base_here}), which a package update "
               f"can't close: remove the bundled glibc after infrasetup (deploy/examples/firesim-smoke.sh "
               f"--use-pc-glibc), or bring the PC to the workstation's OS release")
    else:
        fix = "upgrade libc6 on the PC to match, or remove the bundled glibc after infrasetup (--use-pc-glibc)"
    return (f"glibc differs: workstation {here}, PC {there}. FireSim drivers built on the "
            f"workstation won't start on this PC as they are: {fix}")


def probe(board, ssh=ssh_mod):
    """One ssh call: {'host', 'card', 'xdma', 'glibc'}, or {'error': ...} if unreachable."""
    try:
        out = ssh.run(board["host"], ["sh", "-c", PROBE], timeout=30)
    except ssh_mod.SSHError as e:
        return {"error": str(e)}
    found = {}
    for line in out.splitlines():
        if "=" in line:
            k, v = line.split("=", 1)
            found[k.strip()] = v.strip()
    return found


def failures_of(p):
    if "error" in p:
        return [f"unreachable: {p['error']}"]
    out = []
    if not p.get("card"):
        out.append("no Xilinx card on PCI (lspci -d 10ee:)")
    if not p.get("xdma"):
        out.append("XDMA driver not loaded (lsmod)")
    return out


def check_board(board, ssh=ssh_mod, here=None):
    """Failures and warnings for one board, without changing anything."""
    here = here or local_glibc()
    p = probe(board, ssh)
    w = glibc_warning(here, glibc_version(p.get("glibc", ""))) if "error" not in p else None
    return failures_of(p) + ([w] if w else [])


def pc_busy(board, account, ssh=ssh_mod):
    """'' when nothing of the account runs on the PC, else what runs ('screen, sshd x2'), or 'busy'."""
    try:
        out = ssh.run(board["host"], ["sudo", "-n", "-u", account, KEYS, "busy"], timeout=30).strip()
    except ssh_mod.SSHError:
        return ""
    if not out.startswith("busy"):
        return ""
    names = [n.strip() for n in out.split(":", 1)[1].split(",")] if ":" in out else []
    if len(names) > 8:
        return ", ".join(names[:8]) + f" and {len(names) - 8} more"
    return ", ".join(names) or "busy"


def run(registry, ssh=ssh_mod, slurm=slurm_mod, admin="", account="virtex-host", now=time.time, here=None):
    """Check every board, change states, hold or release licenses. Returns {board: [problems]}."""
    here = here or local_glibc()
    found = {}
    for b in registry.boards():
        name = b["name"]
        p = probe(b, ssh)
        fails = failures_of(p)
        notes = []
        if ("error" not in p and any(f.startswith("XDMA") for f in fails)
                and registry.once(f"reload:{name}")):
            try:
                ssh.run(b["host"], ["sudo", "-n", RELOAD], timeout=120)
                notes.append("tried one XDMA driver reload")
            except ssh_mod.SSHError as e:
                notes.append(f"XDMA driver reload failed: {e}")
            p = probe(b, ssh)
            fails = failures_of(p)
        warnings = []
        g = glibc_warning(here, glibc_version(p.get("glibc", ""))) if "error" not in p else None
        if g:
            warnings.append(g)
        running = pc_busy(b, account, ssh) if not fails and b["state"] == "idle" and not b["job_id"] else ""
        if running:
            warnings.append(f"something runs as {account} on the PC with no Kotl job holding the board: {running}")

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
