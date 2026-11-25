#!/usr/bin/env bash
# Kotl FireSim test: boot Linux on the FPGA and power it off. Needs nothing but this folder:
# no Chipyard, no FireSim install, no conda. Run it through Kotl, from any folder you can write to:
#
#   kotl run --eta 15m -- /path/to/kotl-firesim-test/run.sh
#
# What it does, as you, with only your job's key (KOTL_PC, set by Kotl inside the job):
#   1. checks the board's PC: Xilinx card, XDMA loaded with poll_mode=1, xvsec, xvsecctl, sudo
#   2. copies payload/ to the PC (~/kotl-firesim-test-JOB)
#   3. flashes the FPGA with the bitstream (sudo xvsecctl), the way FireSim's infrasetup does
#   4. runs the FireSim driver in screen session fsim0 (kotl attach shows the console),
#      the way FireSim's runworkload does, using the PC's own glibc
#   5. waits for the simulated Linux to power off (or the time limit), copies the uartlog back
#   6. removes its folder on the PC, and prints KOTL RESULT: PASS only on "reboot: Power down"
#
# It prints 'KOTL FACT: key=value' lines (from MANIFEST: what the package was built from), so its
# line in the lab notes (kotl notes firesim) says which bitstream and driver ran.
# Results: ./firesim-test-results/JOB/ (uartlog, and the driver's other logs).
# Settings (environment): KOTL_TEST_TIMEOUT (seconds, default 900), KOTL_TEST_KEEP=1 keeps the
# folder on the PC, KOTL_TEST_OUT (results folder).
set -uo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
JOB=${KOTL_JOB:-manual-$$}
OUT=${KOTL_TEST_OUT:-$PWD/firesim-test-results/$JOB}
TIMEOUT=${KOTL_TEST_TIMEOUT:-900}
DIR="kotl-firesim-test-$JOB"             # on the PC, in the board account's home
step() { echo; echo "== $(date +%H:%M:%S) $*"; }
fail() { echo "KOTL RESULT: FAIL ($*)"; exit 1; }
pc() { ssh -o BatchMode=yes -o ConnectTimeout=15 "$KOTL_PC" "$@"; }
who_connected() {   # workstation accounts with an SSH connection to the PC now (the kernel's table)
  local ip=${KOTL_PC#*@} hex
  hex=$(echo "$ip" | awk -F. 'NF == 4 { printf "%02X%02X%02X%02X:0016", $4, $3, $2, $1 }')
  [ -n "$hex" ] || return 0
  awk -v h="$hex" 'NR > 1 && $3 == h && $4 == "01" { print $8 }' /proc/net/tcp 2>/dev/null | sort | uniq -c |
    while read -r n uid; do u=$(getent passwd "$uid" | cut -d: -f1); [ "$u" = kotl ] || printf '%s%s ' "${u:-uid $uid}" "$([ "$n" -gt 1 ] && echo " ($n)")"; done
}

[ -n "${KOTL_PC:-}" ] || fail "run me inside a Kotl job: kotl run --eta 15m -- $0"
[ -d "$HERE/payload/sim" ] && [ -f "$HERE/payload/bitstream/firesim.bit" ] || fail "payload/ is incomplete; rebuild the package"
mkdir -p "$OUT" || fail "can't write results to $OUT (run from a folder you can write to, or set KOTL_TEST_OUT)"
. "$HERE/payload/sim/args.sh"            # SIM_ARGS: the driver's arguments (from the FireSim run it came from)

# what this package is, for the lab notes (kotl notes firesim: runs.md)
facts() {
  local m="$HERE/MANIFEST"
  echo "KOTL FACT: tool=firesim"
  echo "KOTL FACT: package=$HERE"
  [ -f "$m" ] || return 0
  sed -n '1s/.*built \([0-9-]*\).*/KOTL FACT: package_built=\1/p' "$m"
  sed -n 's#^chipyard: *\([^ ]*\)$#KOTL FACT: chipyard=\1#p; s#^firesim: *\([^ ]*\)$#KOTL FACT: firesim=\1#p' "$m"
  sed -n 's#^bitstream: .*/\([^/]*\)/[^/]*$#KOTL FACT: bitstream=\1#p' "$m"
  sed -n 's#^driver: .*/\([^/]*\)/[^/]*$#KOTL FACT: driver=\1#p' "$m"
  sed -n 's#^workload: *[^ ]*/\([^/ ]*\) .*#KOTL FACT: workload=\1#p' "$m"
  awk '$2 == "payload/bitstream/firesim.bit" { print "KOTL FACT: bit_sha256=" substr($1, 1, 12) }' "$m"
}
facts

step "1/6 checking the board's PC ($KOTL_PC)"
PC_CHECK=$(cat <<'EOF'
set -e
card=$(lspci -nd 10ee: | head -n 1)
[ -n "$card" ] || { echo "no Xilinx card on PCI"; exit 1; }
echo "card: $card"
if screen -ls 2>/dev/null | grep -q '\.fsim0'; then
  echo "OUTSIDE KOTL: FireSim is already running on the PC, and it isn't a Kotl job:"
  screen -ls 2>/dev/null | grep '\.fsim' | awk '{print "  screen " $1}'
  ps -eo user,etime,comm 2>/dev/null | awk '$3 ~ /^FireSim-/ { print "  driver running for " $2 " (as " $1 ")" }'
  echo "BUSY-OUTSIDE"
  exit 1
fi
lsmod | grep -q '^xdma ' || { echo "the XDMA driver isn't loaded (Kotl's health check reloads it on an idle board)"; exit 1; }
pm=$(cat /sys/module/xdma/parameters/poll_mode 2>/dev/null || echo unknown)
[ "$pm" = 1 ] || { echo "XDMA is loaded with poll_mode=$pm; FireSim needs 1 (admin: sudo /usr/local/bin/kotl-xdma-reload on an idle board)"; exit 1; }
lsmod | grep -q '^xvsec ' || { echo "the xvsec driver isn't loaded (needed to flash the FPGA)"; exit 1; }
command -v xvsecctl >/dev/null || { echo "xvsecctl isn't installed on the PC"; exit 1; }
sudo -n true 2>/dev/null || { echo "the board account can't use sudo without a password (FireSim needs it)"; exit 1; }
echo "ok: XDMA poll_mode=1, xvsec, xvsecctl, sudo"
EOF
)
check=$(pc bash -s <<<"$PC_CHECK" 2>&1); ok=$?
echo "$check" | grep -v '^BUSY-OUTSIDE$'
if [ $ok -ne 0 ]; then
  if echo "$check" | grep -q '^BUSY-OUTSIDE$'; then
    who=$(who_connected)
    echo "  connected to the PC from the workstation now: ${who:-nobody (a leftover, or started and left running)}"
    echo "  Kotl leaves it running. Ask them to use kotl run / kotl lease, then run this test again."
    fail "FireSim is running on the board outside Kotl"
  fi
  fail "the board's PC isn't ready (see above)"
fi

step "2/6 copying the package to the PC (~/$DIR)"
tar -C "$HERE/payload" -cf - . | pc "rm -rf '$DIR' && mkdir -p '$DIR' && tar -C '$DIR' -xf -" || fail "copying to the PC"

cleanup() {
  [ "${KOTL_TEST_KEEP:-0}" = 1 ] && { echo "keeping ~/$DIR on the PC (KOTL_TEST_KEEP=1)"; return; }
  pc "rm -rf '$DIR'" && echo "removed ~/$DIR on the PC"
}

step "3/6 flashing the FPGA"
pc "cd '$DIR' && set -- \$(lspci -nd 10ee: | head -n 1) && bdf=\$1 && bus=\${bdf%%:*} && dev=\${bdf#*:} && dev=\${dev%%.*} &&
    sudo xvsecctl -b 0x\$bus -F 0x\$dev -c 0x1 -p bitstream/firesim.bit" || { cleanup; fail "flashing the FPGA"; }

step "4/6 starting the simulation (screen fsim0; watch it with: kotl attach)"
pc "cd '$DIR/sim' && set -- \$(lspci -nd 10ee: | head -n 1) && bdf=\$1 && id=\$3 && bus=\${bdf%%:*} && rest=\${bdf#*:} && dev=\${rest%%.*} && fn=\${bdf##*.} &&
    screen -S fsim0 -d -m bash -c \"script -f -c 'stty intr ^] && sudo ./FireSim-xilinx_vcu118 $SIM_ARGS +domain=0x0000 +bus=0x\$bus +device=0x\$dev +function=0x\$fn +bar=0x0 +pci-vendor=0x10ee +pci-device=0x\${id#*:} +permissive-off +prog0=poweroffnode-br-base-bin && stty intr ^c' uartlog\" && sleep 2 &&
    screen -ls | grep -q '\.fsim0'" || { cleanup; fail "starting the FireSim driver"; }

step "5/6 waiting for Linux to boot and power off (up to $((TIMEOUT / 60)) min)"
start=$(date +%s); last=""
while pc "screen -ls 2>/dev/null | grep -q '\.fsim0'"; do
  now=$(date +%s)
  line=$(pc "tail -n 1 '$DIR/sim/uartlog' 2>/dev/null" | tr -d '\r' | cut -c1-120)
  [ -n "$line" ] && [ "$line" != "$last" ] && { echo "  [$((now - start))s] $line"; last=$line; }
  if [ $((now - start)) -ge "$TIMEOUT" ]; then
    echo "  time limit reached: stopping the simulation"
    pc "screen -S fsim0 -X quit; sudo pkill -f 'FireSim-xilinx' || true"
    break
  fi
  sleep 10
done
pc "cat '$DIR/sim/uartlog'" > "$OUT/uartlog" 2>/dev/null
for f in blkdev-log0 niclog0; do pc "cat '$DIR/sim/$f' 2>/dev/null" > "$OUT/$f" || rm -f "$OUT/$f"; done
cleanup

step "6/6 result"
echo "--- uartlog (last lines): $OUT/uartlog"
tail -n 8 "$OUT/uartlog" 2>/dev/null | tr -d '\r'
if grep -aqs "reboot: Power down" "$OUT/uartlog"; then
  echo "KOTL RESULT: PASS"
else
  fail "the simulated Linux did not power off; see $OUT/uartlog"
fi
