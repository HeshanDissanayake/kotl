#!/usr/bin/env bash
# managed by kotl (deploy/kotl/update.sh)
# Update Kotl everywhere from this repo, in one go. Run as the admin (not with sudo: it asks for
# sudo itself, here and on each PC), from the repo you want to install:
#
#   bash deploy/kotl/update.sh                 the workstation, then every board's PC
#   bash deploy/kotl/update.sh --no-pc         the workstation only
#   bash deploy/kotl/update.sh --login USER    log in to the PCs as USER (someone with sudo there)
#
# The workstation: deploy/kotl/install.sh with no options, which rebuilds and reinstalls all of
# Kotl (code, kotl command, daemon, notifier, plugins, VS Code extension, Claude rules) and keeps
# the boards and adapters already set. Then each PC: deploy/kotl/pc.sh update (Kotl's helpers and
# every enabled adapter's). Users: Claude Code loads the new plugins at its next session by itself
# (they are read from /opt/kotl); VS Code asks them to run kotl setup for the new extension; on
# their own PCs, Claude Code and VS Code ask for a new client bundle.
#
# Add --dry-run to print what it would run, changing nothing.
set -uo pipefail
DEPLOY=$(cd "$(dirname "$0")/.." && pwd)
REPO=$(cd "$DEPLOY/.." && pwd)
DRY=0 DO_PC=1 PCARGS=()
say() { printf 'kotl-update: %s\n' "$*"; }
die() { printf 'kotl-update: error: %s\n' "$*" >&2; exit 1; }
run() { if [ "$DRY" = 1 ]; then printf 'would run: %s\n' "$*"; else "$@"; fi; }

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1; PCARGS+=(--dry-run) ;;
    --no-pc) DO_PC=0 ;;
    --login) PCARGS+=(--login "${2:-}"); shift ;;
    -h|--help) sed -n '3,16p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown option $1" ;;
  esac
  shift
done
[ "$(id -u)" != 0 ] || [ "$DRY" = 1 ] || die "run it as yourself, not as root: it uses sudo where it needs it"

rev=$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo "?")
ver=$(sed -n 's/^__version__ = "\(.*\)"/\1/p' "$REPO/kotl/__init__.py")
say "installing Kotl $ver from $REPO (commit $rev)"
if [ -n "$(git -C "$REPO" status --porcelain -- kotl deploy plugin plugin-band vscode-kotl .claude-plugin 2>/dev/null)" ]; then
  say "note: the repo has uncommitted changes; they get installed too"
fi

say "1. the workstation"
run sudo bash "$DEPLOY/kotl/install.sh" || die "the workstation install failed: stopping"
if [ "$DO_PC" = 1 ]; then
  say "2. the board PCs"
  bash "$DEPLOY/kotl/pc.sh" update "${PCARGS[@]}" || { say "done, but a PC update failed (above)"; exit 1; }
fi
echo
say "done ($(cat "${KOTL_ROOT:-}/opt/kotl/BUILD" 2>/dev/null || echo "$ver"))"
say "users: new Claude sessions get the new plugins; VS Code asks them to run 'kotl setup'"
