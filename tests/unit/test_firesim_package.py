"""The FireSim test package: built from a (fake) Chipyard without touching it, self-contained,
no workstation glibc, and run.sh refuses to run outside a Kotl job. No board involved."""
import io
import os
import subprocess
import tarfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.feature("fsmod")
ROOT = Path(__file__).resolve().parents[2]
MAKE = ROOT / "deploy/adapters/firesim/make-test-package.sh"


def tar_with(path, files, gz=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(path, "w:gz" if gz else "w") as t:
        for name, data in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))


@pytest.fixture
def chipyard(tmp_path):
    cy = tmp_path / "chipyard"
    fs = cy / "sims/firesim"
    tar_with(fs / "deploy/results-build/ref-2026-06-03-xilinx_vcu118_firesim_rocket_singlecore_4GB_no_nic/firesim.tar.gz",
             {"xilinx_vcu118/firesim.bit": b"BIT", "xilinx_vcu118/metadata": b"meta", "xilinx_vcu118/firesim.mcs": b"MCS"})
    drv = fs / "sim/output/xilinx_vcu118/xilinx_vcu118-firesim-FireSim-FireSimRocket32KBL1NoL2Config-BaseXilinxVCU118Config"
    tar_with(drv / "driver-bundle.tar.gz", {n: b"x" for n in (
        "FireSim-xilinx_vcu118", "libriscv.so", "libdwarf.so.1", "libc.so.6", "libm.so.6", "libpthread.so.0", "libdl.so.2", "librt.so.1")})
    wl = fs / "deploy/workloads/linux-poweroff"
    wl.mkdir(parents=True)
    (wl / "poweroffnode.ext2").write_bytes(b"EXT2")
    (wl / "br-base-bin").write_bytes(b"KERNEL")
    img = fs / "sw/firesim-software/images/firechip/br-base"
    img.mkdir(parents=True)
    (img / "br-base-bin-dwarf").write_bytes(b"DWARF")
    sr = fs / "deploy/results-workload/2026-11-23--11-02-47-linux-poweroff/poweroffnode/sim-run.sh"
    sr.parent.mkdir(parents=True)
    sr.write_text("#!/usr/bin/env bash\nscreen -S fsim0 -d -m bash -c \"script -f -c 'stty intr ^] && sudo ./FireSim-xilinx_vcu118 "
                  "+permissive   +macaddr0=00:12:6D:00:00:02 +blkdev0=poweroffnode-poweroffnode.ext2 +domain=0x0000 +bus=0x01 "
                  "+prog0=poweroffnode-br-base-bin   && stty intr ^c' uartlog\"; sleep 1\n")
    before = sorted((p.relative_to(cy), p.stat().st_mtime) for p in cy.rglob("*"))
    yield cy
    assert sorted((p.relative_to(cy), p.stat().st_mtime) for p in cy.rglob("*")) == before   # never changed


def test_builds_a_self_contained_folder(chipyard, tmp_path):
    out = tmp_path / "pkg"
    r = subprocess.run(["bash", str(MAKE), "--chipyard", str(chipyard), "--out", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    sim = out / "payload/sim"
    assert (out / "payload/bitstream/firesim.bit").read_bytes() == b"BIT"
    assert not (out / "payload/bitstream/firesim.mcs").exists()
    for lib in ("libc.so.6", "libm.so.6", "libpthread.so.0", "libdl.so.2", "librt.so.1"):
        assert not (sim / lib).exists(), lib                                    # the PC's own glibc is used
    assert (sim / "libriscv.so").exists() and os.access(sim / "FireSim-xilinx_vcu118", os.X_OK)
    assert (sim / "poweroffnode-poweroffnode.ext2").read_bytes() == b"EXT2"
    assert (sim / "poweroffnode-br-base-bin-dwarf").read_bytes() == b"DWARF"
    args = (sim / "args.sh").read_text()
    assert 'SIM_ARGS="+permissive +macaddr0=00:12:6D:00:00:02 +blkdev0=poweroffnode-poweroffnode.ext2"' in args
    assert os.access(out / "run.sh", os.X_OK) and "For Claude" in (out / "README.md").read_text()
    assert "payload/sim/args.sh" in (out / "MANIFEST").read_text()


def test_refuses_to_write_inside_the_chipyard(chipyard):
    r = subprocess.run(["bash", str(MAKE), "--chipyard", str(chipyard), "--out", str(chipyard / "pkg")], capture_output=True, text=True)
    assert r.returncode == 2 and "outside the Chipyard" in r.stderr


def test_run_sh_only_runs_inside_a_kotl_job(chipyard, tmp_path):
    out = tmp_path / "pkg"
    subprocess.run(["bash", str(MAKE), "--chipyard", str(chipyard), "--out", str(out)], check=True, capture_output=True)
    env = {k: v for k, v in os.environ.items() if not k.startswith("KOTL_")}
    r = subprocess.run(["bash", str(out / "run.sh")], capture_output=True, text=True, env=env, cwd=tmp_path)
    assert r.returncode == 1 and "KOTL RESULT: FAIL (run me inside a Kotl job" in r.stdout
