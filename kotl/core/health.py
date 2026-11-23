"""Health checks for each board's PC. Runs as kotl: from Slurm every 5 minutes (health.sh),
or by the admin with `kotl board check`.

Checks so far:
  reachable   kotl can log in to the PC
  glibc       the PC's glibc is the workstation's: FireSim bundles the workstation's libc.so.6
              with its driver, and the PC's own loader can't start it if the versions differ
              (seen in job 47: "undefined symbol: __tunable_is_initialized, version GLIBC_PRIVATE")

A failed check becomes a warning on the board (kotl board list, kotl top). It doesn't take
the board out of the pool: jobs that don't use FireSim's driver still work. M4 adds the checks
that mark a board down (PCI card, driver, leftover work).
"""
import subprocess
import time

from kotl import ssh as ssh_mod


def glibc_line(text):
    """First line of `ldd --version`, e.g. 'ldd (Ubuntu GLIBC 2.39-0ubuntu8.12) 2.39'."""
    return (text or "").strip().splitlines()[0].strip() if (text or "").strip() else ""


def glibc_version(line):
    """The distro's full glibc version from that line ('2.39-0ubuntu8.12'), or the line itself."""
    import re
    m = re.search(r"GLIBC ([^)\s]+)\)", line)       # Ubuntu/Debian: the full package version
    if m:
        return m.group(1)
    return line.split()[-1] if line else ""           # elsewhere: the plain version number


def local_glibc():
    r = subprocess.run(["ldd", "--version"], capture_output=True, text=True)
    return glibc_version(glibc_line(r.stdout))


def check_board(board, ssh=ssh_mod, here=None):
    """Returns a list of warnings for one board (empty when healthy)."""
    here = here or local_glibc()
    try:
        there = glibc_version(glibc_line(ssh.run(board["host"], ["ldd", "--version"], timeout=20)))
    except ssh_mod.SSHError as e:
        return [f"unreachable: {e}"]
    if there != here:
        return [f"glibc differs: workstation {here}, PC {there}. FireSim drivers built on the "
                f"workstation won't start on this PC: upgrade libc6 on the PC to match, or remove the bundled "
                f"glibc after infrasetup (deploy/examples/firesim-smoke.sh --use-pc-glibc)"]
    return []


def run(registry, ssh=ssh_mod, now=time.time):
    """Check every board; store the warnings. Returns {board: [warnings]}."""
    here = local_glibc()
    found = {}
    for b in registry.boards():
        warnings = check_board(b, ssh, here)
        registry.set_warnings(b["name"], warnings, healthy_at=None if any(w.startswith("unreachable") for w in warnings) else now())
        found[b["name"]] = warnings
    return found
