#!/usr/bin/env bash
# managed by kotl (deploy/kotl/update.sh)
# Update Kotl everywhere from this repo, in one go. Run as the admin (not with sudo: it asks for
# sudo itself, here and on each PC), from the repo you want to install:
#
#   bash deploy/kotl/update.sh            the workstation, then every board's PC
#   bash deploy/kotl/update.sh --no-pc    the workstation only
#   bash deploy/kotl/update.sh --pc virtex-host@192.168.1.2   only that PC (repeatable)
#
# The workstation: deploy/kotl/install.sh with no options, which rebuilds and reinstalls all of
# Kotl (code, kotl command, daemon, notifier, plugins, VS Code extension, Claude rules) and keeps
# the boards and adapters already set. Each PC: Kotl's PC helpers (pc/setup.sh --keys-helper) and
# the PC part of every enabled adapter (adapters/NAME/pc-setup.sh). The PCs come from
# /etc/ssh/ssh_config.d/kotl.conf, the account from /etc/kotl/kotl.conf (pc_account).
# Users then run `kotl setup` (and reload VS Code) for the new plugins and extension.
#
# Add --dry-run to print what it would run, changing nothing.
set -uo pipefail
DEPLOY=$(cd "$(dirname "$0")/.." && pwd)
REPO=$(cd "$DEPLOY/.." && pwd)
ROOT=${KOTL_ROOT:-}
DRY=0 DO_PC=1 PCS=()
say() { printf 'kotl-update: %s\n' "$*"; }
die() { printf 'kotl-update: error: %s\n' "$*" >&2; exit 1; }
run() { if [ "$DRY" = 1 ]; then printf 'would run: %s\n' "$*"; else "$@"; fi; }
conf() { sed -n "s/^[[:space:]]*$1[[:space:]]*=[[:space:]]*//p" "$ROOT/etc/kotl/kotl.conf" 2>/dev/null | tail -n 1; }

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --no-pc) DO_PC=0 ;;
    --pc) PCS+=("${2:-}"); shift ;;
    -h|--help) sed -n '3,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown option $1" ;;
  esac
  shift
done
[ "$(id -u)" != 0 ] || [ "$DRY" = 1 ] || die "run it as yourself, not as root: it uses sudo where it needs it"

rev=$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo "?")
say "installing Kotl from $REPO (commit $rev)"
if [ -n "$(git -C "$REPO" status --porcelain -- kotl deploy plugin plugin-band vscode-kotl .claude-plugin 2>/dev/null)" ]; then
  say "note: the repo has uncommitted changes; they get installed too"
fi

fails=0
say "1. the workstation"
run sudo bash "$DEPLOY/kotl/install.sh" || { say "the workstation install failed: stopping"; exit 1; }

if [ "$DO_PC" = 1 ]; then
  account=$(conf pc_account); account=${account:-virtex-host}
  if [ ${#PCS[@]} -eq 0 ]; then
    while read -r addr; do PCS+=("$account@$addr"); done < <(awk '$1 == "HostName" { print $2 }' "$ROOT/etc/ssh/ssh_config.d/kotl.conf" 2>/dev/null)
  fi
  adapters=$(conf adapters | tr ',' ' ')
  parts=(pc)
  for a in $adapters; do
    case "$a" in *[!a-z0-9]*|"") die "odd adapter name in kotl.conf: '$a'" ;; esac
    [ -f "$DEPLOY/adapters/$a/pc-setup.sh" ] && parts+=("adapters/$a")
  done
  [ ${#PCS[@]} -gt 0 ] || say "no board PCs found in /etc/ssh/ssh_config.d/kotl.conf; skipping the PCs"
  for pc in "${PCS[@]}"; do
    case "$pc" in *[!A-Za-z0-9@._-]*|"") die "--pc wants USER@ADDRESS, got '$pc'" ;; esac
    say "2. the PC $pc (helpers: ${parts[*]}); it may ask for the sudo password there"
    remote="sudo bash \$d/pc/setup.sh --account $account --keys-helper \$d/pc/kotl-keys"
    for part in "${parts[@]:1}"; do remote+=" && sudo bash \$d/$part/pc-setup.sh"; done
    if [ "$DRY" = 1 ]; then
      printf 'would run: tar -C %s -cf - %s | ssh %s (into a new temporary folder)\n' "$DEPLOY" "${parts[*]}" "$pc"
      printf 'would run: ssh -t %s "%s; rm -rf the folder"\n' "$pc" "$remote"
      continue
    fi
    d=$(tar -C "$DEPLOY" -cf - "${parts[@]}" | ssh "$pc" 'd=$(mktemp -d /tmp/kotl-update.XXXXXX) && tar -C "$d" -xf - && echo "$d"') ||
      { say "couldn't copy the helpers to $pc"; fails=$((fails + 1)); continue; }
    case "$d" in /tmp/kotl-update.*) ;; *) say "odd folder from $pc: '$d'"; fails=$((fails + 1)); continue ;; esac
    ssh -t "$pc" "d=$d; $remote; rc=\$?; rm -rf \"\$d\"; exit \$rc" ||
      { say "the update on $pc failed (see above)"; fails=$((fails + 1)); continue; }
  done
fi

echo
if [ "$fails" -gt 0 ]; then say "done, with $fails PC(s) failed"; else say "done"; fi
say "users: run 'kotl setup' and reload VS Code to get the new plugins and extension"
[ "$fails" -eq 0 ]
