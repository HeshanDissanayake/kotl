#!/usr/bin/env bash
# FireSim adapter, the PC part. Runs ON an FPGA PC, as root, with kotl-xdma-reload copied next to it.
#
#   sudo bash pc-setup.sh            installs /usr/local/bin/kotl-xdma-reload and one sudoers line:
#                                    kotl may run only that script, as root, with no arguments
#                                    (the health check's one XDMA reload on an idle board)
#   sudo bash pc-setup.sh --undo     removes both
#
# Needs Kotl's own PC setup first (deploy/pc/setup.sh: the kotl account). Add --dry-run to preview.
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
DRY=0 ACTION=install
say() { printf 'kotl-pc (firesim): %s\n' "$*"; }
die() { printf 'kotl-pc (firesim): error: %s\n' "$*" >&2; exit 1; }
run() { if [ "$DRY" = 1 ]; then printf 'would run: %s\n' "$*"; else "$@"; fi; }

while [ $# -gt 0 ]; do
  case "$1" in
    --dry-run) DRY=1 ;;
    --undo) ACTION=undo ;;
    -h|--help) sed -n '2,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown option $1" ;;
  esac
  shift
done
[ "$DRY" = 1 ] || [ "$(id -u)" = 0 ] || die "run as root (sudo bash $0), or add --dry-run"

if [ "$ACTION" = undo ]; then
  run rm -f /usr/local/bin/kotl-xdma-reload /etc/sudoers.d/kotl-driver
  say "removed kotl-xdma-reload and its sudoers line"
  exit 0
fi

DRIVER="$HERE/kotl-xdma-reload"
[ -f "$DRIVER" ] || die "copy kotl-xdma-reload next to this script"
head -n 3 "$DRIVER" | grep -q 'managed by kotl' || die "$DRIVER is not Kotl's kotl-xdma-reload"
modinfo xdma >/dev/null 2>&1 || [ -f "/lib/modules/$(uname -r)/extra/xdma.ko" ] ||
  say "WARNING: no xdma module found here, so the reload can't work"
run install -m 755 -o root -g root "$DRIVER" /usr/local/bin/kotl-xdma-reload
rule='kotl ALL=(root) NOPASSWD: /usr/local/bin/kotl-xdma-reload ""'
if [ "$DRY" = 1 ]; then
  say "would write /etc/sudoers.d/kotl-driver (440): $rule"
else
  tmp=$(mktemp)
  printf '# managed by kotl (deploy/adapters/firesim/pc-setup.sh)\n%s\n' "$rule" >"$tmp"
  visudo -cf "$tmp" >/dev/null || { rm -f "$tmp"; die "sudoers line failed visudo"; }
  install -m 440 -o root -g root "$tmp" /etc/sudoers.d/kotl-driver
  rm -f "$tmp"
fi
say "kotl-xdma-reload installed; kotl may run it as root, with no arguments"
