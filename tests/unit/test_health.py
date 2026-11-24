"""Health checks: one probe per PC, failures take an idle board down (with a license hold),
one driver reload is tried, warnings stay on the board, recovery brings it back (fake ssh/slurm)."""
import json
import subprocess
from pathlib import Path

import pytest

from kotl.adapters import firesim
from kotl.adapters.firesim import FireSim
from kotl.core import health
from kotl.core.config import Config
from kotl.core.launcher import Launcher, Refused
from kotl.core.registry import Registry
from kotl.ssh import SSHError

pytestmark = pytest.mark.feature("health")
HERE = "2.39-0ubuntu8.12"
GOOD = {"host": "pc1", "card": "01:00.0 Processing accelerators: Xilinx", "xdma": "xdma",
        "glibc": f"ldd (Ubuntu GLIBC {HERE}) 2.39"}


class FakePC:
    """Answers health's probe, kotl-keys busy and the driver reload."""

    def __init__(self, **state):
        self.state = dict(GOOD, **state)
        self.down = False
        self.busy = False
        self.reloads = 0
        self.reload_fixes = False

    def run(self, host, argv, timeout=60, check=True):
        if self.down:
            raise SSHError(f"{host}: no answer within 30 s")
        if argv[:2] == ["sh", "-c"]:
            return "".join(f"{k}={v}\n" for k, v in self.state.items())
        if "busy" in argv:
            self.busy_args = argv[argv.index("busy") + 1:]
            return "busy: screen, FireSim-xilinx_vcu118\n" if self.busy else "idle\n"
        if argv[-1] == firesim.RELOAD:
            self.reloads += 1
            if self.reload_fixes:
                self.state["xdma"] = "xdma"
            return ""
        raise AssertionError(argv)


class FakeHolds:
    def __init__(self):
        self.held = set()

    def hold_license(self, name, license):
        self.held.add(name)
        return True

    def release_hold(self, name):
        self.held.discard(name)
        return True


@pytest.fixture
def reg(tmp_path):
    r = Registry(str(tmp_path / "kotl.db"))
    r.add_board("vcu118-pc1", "vcu118-pc1", "vcu118")
    return r


def run(reg, pc, holds, adapters=None):
    adapters = [FireSim(here=HERE)] if adapters is None else adapters
    return health.run(reg, ssh=pc, slurm=holds, admin="boss", account="virtex-host", adapters=adapters)


@pytest.mark.parametrize("text,version", [
    (f"ldd (Ubuntu GLIBC {HERE}) 2.39\nCopyright", HERE), ("ldd (GNU libc) 2.35\n", "2.35"), ("", ""),
])
def test_glibc_version(text, version):
    assert firesim.glibc_version(firesim.glibc_line(text)) == version


def test_healthy_board_stays_idle(reg):
    holds = FakeHolds()
    assert run(reg, FakePC(), holds) == {"vcu118-pc1": []}
    b = reg.board("vcu118-pc1")
    assert b["state"] == "idle" and b["last_healthy"] and not holds.held


def test_missing_driver_tries_one_reload_then_goes_down(reg):
    pc, holds = FakePC(xdma=""), FakeHolds()
    found = run(reg, pc, holds)["vcu118-pc1"]
    assert pc.reloads == 1 and "tried one XDMA driver reload" in found
    assert reg.board("vcu118-pc1")["state"] == "down" and holds.held == {"kotl-down-vcu118-pc1"}
    assert "vcu118-pc1 is DOWN: XDMA driver not loaded" in reg.notices("boss")[0]["text"]
    run(reg, pc, holds)
    assert pc.reloads == 1                                  # one reload per down period, not every 5 min
    assert len(reg.notices("boss")) == 1                    # and one notice


def test_reload_that_works_keeps_the_board(reg):
    pc, holds = FakePC(xdma=""), FakeHolds()
    pc.reload_fixes = True
    found = run(reg, pc, holds)["vcu118-pc1"]
    assert reg.board("vcu118-pc1")["state"] == "idle" and not holds.held
    assert found == ["tried one XDMA driver reload"]


def test_unreachable_goes_down_and_comes_back(reg):
    pc, holds = FakePC(), FakeHolds()
    pc.down = True
    run(reg, pc, holds)
    assert reg.board("vcu118-pc1")["state"] == "down" and pc.reloads == 0
    pc.down = False
    run(reg, pc, holds)
    assert reg.board("vcu118-pc1")["state"] == "idle" and not holds.held
    assert [n["text"] for n in reg.notices("boss")][0] == "vcu118-pc1 is back UP: its checks pass again"


def test_no_reload_while_a_job_holds_the_board(reg):
    # FireSim's infrasetup unloads XDMA, flashes, then loads it with poll_mode=1 only if it
    # isn't loaded: a reload from the health check in between would leave the wrong driver
    reg.claim(41, "vcu118")
    pc, holds = FakePC(xdma=""), FakeHolds()
    found = run(reg, pc, holds)["vcu118-pc1"]
    assert pc.reloads == 0 and reg.board("vcu118-pc1")["state"] == "busy"
    assert any("goes down when job 41 ends" in f for f in found)


def test_busy_board_is_never_taken_from_a_job(reg):
    reg.claim(41, "vcu118")
    pc, holds = FakePC(card=""), FakeHolds()
    found = run(reg, pc, holds)["vcu118-pc1"]
    assert reg.board("vcu118-pc1")["state"] == "busy" and not holds.held
    assert any("goes down when job 41 ends" in f for f in found)
    reg.release(41)
    run(reg, pc, holds)
    assert reg.board("vcu118-pc1")["state"] == "down"


def test_glibc_and_unleased_work_are_warnings(reg):
    pc, holds = FakePC(glibc="ldd (Ubuntu GLIBC 2.35-0ubuntu3.13) 2.35"), FakeHolds()
    pc.busy = True
    found = run(reg, pc, holds)["vcu118-pc1"]
    assert reg.board("vcu118-pc1")["state"] == "idle"
    assert any("older glibc release (2.35 vs 2.39)" in f and "--use-pc-glibc" in f for f in found)
    assert any(f.startswith("outside Kotl: work runs on the PC as virtex-host with no Kotl job holding the board: "
                            "screen, FireSim-xilinx_vcu118") for f in found)


def test_patch_gap_suggests_upgrade():
    w = firesim.glibc_warning(HERE, "2.39-0ubuntu8.9")
    assert "upgrade libc6" in w and "older glibc release" not in w


def test_registry_migrates_an_old_database(tmp_path):
    import sqlite3
    db = tmp_path / "old.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE boards (name TEXT PRIMARY KEY, host TEXT NOT NULL, type TEXT NOT NULL, "
                "state TEXT NOT NULL DEFAULT 'idle', job_id INTEGER, bitstream TEXT, driver_version TEXT, "
                "last_healthy TEXT, power_watts REAL)")
    con.execute("INSERT INTO boards(name, host, type) VALUES ('b', 'h', 'vcu118')")
    con.commit(); con.close()
    reg = Registry(str(db))
    reg.set_warnings("b", ["x"])
    assert reg.warnings("b") == ["x"]


def test_only_kotl_or_admin_runs_checks(tmp_path, monkeypatch):
    for d in ("var/lib/kotl", "srv/kotl/out", "etc/kotl"):
        (tmp_path / d).mkdir(parents=True)
    (tmp_path / "etc/kotl/kotl.conf").write_text("admin = boss\n")
    cfg = Config(prefix=str(tmp_path))
    monkeypatch.setattr(firesim, "local_glibc", lambda: HERE)
    Launcher(cfg, who="kotl").reg.add_board("vcu118-pc1", "vcu118-pc1", "vcu118")
    with pytest.raises(Refused):
        Launcher(cfg, who="alice", ssh=FakePC(), slurm=FakeHolds()).health()
    Launcher(cfg, who="boss", ssh=FakePC(card=""), slurm=FakeHolds()).health()
    assert "! no Xilinx card" in Launcher(cfg, who="alice").boards_table()   # everyone sees it


def test_health_sh_always_exits_0():
    r = subprocess.run(["sh", str(Path(__file__).resolve().parents[2] / "deploy/health.sh")])
    assert r.returncode == 0


def test_long_process_lists_are_capped():
    class Many(FakePC):
        def run(self, host, argv, timeout=60, check=True):
            if "busy" in argv:
                return "busy: " + ", ".join(f"p{i}" for i in range(20)) + "\n"
            return super().run(host, argv, timeout, check)
    assert health.pc_busy({"host": "pc"}, "virtex-host", Many()) == "p0, p1, p2, p3, p4, p5, p6, p7 and 12 more"


# ---- the core is generic: without the FireSim adapter it knows nothing of XDMA, glibc or FireSim

def test_without_adapters_only_generic_checks(reg):
    pc, holds = FakePC(xdma="", glibc="ldd (Ubuntu GLIBC 2.35-0ubuntu3.13) 2.35"), FakeHolds()
    found = run(reg, pc, holds, adapters=[])["vcu118-pc1"]
    assert found == [] and pc.reloads == 0 and reg.board("vcu118-pc1")["state"] == "idle"
    assert "xdma" not in health.probe_script({"type": "vcu118"}) and "ldd" not in health.probe_script({"type": "vcu118"})
    pc.state["card"] = ""
    assert run(reg, pc, holds, adapters=[])["vcu118-pc1"] == ["no Xilinx card on PCI (lspci -d 10ee:)"]


def test_firesim_adapter_adds_its_probe_and_work_names(reg):
    pc = FakePC()
    pc.busy = True
    run(reg, pc, FakeHolds())
    assert pc.busy_args == ["--proc", "FireSim-"]
    assert "xdma=" in health.probe_script({"type": "vcu118"}, [FireSim(here=HERE)])
    run(reg, pc, FakeHolds(), adapters=[])
    assert pc.busy_args == []


def test_unknown_board_type_skips_the_card_check():
    assert "lspci" not in health.probe_script({"type": "mystery"})
    assert health.failures_of({"type": "mystery"}, {"host": "h"}) == []


def test_core_has_no_firesim_knowledge():
    core = Path(__file__).resolve().parents[2] / "kotl/core"
    for f in core.glob("*.py"):
        text = f.read_text()
        for word in ("xdma", "glibc", "fsim0", "FireSim-"):
            assert word not in text, f"kotl/core/{f.name} mentions {word}"


# ---- work outside Kotl: who (from the workstation's connection table) and how long; never acted on

def test_connected_users_reads_the_connection_table(tmp_path):
    import os, pwd
    from kotl.core import outside
    me = pwd.getpwuid(os.getuid())
    pc = "0201A8C0:0016"                                   # 192.168.1.2:22, little-endian hex
    table = tmp_path / "tcp"
    table.write_text("  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid\n"
                     f"   0: 0101A8C0:D431 {pc} 01 00000000:00000000 00:00000000 00000000 {me.pw_uid} 0 1\n"
                     f"   1: 0101A8C0:D432 {pc} 01 00000000:00000000 00:00000000 00000000 {me.pw_uid} 0 1\n"
                     f"   2: 0101A8C0:D433 {pc} 06 00000000:00000000 00:00000000 00000000 {me.pw_uid} 0 1\n"
                     f"   3: 0101A8C0:D434 0301A8C0:0016 01 00000000:00000000 00:00000000 00000000 {me.pw_uid} 0 1\n")
    assert outside.connected_users("192.168.1.2", tables=[str(table)]) == {me.pw_name: 2}   # closed and other PCs don't count
    assert outside.describe({me.pw_name: 2, "zed": 1}) == f"{me.pw_name} (2 connections), zed"
    assert outside.connected_users("not-an-ip", tables=[str(table)]) == {}


def test_outside_note_says_who_and_how_long():
    class PC:
        def address(self, host):
            return "192.168.1.2"
    note = health.outside_note({"host": "vcu118-pc1"}, "virtex-host", "screen, FireSim-xilinx_vcu118; for 750", PC(),
                               connected=lambda a: {"alice": 2})
    assert note == ("outside Kotl: work runs on the PC as virtex-host for 12m with no Kotl job holding the board: "
                    "screen, FireSim-xilinx_vcu118; connected from the workstation now: alice (2 connections)")
