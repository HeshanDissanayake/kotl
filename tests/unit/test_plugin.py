"""The Kotl plugin for Claude Code: manifest, marketplace, skill, and its hook scripts."""
import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.feature("plugin")
ROOT = Path(__file__).resolve().parents[2]
PLUGIN = ROOT / "plugin"


def sh(script, stdin="", env=None, path_dirs=()):
    e = {"PATH": ":".join([*map(str, path_dirs), "/usr/bin", "/bin"]), **(env or {})}
    return subprocess.run(["sh", str(PLUGIN / "hooks" / script)], input=stdin, capture_output=True, text=True, env=e)


def fake(dirpath, name, body):
    dirpath.mkdir(exist_ok=True)
    f = dirpath / name
    f.write_text("#!/bin/sh\n" + body)
    f.chmod(0o755)
    return dirpath


def test_manifest_marketplace_and_skill():
    m = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text())
    assert m["name"] == "kotl" and m["version"]
    mk = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
    entry = [p for p in mk["plugins"] if p["name"] == "kotl"][0]
    assert (ROOT / entry["source"] / ".claude-plugin/plugin.json").exists()
    skill = (PLUGIN / "skills/kotl/SKILL.md").read_text()
    front = skill.split("---")[1]
    assert "name: kotl" in front and "description:" in front
    for must in ("kotl run --eta", "kotl lease", "kotl release", "KOTL RESULT: PASS", "kotl fetch", "status.json"):
        assert must in skill


def test_hooks_json_points_at_real_scripts():
    hooks = json.loads((PLUGIN / "hooks/hooks.json").read_text())["hooks"]
    assert set(hooks) == {"SessionStart", "PreToolUse"}
    for event in hooks.values():
        for group in event:
            for h in group["hooks"]:
                script = h["command"].split("/hooks/")[1].rstrip('"')
                assert (PLUGIN / "hooks" / script).exists(), script


@pytest.mark.parametrize("command,asks", [
    ("cd deploy && firesim runworkload -c x.yaml", True),
    ("firesim infrasetup", True),
    ("firesim kill -c a.yaml", True),
    ('kotl run --eta 30m -- sh -c "firesim infrasetup -c X && firesim runworkload -c X"', False),
    ("ssh $KOTL_PC hostname; firesim runworkload  # inside a lease, KOTL_JOB=$KOTL_JOB", False),
    ("firesim buildbitstream", False),
    ("ls -la", False),
])
def test_pre_bash_asks_only_for_board_commands_outside_kotl(command, asks):
    r = sh("pre-bash.sh", json.dumps({"tool_name": "Bash", "tool_input": {"command": command}}))
    assert r.returncode == 0
    if asks:
        out = json.loads(r.stdout)["hookSpecificOutput"]
        assert out["permissionDecision"] == "ask" and "kotl run --eta" in out["permissionDecisionReason"]
    else:
        assert r.stdout.strip() == ""


def test_pre_bash_ignores_garbage():
    assert sh("pre-bash.sh", "not json").returncode == 0


def test_kotl_cmd_local_then_ssh_then_nothing(tmp_path):
    local = fake(tmp_path / "local", "kotl", 'echo "local kotl: $*"\n')
    assert sh("kotl-cmd.sh", path_dirs=[local]).stdout.strip() == "local kotl:"
    remote = fake(tmp_path / "remote", "ssh", 'echo "ssh: $*"\n')
    env = {"KOTL_SSH": "comparch"}
    r = subprocess.run(["sh", str(PLUGIN / "hooks/kotl-cmd.sh"), "logs", "41", "it's"],
                       capture_output=True, text=True, env={"PATH": f"{remote}:/usr/bin:/bin", **env})
    assert r.stdout.strip() == "ssh: -o BatchMode=yes -o ConnectTimeout=5 comparch kotl 'logs' '41' 'it'\\''s'"
    r = subprocess.run(["sh", str(PLUGIN / "hooks/kotl-cmd.sh"), "status"], capture_output=True, text=True,
                       env={"PATH": "/usr/bin:/bin"})
    assert r.returncode == 127


def test_session_start_shows_queue_and_unread_notices(tmp_path):
    k = fake(tmp_path / "bin", "kotl", '''case "$1" in
  status) echo "vcu118-pc1   idle"; echo "kotl: 1 unread notice: kotl notices" ;;
  notices) [ "$2" = "--peek" ] && echo "* 11-23 20:15  job 52 passed its ETA (1m)" ;;
esac
''')
    r = sh("session-start.sh", path_dirs=[k])
    assert r.returncode == 0
    assert "Kotl right now:" in r.stdout and "never stop board work" in r.stdout and "vcu118-pc1   idle" in r.stdout
    assert "job 52 passed its ETA" in r.stdout and "not marked read" in r.stdout


def test_session_start_is_quiet_without_kotl():
    r = sh("session-start.sh")
    assert r.returncode == 0 and r.stdout == ""


def test_band_plugin_is_listed_and_shaped():
    mk = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
    band = [p for p in mk["plugins"] if p["name"] == "kotl-band"][0]
    root = ROOT / band["source"]
    assert json.loads((root / ".claude-plugin/plugin.json").read_text())["name"] == "kotl-band"
    assert json.loads((root / "hooks/hooks.json").read_text()) == {"modules": ["./register.tsx"]}
    src = (root / "hooks/register.tsx").read_text()
    assert "'kotl', 'status', '--json'" in src and "$.process.run" in src
    assert "kotl run" not in src and "scancel" not in src          # read-only: never starts or stops a job


@pytest.mark.skipif(not __import__("shutil").which("claude"), reason="Claude Code isn't installed here")
def test_band_mod_tests_pass():
    r = subprocess.run(["claude", "plugin", "test", str(ROOT / "plugin-band")], capture_output=True, text=True, timeout=300)
    assert r.returncode == 0 and " 0 fail" in r.stdout + r.stderr, (r.stdout + r.stderr)[-2000:]


VSCODE = ROOT / "vscode-kotl"


@pytest.mark.skipif(not __import__("shutil").which("node"), reason="node isn't installed here")
def test_vscode_extension_format_tests_pass():
    r = subprocess.run(["node", "--test", "test/"], cwd=VSCODE, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and "# fail 0" in r.stdout, r.stdout[-2000:]


def test_vscode_extension_packages(tmp_path):
    import zipfile
    r = subprocess.run(["python3", str(VSCODE / "build_vsix.py"), str(tmp_path)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    names = zipfile.ZipFile(r.stdout.strip()).namelist()
    assert {"extension.vsixmanifest", "extension/package.json", "extension/extension.js", "extension/format.js"} <= set(names)
    pkg = json.loads((VSCODE / "package.json").read_text())
    assert pkg["main"] == "./extension.js" and "onStartupFinished" in pkg["activationEvents"]
    src = (VSCODE / "extension.js").read_text()
    assert "'status', '--json'" in src and "scancel" not in src and "kotl run" not in src   # read-only


def nudge_plugin(tmp_path, mine, current):
    import shutil
    plug = tmp_path / "plugin"
    shutil.copytree(PLUGIN, plug)
    if mine:
        (plug / "BUILD").write_text(mine + "\n")
    k = fake(tmp_path / "bin", "kotl", f'''case "$1" in
  status) echo "vcu118-pc1   idle" ;;
  version) echo "{current}" ;;
esac
''')
    e = {"PATH": f"{k}:/usr/bin:/bin"}
    return subprocess.run(["sh", str(plug / "hooks/session-start.sh")], capture_output=True, text=True, env=e)


def test_session_start_says_when_kotl_was_updated(tmp_path):
    r = nudge_plugin(tmp_path, "1.0.0+aaa", "1.0.0+bbb")
    assert "Kotl was updated (1.0.0+bbb" in r.stdout and "kotl setup" in r.stdout
    assert "Kotl was updated" not in nudge_plugin(tmp_path / "same", "1.0.0+bbb", "1.0.0+bbb").stdout
    assert "Kotl was updated" not in nudge_plugin(tmp_path / "dev", "", "1.0.0+bbb").stdout   # a checkout


def test_vscode_extension_carries_the_build(tmp_path):
    import zipfile
    r = subprocess.run(["python3", str(VSCODE / "build_vsix.py"), str(tmp_path), "1.0.0+abc"], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert zipfile.ZipFile(r.stdout.strip()).read("extension/BUILD") == b"1.0.0+abc\n"
    src = (VSCODE / "extension.js").read_text()
    assert "Kotl was updated" in src and "kotl setup" in src and "'kotl.nudged'" in src
