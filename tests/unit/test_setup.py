"""kotl setup (workstation) and the client bundle + installer (a user's own PC), with stand-in
claude / code / code-server / ssh commands in a scratch HOME: nothing real is touched."""
import io
import json
import os
import subprocess
import tarfile
from pathlib import Path

import pytest

from kotl.cli import client, setup

pytestmark = pytest.mark.feature("setup")
ROOT = Path(__file__).resolve().parents[2]


def fake(bindir, name, log):
    bindir.mkdir(parents=True, exist_ok=True)
    f = bindir / name
    f.write_text(f'#!/bin/sh\necho "{name} $*" >> {log}\ncase "$*" in *"marketplace list"*) echo "${{KOTL_FAKE_LIST:-}}";; esac\nexit 0\n')
    f.chmod(0o755)
    return f


@pytest.fixture
def opt(tmp_path):
    o = tmp_path / "opt"
    for d in ("plugin/.claude-plugin", "plugin-band/.claude-plugin", ".claude-plugin", "client"):
        (o / d).mkdir(parents=True)
    (o / "plugin/.claude-plugin/plugin.json").write_text('{"name": "kotl"}')
    (o / "plugin-band/.claude-plugin/plugin.json").write_text('{"name": "kotl-band"}')
    (o / ".claude-plugin/marketplace.json").write_text('{"name": "kotl"}')
    (o / "kotl-status.vsix").write_bytes(b"PK fake")
    (o / "client/install.sh").write_text((ROOT / "deploy/client/install.sh").read_text())
    return o


def test_setup_installs_plugins_and_extension(tmp_path, opt, monkeypatch):
    log = tmp_path / "log"
    bin_ = tmp_path / "bin"
    fake(bin_, "claude", log)
    server = fake(tmp_path / "home/.vscode-server/cli/servers/Stable-abc/server/bin", "code-server", log)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PATH", f"{bin_}:/usr/bin:/bin")
    monkeypatch.setattr(setup, "member_of_kotl_users", lambda u: True)
    monkeypatch.setattr(setup, "in_kotl_users", lambda: True)
    lines = []
    assert setup.setup(out=lines.append, opt=str(opt)) == 0
    calls = log.read_text().splitlines()
    assert f"claude plugin marketplace add {opt}" in calls
    assert "claude plugin install kotl@kotl" in calls and "claude plugin install kotl-band@kotl" in calls
    assert f"code-server --install-extension {opt}/kotl-status.vsix --force" in calls
    assert any("Reload Window" in l for l in lines)


def test_setup_is_safe_to_rerun_and_undo(tmp_path, opt, monkeypatch):
    log = tmp_path / "log"
    fake(tmp_path / "bin", "claude", log)
    fake(tmp_path / "home/.vscode-server/cli/servers/Stable-abc/server/bin", "code-server", log)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PATH", f"{tmp_path / 'bin'}:/usr/bin:/bin")
    monkeypatch.setenv("KOTL_FAKE_LIST", "kotl (directory: /opt/kotl)")
    monkeypatch.setattr(setup, "member_of_kotl_users", lambda u: True)
    monkeypatch.setattr(setup, "in_kotl_users", lambda: True)
    lines = []
    setup.setup(out=lines.append, opt=str(opt))
    assert "marketplace kotl already added" in "\n".join(lines)
    assert not any("marketplace add" in c for c in log.read_text().splitlines())
    setup.setup(undo=True, out=lines.append, opt=str(opt))
    calls = log.read_text().splitlines()
    assert "claude plugin uninstall kotl@kotl" in calls and "claude plugin marketplace remove kotl" in calls
    assert "code-server --uninstall-extension kotl.kotl-status" in calls


def test_setup_without_vscode_server_or_group(tmp_path, opt, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    monkeypatch.setattr(setup, "member_of_kotl_users", lambda u: False)
    lines = []
    assert setup.setup(out=lines.append, opt=str(opt)) == 1
    text = "\n".join(lines)
    assert "not in kotl-users" in text and "connect VS Code to it once" in text


def test_client_bundle_holds_everything(opt):
    data = client.bundle(opt=str(opt), workstation="comparch.example")
    t = tarfile.open(fileobj=io.BytesIO(data))
    names = set(t.getnames())
    for n in ("kotl-client/install.sh", "kotl-client/kotl-status.vsix", "kotl-client/plugin/.claude-plugin/plugin.json",
              "kotl-client/plugin-band/.claude-plugin/plugin.json", "kotl-client/.claude-plugin/marketplace.json"):
        assert n in names, n
    assert t.extractfile("kotl-client/workstation").read() == b"comparch.example\n"


def test_client_bundle_says_what_is_missing(tmp_path):
    with pytest.raises(FileNotFoundError, match="deploy/kotl/install.sh"):
        client.bundle(opt=str(tmp_path))


def test_client_installer_on_a_users_pc(tmp_path, opt):
    t = tarfile.open(fileobj=io.BytesIO(client.bundle(opt=str(opt), workstation="comparch")))
    t.extractall(tmp_path / "dl", filter="data")
    home, log = tmp_path / "pc-home", tmp_path / "log"
    for name in ("claude", "code", "ssh"):
        fake(tmp_path / "bin", name, log)
    env = {"HOME": str(home), "PATH": f"{tmp_path / 'bin'}:/usr/bin:/bin"}
    r = subprocess.run(["sh", str(tmp_path / "dl/kotl-client/install.sh")], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    calls = log.read_text().splitlines()
    assert f"claude plugin marketplace add {home}/.kotl-client" in calls
    assert "claude plugin install kotl-band@kotl" in calls
    assert f"code --install-extension {home}/.kotl-client/kotl-status.vsix --force" in calls
    assert json.loads((home / ".claude/settings.json").read_text())["env"]["KOTL_SSH"] == "comparch"
    assert (home / ".kotl-client/ssh").read_text().strip() == "comparch"
    r = subprocess.run(["sh", str(home / ".kotl-client/install.sh"), "--undo"], env=env, capture_output=True, text=True)
    assert r.returncode == 0 and not (home / ".kotl-client").exists()
    assert "env" not in json.loads((home / ".claude/settings.json").read_text())
    assert "code --uninstall-extension kotl.kotl-status" in log.read_text()
