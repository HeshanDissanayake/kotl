#!/bin/sh
# Example: a FireSim run with a verdict Kotl can read. Run it from your FireSim deploy/ folder:
#
#   kotl run --eta 30m -- ~/working_dir/kotl/deploy/examples/firesim-smoke.sh config_runtime_kotl_smoke.yaml
#
# It sets up the board, runs the workload, then prints KOTL RESULT: PASS only if the
# simulated Linux really powered off (FireSim reports "completed" even when its driver
# fails to start, so the exit code alone isn't enough).
set -u
CFG=${1:?usage: firesim-smoke.sh RUNTIME_CONFIG}
firesim infrasetup -c "$CFG" || { echo "KOTL RESULT: FAIL (infrasetup)"; exit 1; }
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
