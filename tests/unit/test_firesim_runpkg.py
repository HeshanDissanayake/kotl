"""FireSim run packages: kotl-firesim-pack on a (fake) Chipyard, read-only, and run-package.sh
end to end against a fake board PC (ssh, screen, the flasher and the driver are stand-ins).
No board involved."""
import importlib.machinery
import importlib.util
import io
import os
import subprocess
import tarfile
from pathlib import Path

import pytest

pytestmark = pytest.mark.feature("fsmod")
ROOT = Path(__file__).resolve().parents[2]
FS = ROOT / "deploy/adapters/firesim"
QUINT = "xilinx_vcu118-firesim-FireSim-FireSimRocket32KBL1NoL2Config-BaseXilinxVCU118Config"
# what FireSim generated for the run that passed on the board (job 49 / the test package)
GOOD = ("+macaddr0=00:12:6D:00:00:02 +blkdev0=poweroffnode-poweroffnode.ext2 +niclog0=niclog0 "
        "+blkdev-log0=blkdev-log0 +trace-select=1 +trace-start=0 +trace-end=-1 +trace-output-format=0 "
        "+dwarf-file-name=poweroffnode-br-base-bin-dwarf +autocounter-readrate=0 "
        "+autocounter-filename-base=AUTOCOUNTERFILE +print-start=0 +print-end=100000000 +linklatency0=6405 "
        "+netbw0=200 +shmemportname0=default")

RUNTIME = """run_farm:
  base_recipe: run-farm-recipes/externally_provisioned.yaml
  recipe_arg_overrides:
    run_farm_hosts_to_use:
        - someone@10.0.0.2: one_fpgas_spec
target_config:
    topology: no_net_config
    no_net_num_nodes: 1
    link_latency: 6405
    switching_latency: 10
    net_bandwidth: 200
    profile_interval: -1
    default_hw_config: vcu118_rocket   # the bitstream
    plusarg_passthrough: ""
tracing:
    enable: no
    output_format: 0
    selector: 1
    start: 0
    end: -1
autocounter:
    read_rate: 0
workload:
    workload_name: linux-poweroff.json
    terminate_on_completion: no
    suffix_tag: null
host_debug:
    zero_out_dram: no
    disable_synth_asserts: no
synth_print:
    start: 0
    end: 100000000
    cycle_prefix: yes
"""

DRIVER = """#!/bin/sh
echo "driver args: $*"
echo "out" > AUTOCOUNTERFILE0.csv
sleep 3
echo "${FAKE_LAST_LINE:-reboot: Power down}"
"""


def load_pack():
    import sys
    was, sys.dont_write_bytecode = sys.dont_write_bytecode, True     # no __pycache__ in deploy/
    try:
        loader = importlib.machinery.SourceFileLoader("kotl_firesim_pack", str(FS / "kotl-firesim-pack"))
        spec = importlib.util.spec_from_loader("kotl_firesim_pack", loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)
        return mod
    finally:
        sys.dont_write_bytecode = was


def make_chipyard(tmp_path):
    fs = tmp_path / "chipyard/sims/firesim"
    dep = fs / "deploy"
    (dep / "workloads/linux-poweroff").mkdir(parents=True)
    bit = dep / "results-build/ref-rocket/firesim.tar.gz"
    bit.parent.mkdir(parents=True)
    meta = f"firesim-deployquintuplet:{QUINT},firesim-commit:535dcdc29a930525".encode()
    with tarfile.open(bit, "w:gz") as t:
        for name, data in (("xilinx_vcu118/firesim.bit", b"BIT"), ("xilinx_vcu118/metadata", meta)):
            info = tarfile.TarInfo(name); info.size = len(data); t.addfile(info, io.BytesIO(data))
    (dep / "config_runtime.yaml").write_text(RUNTIME)
    (dep / "config_hwdb.yaml").write_text(f"vcu118_rocket:\n    bitstream_tar: file://{bit}\n"
                                          "    deploy_quintuplet_override: null\n    custom_runtime_config: null\n")
    out = fs / "sim/output/xilinx_vcu118" / QUINT
    out.mkdir(parents=True)
    (out / "FireSim-xilinx_vcu118").write_text(DRIVER)
    (out / "FireSim-xilinx_vcu118").chmod(0o755)
    img = tmp_path / "chipyard/software/firemarshal/images/br-base"
    img.mkdir(parents=True)
    (img / "br-base-bin").write_bytes(b"KERNEL")
    (img / "br-base-bin-dwarf").write_bytes(b"DWARF")
    (dep / "workloads/linux-poweroff/br-base-bin").symlink_to(img / "br-base-bin")
    (dep / "workloads/linux-poweroff/poweroffnode.ext2").write_bytes(b"EXT2")
    (dep / "workloads/linux-poweroff.json").write_text(
        '{"common_bootbinary": "br-base-bin", "benchmark_name": "linux-poweroff", "common_simulation_outputs": ["uartlog"],'
        ' "workloads": [{"name": "poweroffnode", "outputs": []}]}')
    return dep


@pytest.fixture
def chipyard(tmp_path):
    dep = make_chipyard(tmp_path)
    cy = tmp_path / "chipyard"
    before = sorted((p.relative_to(cy), p.stat().st_mtime) for p in cy.rglob("*"))
    yield dep
    assert sorted((p.relative_to(cy), p.stat().st_mtime) for p in cy.rglob("*")) == before   # never changed


@pytest.fixture
def chipyard_to_change(tmp_path):
    return make_chipyard(tmp_path)


def pack(dep, out, *args):
    return subprocess.run(["python3", str(FS / "kotl-firesim-pack"), "--deploy", str(dep), "--out", str(out), *args],
                          capture_output=True, text=True, env={k: v for k, v in os.environ.items() if k != "KOTL_SSH"})


def conf(pkg):
    out = subprocess.run(["bash", "-c", f". {pkg}/run.conf; printf '%s\\n' \"$DRIVER\" \"$SIM_ARGS\" \"$PROGS\" \"$TIMEOUT\""],
                         capture_output=True, text=True).stdout.splitlines()
    return dict(zip(("DRIVER", "SIM_ARGS", "PROGS", "TIMEOUT"), out))


def test_pack_makes_what_firesim_would_copy(chipyard, tmp_path):
    r = pack(chipyard, tmp_path / "pkg", "--timeout", "20m")
    assert r.returncode == 0, r.stderr
    pkg = tmp_path / "pkg"
    sim = pkg / "payload/sim"
    assert (pkg / "payload/bitstream/firesim.bit").read_bytes() == b"BIT"
    assert sorted(p.name for p in sim.iterdir()) == ["FireSim-xilinx_vcu118", "poweroffnode-br-base-bin",
                                                     "poweroffnode-br-base-bin-dwarf", "poweroffnode-poweroffnode.ext2"]
    c = conf(pkg)
    assert c == {"DRIVER": "FireSim-xilinx_vcu118", "SIM_ARGS": GOOD, "PROGS": "+prog0=poweroffnode-br-base-bin",
                 "TIMEOUT": "1200"}
    manifest = (pkg / "MANIFEST").read_text()
    for fact in ("fact: tool=firesim", "fact: hw_config=vcu118_rocket", "fact: bitstream=ref-rocket",
                 f"fact: driver={QUINT}", "fact: workload=linux-poweroff/poweroffnode", "fact: firesim=535dcdc29a"):
        assert fact in manifest
    assert "payload/sim/FireSim-xilinx_vcu118" in manifest            # with its sha256
    assert "rsync -a --partial" in r.stdout and "run-package.sh kotl-runs/pkg" in r.stdout
    assert pack(chipyard, tmp_path / "pkg").returncode == 1            # exists: needs --force
    assert pack(chipyard, tmp_path / "pkg", "--force").returncode == 0


def test_pack_follows_the_runtime_config(chipyard_to_change, tmp_path):
    chipyard = chipyard_to_change
    rt = chipyard / "mine.yaml"
    rt.write_text(RUNTIME.replace("enable: no", "enable: yes").replace("cycle_prefix: yes", "cycle_prefix: no")
                  .replace('plusarg_passthrough: ""', 'plusarg_passthrough: "+max-cycles=1000"')
                  .replace("profile_interval: -1", "profile_interval: 100"))
    assert pack(chipyard, tmp_path / "p2", "-c", str(rt)).returncode == 0
    args = conf(tmp_path / "p2")["SIM_ARGS"].split()
    assert "+tracefile=TRACEFILE" in args and "+print-no-cycle-prefix" in args
    assert args[0] == "+profile-interval=100" and args[-1] == "+max-cycles=1000"


@pytest.mark.parametrize("change,msg", [
    (lambda d: (d / "config_runtime.yaml").write_text(RUNTIME.replace("no_net_num_nodes: 1", "no_net_num_nodes: 2")),
     "one simulation on one FPGA"),
    (lambda d: (d / "config_hwdb.yaml").write_text("vcu118_rocket:\n    bitstream_tar: https://x/y.tar.gz\n"
                                                    "    custom_runtime_config: null\n"), "isn't on this machine"),
    (lambda d: (d / "../sim/output/xilinx_vcu118" / QUINT / "FireSim-xilinx_vcu118").rename(d / "gone"),
     "firesim builddriver"),
    (lambda d: (d / "config_hwdb.yaml").write_text("other:\n    agfi: x\n"), "no hardware config 'vcu118_rocket'"),
])
def test_pack_says_what_is_wrong(tmp_path, chipyard_to_change, change, msg):
    chipyard = chipyard_to_change
    change(chipyard)
    r = pack(chipyard, tmp_path / "bad")
    assert r.returncode == 1 and msg in r.stderr and not (tmp_path / "bad").exists()


def test_pack_reads_yaml_without_pyyaml():
    m = load_pack()
    doc = m.mini_yaml(RUNTIME)
    assert doc["target_config"]["default_hw_config"] == "vcu118_rocket"
    assert doc["tracing"]["enable"] is False and doc["synth_print"]["cycle_prefix"] is True
    assert doc["target_config"]["profile_interval"] == -1 and doc["workload"]["suffix_tag"] is None
    assert doc["target_config"]["plusarg_passthrough"] == ""


# ---- run-package.sh against a fake board PC

FAKES = {
    "ssh": """#!/bin/bash
while [ "$1" = -o ]; do shift 2; done
shift
export HOME="$FAKE_PC_HOME"; cd "$HOME" || exit 1
if [ "$1" = bash ] && [ "$2" = -s ]; then cat >/dev/null; echo "ok: fake PC (glibc fine)"; exit 0; fi
exec bash -c "$*"
""",
    "lspci": "#!/bin/sh\necho '01:00.0 0700: 10ee:903f'\n",
    "xvsecctl": "#!/bin/sh\necho \"$*\" >> \"$HOME/flashed\"\n",
    "sudo": "#!/bin/sh\n[ \"$1\" = -n ] && shift\nexec \"$@\"\n",
    "stty": "#!/bin/sh\nexit 0\n",
    "script": "#!/bin/bash\n# script -f -c CMD FILE\nbash -c \"$3\" > \"$4\" 2>&1\n",
    "screen": """#!/bin/bash
m="$HOME/.fsim0"
case "$1" in
  -ls) [ -e "$m" ] && printf '\\t1.fsim0\\t(Detached)\\n'; exit 0 ;;
  -S) [ "$3" = -X ] && { rm -f "$m"; exit 0; }
      touch "$m"; ( bash -c "$7"; rm -f "$m" ) >/dev/null 2>&1 & exit 0 ;;
esac
""",
}


@pytest.fixture
def fake_pc(tmp_path):
    bin_ = tmp_path / "fakebin"
    bin_.mkdir()
    for name, text in FAKES.items():
        (bin_ / name).write_text(text)
        (bin_ / name).chmod(0o755)
    home = tmp_path / "pc-home"
    home.mkdir()
    puts = tmp_path / "puts"
    launch = tmp_path / "launch"
    launch.write_text(f"#!/bin/sh\necho \"$*\" >> {puts}\ncat > /dev/null\n")
    launch.chmod(0o755)
    env = dict(os.environ, PATH=f"{bin_}:{os.environ['PATH']}", FAKE_PC_HOME=str(home), KOTL_PC="acct@10.0.0.2",
               KOTL_JOB="77", KOTL_LAUNCH=str(launch), KOTL_RUN_POLL="1")
    return env, home, puts


def run_pkg(pkg, env, cwd):
    return subprocess.run(["bash", str(FS / "run-package.sh"), str(pkg)], capture_output=True, text=True, env=env,
                          cwd=str(cwd), timeout=120)


def test_run_package_end_to_end_on_a_fake_pc(chipyard, tmp_path, fake_pc):
    env, home, puts = fake_pc
    assert pack(chipyard, tmp_path / "pkg").returncode == 0
    r = run_pkg(tmp_path / "pkg", env, tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "KOTL RESULT: PASS" in r.stdout
    assert "KOTL FACT: tool=firesim" in r.stdout and "KOTL FACT: bitstream=ref-rocket" in r.stdout
    assert "-b 0x01 -F 0x00 -c 0x1 -p bitstream/firesim.bit" in (home / "flashed").read_text()
    out = tmp_path / "firesim-results/77"
    uart = (out / "uartlog").read_text()
    assert f"+permissive {GOOD} +domain=0x0000 +bus=0x01 +device=0x00 +function=0x0" in uart
    assert "+pci-device=0x903f +permissive-off +prog0=poweroffnode-br-base-bin" in uart
    assert (out / "AUTOCOUNTERFILE0.csv").exists() and not (out / "poweroffnode-poweroffnode.ext2").exists()
    assert "put 77 uartlog" in puts.read_text() and "put 77 AUTOCOUNTERFILE0.csv" in puts.read_text()
    assert not (home / "kotl-run-77").exists()                       # its folder on the PC is gone


def test_run_package_fails_on_a_failure_line(chipyard, tmp_path, fake_pc):
    env, home, puts = fake_pc
    assert pack(chipyard, tmp_path / "pkg").returncode == 0
    r = run_pkg(tmp_path / "pkg", dict(env, FAKE_LAST_LINE="*** FAILED *** (code = 3)"), tmp_path)
    assert r.returncode == 1 and "KOTL RESULT: FAIL (the uartlog has a failure line: *** FAILED ***" in r.stdout
    r = run_pkg(tmp_path / "pkg", dict(env, FAKE_LAST_LINE="just ended"), tmp_path)
    assert r.returncode == 1 and "ended without a pass line" in r.stdout


def test_run_package_refuses_outside_a_job_or_without_a_package(chipyard, tmp_path):
    env = {k: v for k, v in os.environ.items() if not k.startswith("KOTL_")}
    r = run_pkg(tmp_path / "nothing", env, tmp_path)
    assert r.returncode == 1 and "run me inside a Kotl job" in r.stdout
    (tmp_path / "notpkg").mkdir()
    r = run_pkg(tmp_path / "notpkg", dict(env, KOTL_PC="a@b"), tmp_path)
    assert r.returncode == 1 and "isn't a run package" in r.stdout
    assert pack(chipyard, tmp_path / "pkg").returncode == 0
    with open(tmp_path / "pkg/run.conf", "a") as f:
        f.write("SIM_ARGS='+x; rm -rf /'\n")
    r = run_pkg(tmp_path / "pkg", dict(env, KOTL_PC="a@b"), tmp_path)
    assert r.returncode == 1 and "unexpected characters" in r.stdout
