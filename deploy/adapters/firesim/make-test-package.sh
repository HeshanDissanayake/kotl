#!/usr/bin/env bash
# Build the Kotl FireSim test package: one self-contained folder that boots Linux on a VCU118
# through Kotl, for users with no Chipyard. Reads a Chipyard (never changes it), writes OUT.
#
#   make-test-package.sh --chipyard ~/chipyard --out /shared/kotl-firesim-test
#
# Defaults are the combination that booted Linux on vcu118-pc1 (Kotl job 49): the
# xilinx_vcu118_firesim_rocket_singlecore_4GB_no_nic bitstream, its FireSimRocket32KBL1NoL2Config
# driver, and the linux-poweroff workload. Override with --bitstream-tar, --driver-dir,
# --workload-dir, --sim-run (a sim-run.sh FireSim generated, for the driver's arguments).
#
# The folder: run.sh, README.md, MANIFEST (sources and sha256), payload/{bitstream,sim}.
# The driver bundle ships WITHOUT the workstation's glibc, so the PC's own glibc is used.
set -euo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
CY="" OUT=""
BIT="" DRV="" WL="" SIMRUN="" IMG=""
while [ $# -gt 0 ]; do
  case "$1" in
    --chipyard) CY=$2; shift ;;
    --out) OUT=$2; shift ;;
    --bitstream-tar) BIT=$2; shift ;;
    --driver-dir) DRV=$2; shift ;;
    --workload-dir) WL=$2; shift ;;
    --sim-run) SIMRUN=$2; shift ;;
    -h|--help) sed -n '2,14p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
  shift
done
[ -n "$CY" ] && [ -n "$OUT" ] || { echo "usage: $0 --chipyard PATH --out DIR" >&2; exit 2; }
FS="$CY/sims/firesim"
BIT=${BIT:-$FS/deploy/results-build/ref-2026-06-03-xilinx_vcu118_firesim_rocket_singlecore_4GB_no_nic/firesim.tar.gz}
DRV=${DRV:-$FS/sim/output/xilinx_vcu118/xilinx_vcu118-firesim-FireSim-FireSimRocket32KBL1NoL2Config-BaseXilinxVCU118Config}
WL=${WL:-$FS/deploy/workloads/linux-poweroff}
IMG="$FS/sw/firesim-software/images/firechip/br-base"
SIMRUN=${SIMRUN:-$(ls -t "$FS"/deploy/results-workload/*linux-poweroff/poweroffnode/sim-run.sh 2>/dev/null | head -n 1)}
for f in "$BIT" "$DRV/driver-bundle.tar.gz" "$WL/poweroffnode.ext2" "$WL/br-base-bin" "$IMG/br-base-bin-dwarf" "$SIMRUN"; do
  [ -e "$f" ] || { echo "missing: $f" >&2; exit 1; }
done
case "$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")/" in "$(cd "$CY" && pwd)/"*) echo "--out must be outside the Chipyard" >&2; exit 2 ;; esac

tmp="$OUT.partial"
rm -rf "$tmp"
mkdir -p "$tmp/payload/bitstream" "$tmp/payload/sim"
echo "bitstream: $BIT"
tar -xzf "$BIT" -C "$tmp/payload/bitstream" --strip-components=1 xilinx_vcu118/firesim.bit xilinx_vcu118/metadata
echo "driver:    $DRV/driver-bundle.tar.gz (without the workstation's glibc)"
tar -xzf "$DRV/driver-bundle.tar.gz" -C "$tmp/payload/sim" --exclude=libc.so.6 --exclude=libm.so.6 \
  --exclude=libpthread.so.0 --exclude=libdl.so.2 --exclude=librt.so.1
echo "workload:  $WL (linux-poweroff)"
cp -L "$WL/poweroffnode.ext2" "$tmp/payload/sim/poweroffnode-poweroffnode.ext2"
cp -L "$WL/br-base-bin" "$tmp/payload/sim/poweroffnode-br-base-bin"
cp -L "$IMG/br-base-bin-dwarf" "$tmp/payload/sim/poweroffnode-br-base-bin-dwarf"
# the driver's own arguments, as FireSim generated them; the PCI address is found on the PC
args=$(grep -o "sudo ./FireSim-xilinx_vcu118 [^&']*" "$SIMRUN" | sed 's#^sudo ./FireSim-xilinx_vcu118 ##; s# +domain=.*##; s#  *# #g; s# *$##')
[ -n "$args" ] || { echo "no driver arguments found in $SIMRUN" >&2; exit 1; }
printf '# the FireSim driver arguments (from %s)\nSIM_ARGS="%s"\n' "$SIMRUN" "$args" >"$tmp/payload/sim/args.sh"
cp "$HERE/test-package/run.sh" "$tmp/run.sh"
abs_out="$(cd "$(dirname "$OUT")" && pwd)/$(basename "$OUT")"
sed "s#@PACKAGE@#$abs_out#g" "$HERE/test-package/README.md" >"$tmp/README.md"
chmod 755 "$tmp/run.sh" "$tmp/payload/sim/FireSim-xilinx_vcu118"
{
  echo "Kotl FireSim test package, built $(date -Is) by $(id -un) on $(hostname -s)"
  echo "bitstream: $BIT"
  echo "driver:    $DRV/driver-bundle.tar.gz"
  echo "workload:  $WL + $IMG/br-base-bin-dwarf"
  echo "args from: $SIMRUN"
  echo "chipyard:  $(git -C "$CY" rev-parse --short=10 HEAD 2>/dev/null || echo '?')"
  echo "firesim:   $(git -C "$FS" rev-parse --short=10 HEAD 2>/dev/null || echo '?')"
  echo
  (cd "$tmp" && find payload run.sh README.md -type f -print0 | sort -z | xargs -0 sha256sum)
} >"$tmp/MANIFEST"
chmod -R a+rX "$tmp"
rm -rf "$OUT"
mv "$tmp" "$OUT"
echo "built $OUT ($(du -sh "$OUT" | cut -f1)); anyone can read it. Try: kotl run --eta 15m -- $OUT/run.sh"
