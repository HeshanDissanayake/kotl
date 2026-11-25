#!/usr/bin/env bash
# managed by kotl (deploy/kotl/install.sh, as /opt/kotl/adapters/firesim/run-package.sh)
# Run a FireSim run package (made by kotl-firesim-pack) on the board Kotl gave this job. Needs no
# FireSim, Chipyard or conda here: it does what FireSim's infrasetup and runworkload do on the
# board's PC, with only your job's key (KOTL_PC, set by Kotl inside the job):
#
#   kotl run --eta 20m -- /opt/kotl/adapters/firesim/run-package.sh PACKAGE [--timeout 30m] [--keep]
#
#   1. checks the board's PC: Xilinx card, XDMA (poll_mode=1), xvsec, xvsecctl, sudo, its glibc
#      against what the driver needs, and FireSim running outside Kotl (never stopped: reported)
#   2. copies the package's payload to the PC (~/kotl-run-JOB)
#   3. flashes the FPGA with its bitstream (sudo xvsecctl)
#   4. runs the driver in screen session fsim0 with its arguments (kotl attach shows the console)
#   5. waits for it to end (or --timeout), copies back uartlog and what the run wrote
#   6. removes its folder on the PC (--keep leaves it), prints KOTL RESULT from the uartlog
#      (run.conf's PASS_RE / FAIL_RE), and KOTL FACT lines from the MANIFEST for the lab notes
#
# Results: ./firesim-results/JOB/ (KOTL_RUN_OUT changes it), and in the job's outputs
# (kotl fetch JOB brings them back, e.g. to your own PC).
set -uo pipefail
PKG=${1:-}
[ -n "$PKG" ] && [ "${PKG#-}" = "$PKG" ] || { echo "usage: $0 PACKAGE [--timeout 30m] [--keep]"; echo "KOTL RESULT: FAIL (no package given)"; exit 2; }
shift
KEEP=0 TIMEOUT_ARG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --timeout) TIMEOUT_ARG=${2:-}; shift ;;
    --keep) KEEP=1 ;;
    *) echo "KOTL RESULT: FAIL (unknown option $1)"; exit 2 ;;
  esac
  shift
done
JOB=${KOTL_JOB:-manual-$$}
DIR="kotl-run-$JOB"                       # on the PC, in the board account's home
read -r -a LAUNCH <<<"${KOTL_LAUNCH:-sudo -n -u kotl /opt/kotl/launch}"
step() { echo; echo "== $(date +%H:%M:%S) $*"; }
fail() { echo "KOTL RESULT: FAIL ($*)"; exit 1; }
pc() { ssh -o BatchMode=yes -o ConnectTimeout=15 "$KOTL_PC" "$@"; }
secs() { case "$1" in *h) echo $(( ${1%h} * 3600 )) ;; *m) echo $(( ${1%m} * 60 )) ;; *s) echo "${1%s}" ;; *) echo $(( $1 * 60 )) ;; esac; }

[ -n "${KOTL_PC:-}" ] || fail "run me inside a Kotl job: kotl run --eta 20m -- $0 $PKG"
PKG=$(cd "$PKG" 2>/dev/null && pwd) || fail "no package folder ${1:-$PKG} on this machine (copy it here first)"
[ -f "$PKG/run.conf" ] && [ -f "$PKG/payload/bitstream/firesim.bit" ] && [ -d "$PKG/payload/sim" ] ||
  fail "$PKG isn't a run package (make one with kotl-firesim-pack)"
DRIVER="" SIM_ARGS="" PROGS="" RUNTIME_CONF="" GLIBC_NEED="" TIMEOUT=1800 PASS_RE="" FAIL_RE=""
. "$PKG/run.conf"
[ -n "$TIMEOUT_ARG" ] && TIMEOUT=$(secs "$TIMEOUT_ARG")
case "$DRIVER" in FireSim-*) ;; *) fail "run.conf: odd driver name '$DRIVER'" ;; esac
[ -f "$PKG/payload/sim/$DRIVER" ] || fail "the package has no driver $DRIVER"
rconf=""      # the hwdb's custom runtime config: its plusargs, one line (as FireSim's sed does)
[ -n "$RUNTIME_CONF" ] && rconf=$(tr '\n' ' ' <"$PKG/payload/sim/$RUNTIME_CONF")
for v in "$SIM_ARGS" "$PROGS" "$rconf"; do   # they go into a remote shell line: plusargs only
  case "$v" in *[!A-Za-z0-9_+=:./,@%\ -]*) fail "run.conf: unexpected characters in the driver's arguments: $v" ;; esac
done
OUT=${KOTL_RUN_OUT:-$PWD/firesim-results/$JOB}
mkdir -p "$OUT" || fail "can't write results to $OUT (run from a folder you can write to, or set KOTL_RUN_OUT)"

# what this run is, for the lab notes (kotl notes firesim: runs.md)
sed -n 's/^fact: \([a-z][a-z0-9_]*=.*\)$/KOTL FACT: \1/p' "$PKG/MANIFEST" 2>/dev/null

step "1/6 checking the board's PC ($KOTL_PC)"
PC_CHECK=$(cat <<'EOF'
set -e
need=$1
card=$(lspci -nd 10ee: | head -n 1)
[ -n "$card" ] || { echo "no Xilinx card on PCI"; exit 1; }
echo "card: $card"
if screen -ls 2>/dev/null | grep -q '\.fsim0'; then
  echo "OUTSIDE KOTL: FireSim is already running on the PC, and it isn't this job:"
  screen -ls 2>/dev/null | grep '\.fsim' | awk '{print "  screen " $1}'
  ps -eo user,etime,comm 2>/dev/null | awk '$3 ~ /^FireSim-/ { print "  driver running for " $2 " (as " $1 ")" }'
  echo "BUSY-OUTSIDE"
  exit 1
fi
lsmod | grep -q '^xdma ' || { echo "the XDMA driver isn't loaded (Kotl's health check reloads it on an idle board)"; exit 1; }
pm=$(cat /sys/module/xdma/parameters/poll_mode 2>/dev/null || echo unknown)
[ "$pm" = 1 ] || { echo "XDMA is loaded with poll_mode=$pm; FireSim needs 1 (admin: sudo /usr/local/bin/kotl-xdma-reload on an idle board)"; exit 1; }
lsmod | grep -q '^xvsec ' || { echo "the xvsec driver isn't loaded (needed to flash the FPGA)"; exit 1; }
command -v xvsecctl >/dev/null || { echo "xvsecctl isn't installed on the PC"; exit 1; }
sudo -n true 2>/dev/null || { echo "the board account can't use sudo without a password (FireSim needs it)"; exit 1; }
have=$(ldd --version 2>/dev/null | head -n 1 | awk '{print $NF}')
if [ -n "$need" ] && [ -n "$have" ] && [ "$(printf '%s\n%s\n' "$need" "$have" | sort -V | head -n 1)" != "$need" ]; then
  echo "the driver needs glibc $need; this PC has $have. Build the driver on a system with glibc $have or older (kotl notes firesim: setup.md)"
  exit 1
fi
echo "ok: XDMA poll_mode=1, xvsec, xvsecctl, sudo, glibc $have (the driver needs ${need:-any})"
EOF
)
check=$(pc bash -s -- "$GLIBC_NEED" <<<"$PC_CHECK" 2>&1); ok=$?
echo "$check" | grep -v '^BUSY-OUTSIDE$'
if [ $ok -ne 0 ]; then
  if echo "$check" | grep -q '^BUSY-OUTSIDE$'; then
    echo "  Kotl leaves it running. Ask its owner to use kotl run / kotl lease, then run this again."
    fail "FireSim is running on the board outside Kotl"
  fi
  fail "the board's PC isn't ready (see above)"
fi

step "2/6 copying the package to the PC (~/$DIR, $(du -sh "$PKG/payload" | cut -f1))"
tar -C "$PKG/payload" -cf - . | pc "rm -rf '$DIR' && mkdir -p '$DIR' && tar -C '$DIR' -xf -" || fail "copying to the PC"
cleanup() {
  [ "$KEEP" = 1 ] && { echo "keeping ~/$DIR on the PC (--keep)"; return; }
  pc "rm -rf '$DIR'" && echo "removed ~/$DIR on the PC"
}

step "3/6 flashing the FPGA"
pc "cd '$DIR' && set -- \$(lspci -nd 10ee: | head -n 1) && bdf=\$1 && bus=\${bdf%%:*} && dev=\${bdf#*:} && dev=\${dev%%.*} &&
    sudo xvsecctl -b 0x\$bus -F 0x\$dev -c 0x1 -p bitstream/firesim.bit" || { cleanup; fail "flashing the FPGA"; }

step "4/6 starting the simulation (screen fsim0; watch it with: kotl attach)"
pc "cd '$DIR/sim' && chmod +x '$DRIVER' && set -- \$(lspci -nd 10ee: | head -n 1) && bdf=\$1 && id=\$3 && bus=\${bdf%%:*} && rest=\${bdf#*:} && dev=\${rest%%.*} && fn=\${bdf##*.} &&
    screen -S fsim0 -d -m bash -c \"script -f -c 'stty intr ^] && sudo ./$DRIVER +permissive $rconf $SIM_ARGS +domain=0x0000 +bus=0x\$bus +device=0x\$dev +function=0x\$fn +bar=0x0 +pci-vendor=0x10ee +pci-device=0x\${id#*:} +permissive-off $PROGS && stty intr ^c' uartlog\" && sleep 2 &&
    screen -ls | grep -q '\.fsim0'" || { cleanup; fail "starting the FireSim driver"; }

step "5/6 waiting for the simulation to end (up to $((TIMEOUT / 60)) min)"
start=$(date +%s); last="" timed_out=0
while pc "screen -ls 2>/dev/null | grep -q '\.fsim0'"; do
  now=$(date +%s)
  line=$(pc "tail -n 1 '$DIR/sim/uartlog' 2>/dev/null" | tr -d '\r' | cut -c1-120)
  [ -n "$line" ] && [ "$line" != "$last" ] && { echo "  [$((now - start))s] $line"; last=$line; }
  if [ $((now - start)) -ge "$TIMEOUT" ]; then
    echo "  time limit reached: stopping the simulation"
    pc "screen -S fsim0 -X quit; sudo pkill -f '$DRIVER' || true"
    timed_out=1
    break
  fi
  sleep "${KOTL_RUN_POLL:-10}"
done
# what the run wrote: everything in the sim folder that the package didn't bring
( cd "$PKG/payload/sim" && find . -type f | sed 's#^\./##' ) | sort >"$OUT/.inputs"
pc "cd '$DIR/sim' && find . -maxdepth 1 -type f -size -200M | sed 's#^\./##'" | sort | comm -13 "$OUT/.inputs" - >"$OUT/.outputs"
while read -r f; do
  case "$f" in *[!A-Za-z0-9._-]*|"") continue ;; esac
  pc "cat '$DIR/sim/$f'" >"$OUT/$f" 2>/dev/null || rm -f "$OUT/$f"
  [ -s "$OUT/$f" ] && "${LAUNCH[@]}" put "$JOB" "$f" <"$OUT/$f" 2>/dev/null
done <"$OUT/.outputs"
rm -f "$OUT/.inputs" "$OUT/.outputs"
cleanup

step "6/6 result"
echo "--- uartlog (last lines): $OUT/uartlog (and: kotl fetch $JOB)"
tail -n 8 "$OUT/uartlog" 2>/dev/null | tr -d '\r'
if [ -n "$FAIL_RE" ] && grep -aqsE "$FAIL_RE" "$OUT/uartlog"; then
  fail "the uartlog has a failure line: $(grep -aoE "$FAIL_RE" "$OUT/uartlog" | head -n 1)"
elif [ "$timed_out" = 1 ]; then
  fail "the time limit ($((TIMEOUT / 60)) min) was reached; see $OUT/uartlog"
elif grep -aqsE "${PASS_RE:-reboot: Power down}" "$OUT/uartlog"; then
  echo "KOTL RESULT: PASS"
else
  fail "the simulation ended without a pass line ($PASS_RE); see $OUT/uartlog"
fi
