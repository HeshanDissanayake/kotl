#!/usr/bin/env bash
# managed by kotl (deploy/uninstall.sh)
# Remove Kotl completely: every board's PC, then the workstation, each part's --undo in the
# reverse order of installing. Run as the admin (not with sudo: it asks for sudo itself).
#
#   bash deploy/uninstall.sh            removes Kotl; keeps the job history and results
#                                       (/var/lib/kotl, /srv/kotl), the kotl account and its key,
#                                       and Slurm's packages and accounting database
#   bash deploy/uninstall.sh --purge    also those: nothing of Kotl is left
#   bash deploy/uninstall.sh --keep-pcs leaves the PCs as they are (e.g. one is unreachable)
#
# Order: PCs (pc.sh undo), the Kotl code and services (kotl/install.sh --undo), Kotl's SSH
# (ssh/setup-kotl-key.sh --undo), Slurm (slurm/install.sh --undo), accounts and folders
# (accounts.sh --undo). Files Kotl replaced are put back from their .kotl-orig copies.
# It asks you to type "uninstall" first. Add --dry-run to print what it would run.
set -uo pipefail
DEPLOY=$(cd "$(dirname "$0")" && pwd)
DRY=0 PURGE=() KEEP_PCS=0 PCARGS=()
say() { printf 'kotl-uninstall: %s\n' "$*"; }
die() { printf 'kotl-uninstall: error: %s\n' "$*" >&2; exit 1; }
run() { if [ "$DRY" = 1 ]; then printf 'would run: %s\n' "$*"; else "$@"; fi; }

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1; PCARGS+=(--dry-run) ;;
    --purge) PURGE=(--purge) ;;
    --keep-pcs) KEEP_PCS=1 ;;
    --login) PCARGS+=(--login "${2:-}"); shift ;;
    -h|--help) sed -n '3,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown option $1" ;;
  esac
  shift
done
[ "$(id -u)" != 0 ] || [ "$DRY" = 1 ] || die "run it as yourself, not as root: it uses sudo where it needs it"

if [ "$DRY" != 1 ]; then
  running=$(squeue -h -o '%i %u %j' 2>/dev/null | awk '$3 ~ /^kotl-/')
  [ -z "$running" ] || die "Kotl jobs are queued or running; wait for them, or cancel your own:
$running"
  printf 'This removes Kotl from this workstation%s%s. Type "uninstall" to go on: ' \
    "$([ "$KEEP_PCS" = 1 ] || echo " and every board's PC")" "$([ ${#PURGE[@]} -gt 0 ] && echo ", with all its data (--purge)")"
  read -r answer
  [ "$answer" = uninstall ] || die "stopped; nothing changed"
fi

fails=0
step() { say "$1"; shift; run "$@" || { say "  that step failed (above); going on"; fails=$((fails + 1)); }; }
if [ "$KEEP_PCS" = 1 ]; then say "1/5 leaving the PCs as they are (--keep-pcs)"; else
  say "1/5 every board's PC"     # pc.sh previews itself in a dry run
  bash "$DEPLOY/kotl/pc.sh" undo "${PCARGS[@]}" || { say "  that step failed (above); going on"; fails=$((fails + 1)); }; fi
step "2/5 Kotl's code and services" sudo bash "$DEPLOY/kotl/install.sh" --undo
step "3/5 Kotl's SSH to the PCs" sudo bash "$DEPLOY/ssh/setup-kotl-key.sh" --undo "${PURGE[@]}"
step "4/5 Slurm" sudo bash "$DEPLOY/slurm/install.sh" --undo "${PURGE[@]}"
step "5/5 accounts and folders" sudo bash "$DEPLOY/accounts.sh" --undo "${PURGE[@]}"
echo
if [ "$fails" -gt 0 ]; then say "done, but $fails step(s) failed (above); re-run to retry them"; exit 1; fi
[ "$DRY" = 1 ] && { say "dry run: nothing changed"; exit 0; }
say "Kotl is uninstalled$([ ${#PURGE[@]} -gt 0 ] && echo ", with its data" || echo "; its data stays (--purge removes it)")"
say "users' own setups: each person runs 'kotl setup --undo' before this, or removes the 'kotl'"
say "plugins in Claude Code (/plugin) and the Kotl extension in VS Code by hand afterwards"
