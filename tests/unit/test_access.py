"""PC access: job keys added at start and removed at the end (fake ssh), and kotl-keys itself."""
import os
import subprocess
from pathlib import Path

import pytest

from kotl.core import results
from kotl.core.config import Config
from kotl.core.launcher import Launcher, Refused

from .fakes import FakeSlurm

pytestmark = pytest.mark.feature("access")
KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIBk3p0P8bKzm3nKQwqtOuB0Gk8sV2bT9H2yq8Ah5c0xQ"
HELPER = Path(__file__).resolve().parents[2] / "deploy/pc/kotl-keys"


class FakeSSH:
    SSHError = RuntimeError

    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def run(self, host, argv, timeout=60, check=True):
        from kotl.ssh import SSHError
        self.calls.append((host, list(argv)))
        if self.fail:
            raise SSHError(f"{host}: unreachable")
        return ""

    def address(self, host):
        return "192.168.1.2"


@pytest.fixture
def world(tmp_path):
    for d in ("var/lib/kotl", "srv/kotl/out", "etc/kotl"):
        (tmp_path / d).mkdir(parents=True)
    (tmp_path / "etc/kotl/kotl.conf").write_text("admin = boss\npc_account = virtex-host\n")
    cfg, fs = Config(prefix=str(tmp_path)), FakeSlurm()

    def make(who, ssh):
        L = Launcher(cfg, slurm=fs, who=who, ssh=ssh)
        L.spawn_watcher = lambda job: None
        return L
    make("kotl", FakeSSH()).reg.add_board("vcu118-pc1", "vcu118-pc1", "vcu118")
    return cfg, fs, make


def test_key_added_at_start_and_removed_at_end(world):
    cfg, fs, make = world
    ssh = FakeSSH()
    fs.add(7, "alice")
    L = make("alice", ssh)
    L.start(7, "firesim", pubkey=KEY)
    assert ssh.calls[0] == ("vcu118-pc1", ["sudo", "-n", "-u", "virtex-host", "/usr/local/bin/kotl-keys", "add", "7", KEY])
    st = results.read_status(results.job_dir(cfg.out, "alice", 7))
    assert st["pc_address"] == "192.168.1.2" and st["pc_user"] == "virtex-host"
    L.end(7, signal=True)
    assert ssh.calls[-1][1][-3:] == ["remove", "7", "soft"]


@pytest.mark.parametrize("bad", [
    'command="rm -rf /" ' + KEY,                     # options smuggled in front
    KEY + "\nssh-ed25519 AAAAother",                  # a second key
    "ssh-rsa AAAAB3NzaC1yc2E",                        # other key types
    KEY + " comment; rm -rf /",
])
def test_only_a_bare_ed25519_key_is_accepted(world, bad):
    cfg, fs, make = world
    fs.add(7, "alice")
    with pytest.raises(Refused, match="one ssh-ed25519"):
        make("alice", FakeSSH()).start(7, "run", pubkey=bad)
    assert make("kotl", FakeSSH()).reg.board("vcu118-pc1")["state"] == "idle"


def test_unreachable_pc_refuses_and_frees_the_board(world):
    cfg, fs, make = world
    fs.add(7, "alice")
    with pytest.raises(Refused, match="could not give job 7 access"):
        make("alice", FakeSSH(fail=True)).start(7, "run", pubkey=KEY)
    L = make("kotl", FakeSSH())
    assert L.reg.board("vcu118-pc1")["state"] == "idle" and L.reg.job(7)["result"] == "no_access"


def test_failed_removal_never_blocks_the_end(world):
    cfg, fs, make = world
    fs.add(7, "alice")
    make("alice", FakeSSH()).start(7, "run", pubkey=KEY)
    assert make("alice", FakeSSH(fail=True)).end(7, rc=0) == "succeeded"
    log = open(os.path.join(results.job_dir(cfg.out, "alice", 7), "launcher.log")).read()
    assert "could not remove the job key" in log


def test_full_lockdown_asks_for_full_removal(world):
    cfg, fs, make = world
    with open(cfg.conf_file, "a") as f:
        f.write("lockdown = full\n")
    ssh = FakeSSH()
    fs.add(7, "alice")
    make("alice", ssh).start(7, "run", pubkey=KEY)
    make("alice", ssh).end(7, rc=0)
    assert ssh.calls[-1][1][-1] == "full"


def test_owner_result_and_put(world):
    cfg, fs, make = world
    import io
    fs.add(7, "alice")
    L = make("alice", FakeSSH())
    L.start(7, "firesim")
    with pytest.raises(Refused):
        L.set_result(7, "amazing")
    L.set_result(7, "passed")
    with pytest.raises(Refused):
        L.put(7, "../escape", io.BytesIO(b"x"))
    L.put(7, "uartlog", io.BytesIO(b"KOTL RESULT: PASS\n"))
    assert L.end(7, signal=True) == "passed"
    with pytest.raises(Refused):
        make("bob", FakeSSH()).set_result(7, "failed")


# ---- kotl-keys, run locally against a scratch home folder

def keys(home, *args):
    env = dict(os.environ, KOTL_KEYS_TEST_HOME=str(home))
    return subprocess.run(["sh", str(HELPER), *args], capture_output=True, text=True, env=env)


def test_kotl_keys_add_remove_keeps_other_keys(tmp_path):
    ak = tmp_path / ".ssh" / "authorized_keys"
    ak.parent.mkdir()
    ak.write_text("ssh-ed25519 AAAAyours you@laptop\n")
    assert keys(tmp_path, "add", "42", KEY).returncode == 0
    assert keys(tmp_path, "add", "43", KEY).returncode == 0
    text = ak.read_text()
    assert f"restrict,pty {KEY} kotl-job-42\n" in text and "you@laptop" in text
    assert keys(tmp_path, "list").stdout.split() == ["42", "43"]
    assert keys(tmp_path, "remove", "42").returncode == 0
    assert ak.read_text() == f"ssh-ed25519 AAAAyours you@laptop\nrestrict,pty {KEY} kotl-job-43\n"
    assert oct(ak.stat().st_mode & 0o777) == "0o600"


@pytest.mark.parametrize("args", [
    ["add", "4x", KEY], ["add", "42", "ssh-rsa AAAA"], ["add", "42", 'from="*" ' + KEY], ["remove", ""], ["nuke"],
])
def test_kotl_keys_refuses_bad_input(tmp_path, args):
    (tmp_path / ".ssh").mkdir()
    r = keys(tmp_path, *args)
    assert r.returncode == 2
    assert (tmp_path / ".ssh" / "authorized_keys").read_text() == ""


def test_kotl_keys_busy_answers(tmp_path):
    (tmp_path / ".ssh").mkdir()
    r = keys(tmp_path, "busy")
    out = r.stdout.strip()
    assert r.returncode == 0 and (out == "idle" or out.startswith("busy: "))
    if out != "idle":
        assert "kotl-keys" not in out and " ps" not in out           # this check itself isn't counted


def test_kotl_keys_remove_takes_the_adapters_names(tmp_path):
    (tmp_path / ".ssh").mkdir()
    keys(tmp_path, "add", "42", KEY)
    r = keys(tmp_path, "remove", "42", "soft", "--screen", "fsim", "--proc", "FireSim-")
    assert r.returncode == 0 and "screens: fsim procs: FireSim-" in r.stdout
    assert keys(tmp_path, "list").stdout.split() == []
    r = keys(tmp_path, "remove", "43")
    assert r.returncode == 0 and "screens: none procs: none" in r.stdout          # generic: names nothing


@pytest.mark.parametrize("bad", [["--proc", "a b"], ["--proc", "x;rm"], ["--screen", ""], ["--nuke", "x"]])
def test_kotl_keys_refuses_bad_names(tmp_path, bad):
    (tmp_path / ".ssh").mkdir()
    keys(tmp_path, "add", "42", KEY)
    assert keys(tmp_path, "remove", "42", "soft", *bad).returncode == 2
    assert keys(tmp_path, "list").stdout.split() == ["42"]                       # nothing removed on bad input


def test_end_step_passes_the_adapters_names():
    from kotl.adapters import load, stop_args, work_args
    assert stop_args(load("firesim")) == ["--screen", "fsim", "--proc", "FireSim-"]
    assert work_args(load("firesim")) == ["--proc", "FireSim-"]
    assert stop_args(load("")) == [] and work_args(load("")) == []


def test_end_step_runs_the_firesim_root_stop_only_with_the_adapter(world):
    cfg, fs, make = world
    for adapters, expect in (("firesim", True), ("", False)):
        conf = cfg.path("/etc/kotl/kotl.conf")
        open(conf, "w").write(f"admin = boss\npc_account = virtex-host\nadapters = {adapters}\n")
        cfg.settings = {}
        ssh = FakeSSH()
        job = 90 if expect else 91
        fs.add(job, "alice")
        L = make("alice", ssh)
        L.start(job, "run", pubkey=KEY)
        L.end(job, signal=True)
        stop = ("vcu118-pc1", ["sudo", "-n", "/usr/local/bin/kotl-firesim-stop"])
        assert (stop in ssh.calls) == expect
        if expect:
            remove = next(i for i, c in enumerate(ssh.calls) if "remove" in c[1])
            assert ssh.calls.index(stop) > remove                    # after the key is out
            assert ssh.calls[remove][1][-4:] == ["--screen", "fsim", "--proc", "FireSim-"]
