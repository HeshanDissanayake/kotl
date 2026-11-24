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

if ask "1. Update Kotl here (sudo) with the FireSim adapter switched on (adapters = firesim)"; then
  step "sudo deploy/kotl/install.sh --adapters firesim --board vcu118-pc1=vcu118@vcu118-pc1" &&
  step "grep -E '^adapters' /etc/kotl/kotl.conf"
fi

if ask "2. Update the PC (sudo there): the generic kotl-keys, and the FireSim adapter's PC part"; then
  step "scp deploy/pc/setup.sh deploy/pc/kotl-keys deploy/adapters/firesim/pc-setup.sh deploy/adapters/firesim/kotl-xdma-reload $PC:/tmp/" &&
  step "ssh -t $PC 'sudo bash /tmp/setup.sh --keys-helper /tmp/kotl-keys && sudo bash /tmp/pc-setup.sh && rm /tmp/setup.sh /tmp/kotl-keys /tmp/pc-setup.sh /tmp/kotl-xdma-reload'"
fi

if ask "3. Check the board with the adapter (as admin; read-only on the PC)"; then
  step "kotl board check"
fi

if ask "4. Run kotl setup for yourself (Claude plugins + VS Code extension; no sudo)"; then
  step "kotl setup"
fi

log "=== next.sh finished"
echo
echo "Done. Everything is in .kotl/next.log, and Claude sees it with your next message."
echo "Then start a NEW Claude Code session in a fresh terminal and try it (deploy/NEXT.md step 3)."
