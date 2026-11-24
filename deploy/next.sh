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

if ask "1. Update to Kotl 1.0.0 everywhere (sudo here, then the sudo password on the PC)"; then
  step "bash deploy/kotl/update.sh"
fi

if ask "2. Test PC onboarding on the board you have: re-add vcu118-pc1 (safe: it only re-applies)"; then
  step "bash deploy/kotl/pc.sh add vcu118-pc1 vcu118 192.168.1.2"
fi

if ask "3. Preview a full uninstall (dry run: changes nothing)"; then
  step "bash deploy/uninstall.sh --dry-run"
fi

if ask "4. Your VS Code extension: kotl setup (then reload the VS Code window)"; then
  step "kotl version && kotl setup"
fi

log "=== next.sh finished"
echo
echo "Done. Everything is in .kotl/next.log, and Claude sees it with your next message."
echo "Kotl 1.0.0. Updates from now on: bash deploy/kotl/update.sh"
