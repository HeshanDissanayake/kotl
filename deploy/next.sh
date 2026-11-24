#!/usr/bin/env bash
# The steps Claude needs from you right now. Run from anywhere:  bash ~/working_dir/kotl/deploy/next.sh
# It asks before each step; answer n to skip one. deploy/NEXT.md explains each step.
# Everything is logged to .kotl/next.log (time, your answers, all output, exit codes), so Claude
# can see what ran without you telling it. Passwords you type are never shown, so never logged.
set -u
cd "$(dirname "$0")/.." || exit 1
PC=virtex-host@192.168.1.2
LOG=.kotl/next.log
mkdir -p .kotl

log() { printf '%s %s\n' "$(date '+%F %T')" "$*" >>"$LOG"; }
ask() {
  printf '\n== %s\n   run it? [y/N] ' "$1"; read -r a
  if [ "$a" = y ] || [ "$a" = Y ]; then log "STEP $1: yes"; return 0; fi
  log "STEP $1: skipped"; return 1
}
# step 'commands': run them in a recorded terminal, so prompts and colours still work
step() {
  script -q -e -a -c "$1" "$LOG"; rc=$?
  log "  -> exit $rc"
  return $rc
}

log "=== next.sh started by $(id -un) (deploy/next.sh $(git rev-parse --short HEAD 2>/dev/null))"

if ask "1. Look (read-only): what FireSim runs on the PC now, and what job 68's end step did"; then
  step "ssh $PC 'echo \"screens:\"; screen -ls 2>&1 | grep fsim || echo \"  none\"; echo \"FireSim drivers:\"; ps -eo user,etime,args | grep \"[F]ireSim-\" | cut -c1-110 || echo \"  none\"'"
  step "mkdir -p /research/$USER/kotl-test-runs && cd /research/$USER/kotl-test-runs && kotl fetch 68 >/dev/null && tail -n 8 kotl-results/68/launcher.log"
fi

if ask "2. Run the FireSim test package again (about 5-15 min; the board is busy meanwhile)"; then
  step "cd /research/$USER/kotl-test-runs && kotl run --eta 15m -- /research/$USER/kotl-firesim-test/run.sh"
fi

if ask "3. Update Kotl here (sudo; small: the client installer's backup copy)"; then
  step "sudo deploy/kotl/install.sh --adapters firesim --board vcu118-pc1=vcu118@vcu118-pc1"
fi

log "=== next.sh finished"
echo
echo "Done. Everything is in .kotl/next.log, and Claude sees it with your next message."
echo "Then start a NEW Claude Code session in a fresh terminal and try it (deploy/NEXT.md step 3)."
