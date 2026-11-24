#!/usr/bin/env bash
# FireSim adapter, the PC part. Runs ON an FPGA PC, as root, with kotl-xdma-reload and
# kotl-firesim-stop copied next to it.
#
#   sudo bash pc-setup.sh            installs both in /usr/local/bin with one sudoers line each:
#                                    kotl may run only that script, as root, with no arguments
#                                    kotl-xdma-reload:  the health check's one XDMA reload (idle board)
#                                    kotl-firesim-stop: the end step stops FireSim's root driver
#                                    (it may also pass the job's age: a number, the script checks it)
#   sudo bash pc-setup.sh --undo     removes them
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
    -h|--help) sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) die "unknown option $1" ;;
  esac
  shift
done
[ "$DRY" = 1 ] || [ "$(id -u)" = 0 ] || die "run as root (sudo bash $0), or add --dry-run"

if [ "$ACTION" = undo ]; then
  run rm -f /usr/local/bin/kotl-xdma-reload /etc/sudoers.d/kotl-driver
  run rm -f /usr/local/bin/kotl-firesim-stop /etc/sudoers.d/kotl-firesim-stop
  say "removed kotl-xdma-reload, kotl-firesim-stop and their sudoers lines"
  exit 0
fi

# install_helper NAME SUDOERS-FILE [any]: /usr/local/bin/NAME, and "kotl may run it as root" with
# no arguments (or, with "any", also with arguments, which the script itself checks)
install_helper() {
  local src="$HERE/$1" rule
  [ -f "$src" ] || die "copy $1 next to this script"
  head -n 3 "$src" | grep -q 'managed by kotl' || die "$src is not Kotl's $1"
  run install -m 755 -o root -g root "$src" "/usr/local/bin/$1"
  rule="kotl ALL=(root) NOPASSWD: /usr/local/bin/$1 \"\""
  [ "${3:-}" = any ] && rule="kotl ALL=(root) NOPASSWD: /usr/local/bin/$1 \"\", /usr/local/bin/$1 [0-9]*"
  if [ "$DRY" = 1 ]; then
    say "would write /etc/sudoers.d/$2 (440): $rule"
  else
    tmp=$(mktemp)
    printf '# managed by kotl (deploy/adapters/firesim/pc-setup.sh)\n%s\n' "$rule" >"$tmp"
    visudo -cf "$tmp" >/dev/null || { rm -f "$tmp"; die "sudoers line failed visudo"; }
    install -m 440 -o root -g root "$tmp" "/etc/sudoers.d/$2"
    rm -f "$tmp"
  fi
  say "$1 installed; kotl may run it as root$([ "${3:-}" = any ] && echo ", with a number of seconds or nothing" || echo ", with no arguments")"
}

modinfo xdma >/dev/null 2>&1 || [ -f "/lib/modules/$(uname -r)/extra/xdma.ko" ] ||
  say "WARNING: no xdma module found here, so the reload can't work"
install_helper kotl-xdma-reload kotl-driver
install_helper kotl-firesim-stop kotl-firesim-stop any
