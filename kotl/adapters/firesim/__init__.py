"""FireSim adapter: what Kotl needs to know so users can run their own FireSim on a board.

Users run FireSim unchanged inside `kotl run` / `kotl lease`; this adapter only adds:

  checks    XDMA driver loaded (failure); glibc on the PC vs the workstation (warning: drivers
            built here won't start on an older glibc)
  repair    one XDMA reload on an IDLE board (kotl-xdma-reload on the PC, loading it exactly as
            FireSim's infrasetup does, poll_mode=1). Never while a job holds the board: FireSim
            unloads and reloads XDMA itself during infrasetup.
  end step  quit FireSim's screen sessions (fsim*) and stop its drivers (FireSim-*); then, as root,
            kotl-firesim-stop: FireSim starts its driver through sudo, so the driver runs as
            root and the board account can't stop it. Both stop only what started during the
            job (the job's age is passed); older FireSim work on the PC isn't the job's: it is
            left running and reported (who, how long, outside Kotl)
  idle      FireSim-* processes count as work for the lease idle guard
  console   `kotl attach` opens screen session fsim0
  notes     a job whose command mentions firesim is a FireSim run: when it ends, its line in the
            lab notes (firesim/runs.md) carries the FireSim and Chipyard commits, the hardware
            config, its bitstream and the workload, read from the user's FireSim (FACTS, run as
            the user). The pages start from SEED until someone writes them

Its PC part is deploy/adapters/firesim/ (kotl-xdma-reload, kotl-firesim-stop and their install). Later, admin only:
flash a known-good bitstream, recover a board.
"""
import re
import subprocess

from kotl import ssh as ssh_mod
from kotl.adapters import Adapter

RELOAD = "/usr/local/bin/kotl-xdma-reload"

# run as the user in the job's folder when a FireSim run ends: key=value lines for runs.md
FACTS = r"""
echo tool=firesim
fs=$(command -v firesim 2>/dev/null) || exit 0
dep=$(cd "$(dirname "$(readlink -f "$fs")")" 2>/dev/null && pwd) || exit 0
ver() {
  c=$(git -C "$1" rev-parse --short=10 HEAD 2>/dev/null) || return 1   # read-only: no index refresh
  git --no-optional-locks -C "$1" diff --quiet --ignore-submodules HEAD 2>/dev/null || c="$c+changes"
  echo "$c"
}
v=$(ver "$dep/..") && echo "firesim=$v"
cy=$(git -C "$dep/.." rev-parse --show-superproject-working-tree 2>/dev/null)
[ -n "$cy" ] && v=$(ver "$cy") && echo "chipyard=$v"
# a FireSim config given in the command (-c/--runtimeconfigfile, -a/--hwdbconfigfile: *.yaml)
arg() {
  set -f; set -- $KOTL_COMMAND; set +f
  while [ $# -gt 1 ]; do
    case "$1" in "$A"|"$B") case "$2" in *.yaml|*.yml) echo "$2"; return ;; esac ;; esac
    shift
  done
}
val() { sed -n "s/^[[:space:]]*$1:[[:space:]]*//p" "$2" 2>/dev/null | sed 's/[[:space:]]*#.*//; s/["'"'"']//g' | head -n 1; }
A=-c B=--runtimeconfigfile rt=$(arg); rt=${rt:-$dep/config_runtime.yaml}
A=-a B=--hwdbconfigfile hwdb=$(arg); hwdb=${hwdb:-$dep/config_hwdb.yaml}
[ "$rt" = "$dep/config_runtime.yaml" ] || echo "runtime_config=$rt"
hw=$(val default_hw_config "$rt"); [ -n "$hw" ] && echo "hw_config=$hw"
wl=$(val workload_name "$rt"); [ -n "$wl" ] && echo "workload=$wl"
if [ -n "$hw" ]; then
  bit=$(awk -v h="$hw:" '$1 == h { f = 1; next } f && /^[^[:space:]#]/ { f = 0 }
                         f && $1 == "bitstream_tar:" { print $2; exit }' "$hwdb" 2>/dev/null)
  bit=${bit#file://}
  [ -n "$bit" ] && echo "bitstream=$(basename "$(dirname "$bit")")"
fi
true
"""

SEED = {
    "setup.md": """# FireSim: setup

What the boards' PCs have for FireSim, and what a run needs. Correct it when something changes:
kotl notes set firesim setup.md < file (the old page is kept in .history/).

## Every board's PC (Kotl's health check watches these)

- XDMA driver loaded, poll_mode=1 (Kotl reloads it on an idle board if it's missing)
- xvsec driver and xvsecctl, to flash the bitstream (what FireSim's infrasetup does)
- the board account can use sudo without a password (FireSim runs its driver through sudo)
- glibc: `kotl board list` warns when the PC's differs from the workstation's; then remove
  FireSim's bundled glibc on the PC after infrasetup (/opt/kotl/adapters/firesim/firesim-smoke.sh
  --use-pc-glibc)

## Not written yet

- the boards (type, PC, shell/bitstream flashed at boot)
- the Vivado, XDMA and FireSim versions the PCs are set up for
- the lab's FireSim test package (a known-good bitstream and driver): where it is
""",
    "compatible.md": """# FireSim: what works together

Known-good combinations on these boards (FireSim and Chipyard commits, hardware config and
bitstream, driver, workload), and known-bad ones with the symptom. The latest runs are in
runs.md: each line has what that run used. Correct this page with
kotl notes set firesim compatible.md < file.

## Known good

(none written yet: see the ok lines in runs.md)

## Known bad

(none written yet)

## Watch out: the FireSim version

The board's PC was set up (XDMA driver, poll_mode=1, xvsec) for one FireSim version. A design
built with a much newer or older FireSim may expect another XDMA driver, and nothing checks
that before the run: it shows as a flash or driver-start failure. Compare the run's firesim=
commit with the ok lines in runs.md; the first run on a new FireSim version, pass or fail,
belongs in this page.
""",
}
STOP = "/usr/local/bin/kotl-firesim-stop"


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
               f"can't close: remove the bundled glibc after infrasetup (/opt/kotl/adapters/firesim/firesim-smoke.sh "
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
    title = "FireSim"
    notes_seed = SEED
    facts = FACTS

    def is_run(self, command):
        return bool(re.search(r"firesim", command, re.I))

    def end_commands(self, age):
        return [["sudo", "-n", STOP] + ([str(int(age))] if age is not None else [])]
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
