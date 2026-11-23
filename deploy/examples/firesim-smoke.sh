#!/bin/sh
# Example: a FireSim run with a verdict Kotl can read. Run it from your FireSim deploy/ folder:
#
#   kotl run --eta 30m -- ~/working_dir/kotl/deploy/examples/firesim-smoke.sh [--use-pc-glibc] config_runtime_kotl_smoke.yaml
#
# --use-pc-glibc: after infrasetup, delete the glibc libraries FireSim bundled from the
#   workstation, so the driver uses the PC's own glibc (the fix when their versions differ).
#   It reaches the PC with the job's own key: ssh "$KOTL_PC" (set by Kotl inside the job).
#
# It sets up the board, runs the workload, then prints KOTL RESULT: PASS only if the
# simulated Linux really powered off (FireSim reports "completed" even when its driver
# fails to start, so the exit code alone isn't enough).
set -u
PC_GLIBC=0
[ "${1:-}" = --use-pc-glibc ] && { PC_GLIBC=1; shift; }
CFG=${1:?usage: firesim-smoke.sh [--use-pc-glibc] RUNTIME_CONFIG}
firesim infrasetup -c "$CFG" || { echo "KOTL RESULT: FAIL (infrasetup)"; exit 1; }
if [ "$PC_GLIBC" = 1 ]; then
  simdir=$(sed -n 's/^ *default_simulation_dir: *//p' "$CFG" | head -n 1)
  [ -n "$simdir" ] && [ -n "${KOTL_PC:-}" ] || { echo "KOTL RESULT: FAIL (no simulation dir or KOTL_PC)"; exit 1; }
  echo "kotl-example: using the PC's own glibc: removing the bundled copies in $simdir/sim_slot_0"
  ssh -o BatchMode=yes "$KOTL_PC" "cd '$simdir/sim_slot_0' && rm -v -f libc.so.6 libm.so.6 libpthread.so.0 libdl.so.2 librt.so.1" \
    || { echo "KOTL RESULT: FAIL (could not remove the bundled glibc)"; exit 1; }
fi
firesim runworkload -c "$CFG" || { echo "KOTL RESULT: FAIL (runworkload)"; exit 1; }
run=$(ls -td results-workload/*/ | head -n 1)
for u in "$run"*/uartlog; do
  echo "--- $u (last lines)"
  tail -n 5 "$u"
done
if grep -aqs "reboot: Power down" "$run"*/uartlog; then
  echo "KOTL RESULT: PASS"
else
  echo "KOTL RESULT: FAIL (the simulated Linux did not power off; see the uartlog above)"
  exit 1
fi
