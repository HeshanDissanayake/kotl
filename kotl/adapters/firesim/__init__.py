"""FireSim adapter: what Kotl needs to know so users can run their own FireSim on a board.

Users run FireSim unchanged inside `kotl run` / `kotl lease`; this adapter only adds:

  checks    XDMA driver loaded (failure); glibc on the PC vs the workstation (warning: drivers
            built here won't start on an older glibc)
  repair    one XDMA reload on an IDLE board (kotl-xdma-reload on the PC, loading it exactly as
            FireSim's infrasetup does, poll_mode=1). Never while a job holds the board: FireSim
            unloads and reloads XDMA itself during infrasetup.
  end step  quit FireSim's screen sessions (fsim*) and stop its drivers (FireSim-*)
  idle      FireSim-* processes count as work for the lease idle guard
  console   `kotl attach` opens screen session fsim0

Its PC part is deploy/adapters/firesim/ (kotl-xdma-reload and its install). Later, admin only:
flash a known-good bitstream, recover a board.
"""
import re
import subprocess

from kotl import ssh as ssh_mod
from kotl.adapters import Adapter

RELOAD = "/usr/local/bin/kotl-xdma-reload"


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


class FireSim(Adapter):
    name = "firesim"
    probe = ('echo "xdma=$(lsmod 2>/dev/null | grep -o "^xdma ")"; '
             'echo "glibc=$(ldd --version 2>/dev/null | head -n 1)"')
    stop_screens = ("fsim",)
    stop_procs = ("FireSim-",)
    work_procs = ("FireSim-",)
    console = "fsim0"
    XDMA = "XDMA driver not loaded (lsmod)"

    def __init__(self, here=None):
        self._here = here

    @property
    def here(self):
        if self._here is None:
            self._here = local_glibc()
        return self._here

    def failures(self, p):
        return [] if p.get("xdma") else [self.XDMA]

    def warnings(self, p):
        w = glibc_warning(self.here, glibc_version(p.get("glibc", "")))
        return [w] if w else []

    def repair(self, board, ssh, failures):
        if self.XDMA not in failures:
            return None
        try:
            ssh.run(board["host"], ["sudo", "-n", RELOAD], timeout=120)
            return "tried one XDMA driver reload"
        except ssh_mod.SSHError as e:
            return f"XDMA driver reload failed: {e}"
