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

if ask "0. Show what runs as virtex-host on the PC (read-only)"; then
  step "ssh $PC 'ps -u virtex-host -o pid,etime,cmd --sort=start_time'"
fi

if ask "0b. Update kotl-keys on the PC (sudo there), then Kotl on the workstation (sudo here)"; then
  step "scp deploy/pc/setup.sh deploy/pc/kotl-keys $PC:/tmp/" &&
  step "ssh -t $PC 'sudo bash /tmp/setup.sh --keys-helper /tmp/kotl-keys && rm /tmp/setup.sh /tmp/kotl-keys'" &&
  step "sudo deploy/kotl/install.sh --board vcu118-pc1=vcu118@vcu118-pc1"
fi

if ask "2. Driver-failure test: unload XDMA on the PC on purpose (only when nobody runs FireSim)"; then
  step "ssh -t $PC 'sudo modprobe -r xdma; echo xdma modules loaded now: \$(lsmod | grep -c ^xdma)'"
  echo "Kotl's next health check (within 5 minutes) should reload it once. Tell Claude."
fi

log "=== next.sh finished"
echo
echo "Done. Everything is in .kotl/next.log, and Claude sees it with your next message."
echo "Add \"ok PC\" to that message if Claude may run its own two short tests (deploy/NEXT.md step 1)."
