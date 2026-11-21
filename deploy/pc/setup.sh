#!/usr/bin/env bash
# Kotl on an FPGA PC (soft lockdown). Runs ON the PC, as root. Self-contained: copy just this file.
#
#   sudo bash setup.sh --key 'ssh-ed25519 AAAA... kotl@comparch'
#       adds a 'kotl' account (key login only, no password) with that public key.
#       Nothing else changes: sshd, passwords, virtex-host and its keys stay as they are.
#   sudo bash setup.sh --keys-helper /tmp/kotl-keys      (M3, with kotl-keys copied next to it)
#       installs /usr/local/bin/kotl-keys and one sudoers line: kotl may run only kotl-keys,
#       as the FireSim account (virtex-host). Can be combined with --key.
#   sudo bash setup.sh --undo
#       deletes the kotl account, kotl-keys and the sudoers line
#
# Add --dry-run to preview without changing anything.
set -euo pipefail

DRY=0 ACTION=install KEY="" HELPER="" ACCOUNT=virtex-host
say() { printf 'kotl-pc: %s\n' "$*"; }
die() { printf 'kotl-pc: error: %s\n' "$*" >&2; exit 1; }
run() { if [ "$DRY" = 1 ]; then printf 'would run: %s\n' "$*"; else "$@"; fi; }

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --undo) ACTION=undo ;;
    --key) KEY=${2:-}; shift ;;
    --keys-helper) HELPER=${2:-}; shift ;;
    --account) ACCOUNT=${2:-}; shift ;;
    -h|--help) sed -n '2,11p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown option $1" ;;
  esac
  shift
done
[ "$DRY" = 1 ] || [ "$(id -u)" = 0 ] || die "run as root (sudo bash $0 ...), or add --dry-run"

if [ "$ACTION" = undo ]; then
  run rm -f /usr/local/bin/kotl-keys /etc/sudoers.d/kotl
  if getent passwd kotl >/dev/null; then run userdel --remove kotl; else say "no kotl account here"; fi
  exit 0
fi

if [ -n "$HELPER" ]; then
  [ -f "$HELPER" ] || die "--keys-helper: no file $HELPER"
  head -n 3 "$HELPER" | grep -q 'managed by kotl' || die "--keys-helper: $HELPER is not Kotl's kotl-keys"
  getent passwd "$ACCOUNT" >/dev/null || die "no account $ACCOUNT on this PC"
  command -v flock >/dev/null || die "kotl-keys needs flock (util-linux)"
  run install -m 755 -o root -g root "$HELPER" /usr/local/bin/kotl-keys
  rule="kotl ALL=($ACCOUNT) NOPASSWD: /usr/local/bin/kotl-keys"
  if [ "$DRY" = 1 ]; then
    say "would write /etc/sudoers.d/kotl (440): $rule"
  else
    tmp=$(mktemp)
    printf '# managed by kotl (deploy/pc/setup.sh)\n%s\n' "$rule" >"$tmp"
    visudo -cf "$tmp" >/dev/null || { rm -f "$tmp"; die "sudoers line failed visudo"; }
    install -m 440 -o root -g root "$tmp" /etc/sudoers.d/kotl
    rm -f "$tmp"
  fi
  say "kotl-keys installed; kotl may run it as $ACCOUNT"
  [ -n "$KEY" ] || exit 0
fi

case "$KEY" in
  ssh-ed25519\ *|ssh-rsa\ *|ecdsa-sha2-*) ;;
  *) die "--key must be kotl's public key line (from ssh/setup-kotl-key.sh on the workstation)" ;;
esac

if ! getent passwd kotl >/dev/null; then
  run useradd --create-home --shell /bin/bash --comment "Kotl FPGA job manager" kotl
fi
run passwd -l kotl
run install -d -m 700 -o kotl -g kotl /home/kotl/.ssh
AK=/home/kotl/.ssh/authorized_keys
if [ "$DRY" = 1 ]; then
  say "would write $AK (600 kotl:kotl):"
  printf '  # managed by kotl (deploy/pc/setup.sh)\n  %s\n' "$KEY"
else
  printf '# managed by kotl (deploy/pc/setup.sh)\n%s\n' "$KEY" >"$AK"
  chown kotl:kotl "$AK"; chmod 600 "$AK"
fi

# warn if sshd only lets in a fixed list of users
if command -v sshd >/dev/null 2>&1; then
  allow=$(sshd -T 2>/dev/null | sed -n 's/^allowusers //p' | tr '\n' ' ' || true)
  if [ -n "$allow" ] && ! printf '%s' "$allow" | grep -qw kotl; then
    say "WARNING: sshd has AllowUsers ($allow) without kotl. Add kotl there, or Kotl can't log in."
  fi
fi
say "done: kotl can log in here with its key. Test from the workstation: sudo -u kotl ssh vcu118-pc1 hostname"
