#!/usr/bin/env bash
# Read-only check that an FPGA PC is ready for users' own FireSim. Changes nothing.
# Run on the workstation as root (it logs in as kotl):
#
#   sudo deploy/adapters/firesim/check.sh [vcu118-pc1]
#
# Checks: kotl can log in; the Xilinx card shows on PCI; the XDMA driver is loaded;
# the PC's FireSim account (pc_account in /etc/kotl/kotl.conf) exists.
set -uo pipefail

PC=${1:-vcu118-pc1}
ACCOUNT=$(sed -n 's/^pc_account *= *//p' /etc/kotl/kotl.conf 2>/dev/null | head -n 1)
ACCOUNT=${ACCOUNT:-virtex-host}
fails=0

check() {  # check NAME COMMAND-ON-PC
  local out
  if out=$(runuser -u kotl -- ssh "$PC" "$2" 2>&1) && [ -n "$out" ]; then
    printf 'PASS  %-22s %s\n' "$1" "$(printf '%s' "$out" | head -n 1)"
  else
    printf 'FAIL  %-22s %s\n' "$1" "$(printf '%s' "$out" | head -n 1)"; fails=$((fails + 1))
  fi
}

[ "$(id -u)" = 0 ] || { echo "run as root: sudo $0 $PC" >&2; exit 2; }
check "kotl login"       "hostname"
check "Xilinx card (PCI)" "lspci -d 10ee: | head -n 1"
check "XDMA driver"      "lsmod | grep -w xdma | head -n 1"
check "account $ACCOUNT" "getent passwd $ACCOUNT | cut -d: -f1"
exit $((fails > 0))
