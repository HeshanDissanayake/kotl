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

if ask "1. Update kotl-xdma-reload on the PC (sudo there) and Kotl here (sudo)"; then
  step "scp deploy/pc/setup.sh deploy/pc/kotl-keys deploy/pc/kotl-xdma-reload $PC:/tmp/" &&
  step "ssh -t $PC 'sudo bash /tmp/setup.sh --keys-helper /tmp/kotl-keys --driver-helper /tmp/kotl-xdma-reload && rm /tmp/setup.sh /tmp/kotl-keys /tmp/kotl-xdma-reload'" &&
  step "sudo deploy/kotl/install.sh --board vcu118-pc1=vcu118@vcu118-pc1"
fi

if ask "2. Show how XDMA is loaded on the PC now (read-only)"; then
  step "ssh $PC 'lsmod | grep ^xdma; echo poll_mode=\$(cat /sys/module/xdma/parameters/poll_mode 2>/dev/null || echo not-loaded)'"
fi

if ask "3. Reload XDMA the way FireSim does (sudo on the PC; ONLY if nobody is running FireSim)"; then
  step "ssh -t $PC 'sudo /usr/local/bin/kotl-xdma-reload'"
fi

if ask "4. Check this terminal can reach Kotl (needs the kotl-users group)"; then
  step "id -nG | tr ' ' '\\n' | grep -x kotl-users || echo 'NOT in kotl-users here: restart tmux (tmux kill-server) or log in again'" &&
  step "kotl board list"
fi

log "=== next.sh finished"
echo
echo "Done. Everything is in .kotl/next.log, and Claude sees it with your next message."
echo "Then start a NEW Claude Code session in a fresh terminal and try it (deploy/NEXT.md step 3)."
