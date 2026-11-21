"""The firesim wrapper: config aiming, ETA, passing through, and the lease flow (fakes)."""
import json
import os
import stat

import pytest

from kotl import slurm
from kotl.adapters.firesim import wrapper as w
from kotl.cli import main as cli

from .fakes import FakeSlurm

pytestmark = pytest.mark.feature("fsmod")

USER_CFG = """run_farm:
  base_recipe: run-farm-recipes/externally_provisioned.yaml
  recipe_arg_overrides:
    default_platform: XilinxVCU118InstanceDeployManager
    default_simulation_dir: /home/virtex-host/firesim-sim
    run_farm_hosts_to_use:
        - virtex-host@10.0.0.9: one_fpgas_spec  # old
metasimulation:
  metasimulation_enabled: false
target_config:
    default_hw_config: my_hw
"""


def test_aim_config_changes_only_the_host():
    out = w.aim_config(USER_CFG, "virtex-host@192.168.1.2")
    assert "- virtex-host@192.168.1.2: one_fpgas_spec  # old" in out
    assert out.replace("192.168.1.2", "10.0.0.9") == USER_CFG


def test_aim_config_needs_hosts():
    with pytest.raises(ValueError):
        w.aim_config("run_farm:\n  base_recipe: x\n", "a@b")


@pytest.mark.parametrize("args,expect", [
    (["runworkload"], ["runworkload", "-c", "/k/c.yaml"]),
    (["runworkload", "-c", "mine.yaml", "-a", "hw.yaml"], ["runworkload", "-c", "/k/c.yaml", "-a", "hw.yaml"]),
    (["kill", "--runtimeconfigfile=mine.yaml"], ["kill", "--runtimeconfigfile=/k/c.yaml"]),
])
def test_with_config(args, expect):
    assert w.with_config(args, "/k/c.yaml") == expect


def test_finds_the_real_firesim_after_the_wrapper(tmp_path, monkeypatch):
    mine, theirs = tmp_path / "kotlbin", tmp_path / "deploy"
    for d in (mine, theirs):
        d.mkdir()
        f = d / "firesim"
        f.write_text("#!/bin/sh\n")
        f.chmod(0o755)
    monkeypatch.setenv("PATH", f"{mine}:{theirs}")
    assert w.real_firesim([str(mine)]) == str(theirs / "firesim")


def test_settings_env_then_kotl_json(tmp_path, monkeypatch):
    monkeypatch.delenv("KOTL_ETA", raising=False)
    assert w.settings(str(tmp_path))["eta"] is None
    (tmp_path / "kotl.json").write_text(json.dumps({"eta": "2h", "max": "3h"}))
    assert w.settings(str(tmp_path)) == {"eta": "2h", "max": "3h"}
    monkeypatch.setenv("KOTL_ETA", "30m")
    assert w.settings(str(tmp_path))["eta"] == "30m"


@pytest.fixture
def flow(tmp_path, monkeypatch):
    """A fake world: Slurm, the launcher, a real-firesim stand-in, a deploy folder."""
    fs = FakeSlurm()
    for name in ("submit", "cancel", "state", "queue"):
        monkeypatch.setattr(slurm, name, getattr(fs, name))
    deploy = tmp_path / "deploy"; deploy.mkdir()
    (deploy / "config_runtime.yaml").write_text(USER_CFG)
    keys = tmp_path / "keys"; keys.mkdir(mode=0o700)
    monkeypatch.chdir(deploy)
    monkeypatch.setenv("KOTL_KEYDIR", str(keys))
    monkeypatch.setattr(w, "real_firesim", lambda: "/real/firesim")
    monkeypatch.setattr(w, "start_agent", lambda key: dict(os.environ, SSH_AUTH_SOCK="x"))
    monkeypatch.setattr(w.subprocess, "run", lambda *a, **k: None)
    calls = {"launch": [], "ran": []}
    monkeypatch.setattr(cli, "launch", lambda *a, **k: calls["launch"].append(a) or 0)
    monkeypatch.setattr(cli, "wait_running", lambda job: True)
    monkeypatch.setattr(cli, "job_status", lambda job, tries=30: {
        "board": "vcu118-pc1", "pc_address": "192.168.1.2", "pc_user": "virtex-host",
        "state": "done" if calls["launch"] and calls["launch"][-1][0] == "result" else "running"})

    def run_in_job(job, argv, env=None):
        calls["ran"].append((job, argv))
        if argv[1] == "runworkload":
            d = deploy / "results-workload" / "2026-11-22--run" / "node0"
            d.mkdir(parents=True)
            (d / "uartlog").write_text("boot...\nKOTL RESULT: PASS\n")
        return 0
    monkeypatch.setattr(slurm, "run_in_job", run_in_job)
    monkeypatch.setattr(w, "my_lease", lambda user=None: (101 if fs.submitted else None))
    return fs, calls, deploy, keys


def test_infrasetup_needs_an_eta(flow, monkeypatch):
    monkeypatch.delenv("KOTL_ETA", raising=False)
    with pytest.raises(SystemExit):
        w.main(["infrasetup"])
    assert flow[0].submitted == []


def test_runworkload_without_a_board(flow, capsys):
    with pytest.raises(SystemExit):
        w.main(["runworkload"])
    assert "run 'firesim infrasetup' first" in capsys.readouterr().err


def test_full_flow_takes_and_frees_the_board(flow, monkeypatch):
    fs, calls, deploy, keys = flow
    monkeypatch.setenv("KOTL_ETA", "1h")
    assert w.main(["infrasetup"]) == 0
    s = fs.submitted[0]
    assert s["name"] == "kotl-firesim" and s["args"] == ["sleep", "infinity"] and s["minutes"] == 60
    job, argv = calls["ran"][0]
    assert job == 101 and argv[:2] == ["/real/firesim", "infrasetup"]
    aimed = (keys / "job-101-config_runtime.yaml").read_text()
    assert "virtex-host@192.168.1.2: one_fpgas_spec" in aimed
    assert (deploy / "config_runtime.yaml").read_text() == USER_CFG       # yours is never changed
    assert fs.cancelled == []                                              # board still held

    assert w.main(["runworkload"]) == 0
    assert ("result", 101, "passed") in calls["launch"]
    assert any(c[0] == "put" and c[2] == "uartlog" for c in calls["launch"])
    assert fs.cancelled == [101]                                           # lease ended


def test_other_commands_pass_straight_through(flow, monkeypatch):
    seen = {}
    monkeypatch.setattr(os, "execv", lambda path, args: seen.update(path=path, args=args) or (_ for _ in ()).throw(SystemExit(0)))
    with pytest.raises(SystemExit):
        w.main(["buildbitstream"])
    assert seen == {"path": "/real/firesim", "args": ["/real/firesim", "buildbitstream"]}
    assert flow[0].submitted == []
