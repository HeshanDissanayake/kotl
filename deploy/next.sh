#!/usr/bin/env bash
# The steps Claude needs from you right now. Run from anywhere:  bash ~/working_dir/kotl/deploy/next.sh
# It asks before each step; answer n to skip one. deploy/NEXT.md explains each step.
set -u
cd "$(dirname "$0")/.." || exit 1
PC=virtex-host@192.168.1.2

ask() { printf '\n== %s\n   run it? [y/N] ' "$1"; read -r a; [ "$a" = y ] || [ "$a" = Y ]; }

if ask "0. Show what runs as virtex-host on the PC (read-only)"; then
  ssh "$PC" 'ps -u virtex-host -o pid,etime,cmd --sort=start_time'
fi

if ask "0b. Update kotl-keys on the PC (sudo there), then Kotl on the workstation (sudo here)"; then
  scp deploy/pc/setup.sh deploy/pc/kotl-keys "$PC":/tmp/ &&
  ssh -t "$PC" "sudo bash /tmp/setup.sh --keys-helper /tmp/kotl-keys && rm /tmp/setup.sh /tmp/kotl-keys" &&
  sudo deploy/kotl/install.sh --board vcu118-pc1=vcu118@vcu118-pc1
fi

if ask "2. Driver-failure test: unload XDMA on the PC on purpose (only when nobody runs FireSim)"; then
  ssh -t "$PC" 'sudo modprobe -r xdma; echo "xdma modules loaded now: $(lsmod | grep -c "^xdma ")"'
  echo "Kotl's next health check (within 5 minutes) should reload it once. Tell Claude."
fi

echo
echo "Done. Tell Claude what you ran, and add \"ok PC\" if Claude may run its own two short tests"
echo "(the ETA notice and kotl attach; see deploy/NEXT.md step 1)."
