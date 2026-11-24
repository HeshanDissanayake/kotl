"""M1 deploy scripts, run in --dry-run mode: nothing on this machine changes.

Files land under a temporary KOTL_ROOT, and commands are printed as 'would run: ...'.
The real install is checked by deploy/verify-m1.sh after the admin runs the scripts.
"""
import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "deploy"
SCRIPTS = {  # script -> feature it belongs to
    "lib.sh": "os", "accounts.sh": "os", "verify-m1.sh": "os",
    "slurm/install.sh": "queue", "epilog.sh": "starter", "health.sh": "health",
    "ssh/setup-kotl-key.sh": "key", "pc/setup.sh": "pc1", "adapters/firesim/check.sh": "fsmod",
    "kotl/install.sh": "launcher", "job.sh": "launcher",
    "pc/kotl-keys": "access", "adapters/firesim/pc-setup.sh": "fsmod",
}


def dry(script, *args, root, check=True):
    env = dict(os.environ, KOTL_ROOT=str(root))
    r = subprocess.run(["bash", str(DEPLOY / script), "--dry-run", *args],
                       capture_output=True, text=True, env=env)
    if check:
        assert r.returncode == 0, r.stdout + r.stderr
    return r


def me():
    return subprocess.run(["id", "-un"], capture_output=True, text=True).stdout.strip()


# ---- every script parses, and has no lab user names baked in

@pytest.mark.parametrize("script", sorted(SCRIPTS))
def test_script_syntax(script, request):
    request.node.add_marker(pytest.mark.feature(SCRIPTS[script]))
    r = subprocess.run(["bash", "-n", str(DEPLOY / script)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


@pytest.mark.feature("os")
def test_no_user_names_in_deploy():
    # people's names come from the machine at run time, never from git
    text = "".join(p.read_text() for p in DEPLOY.rglob("*") if p.is_file())
    assert me() not in text


@pytest.mark.feature("os")
def test_scripts_refuse_without_root_or_dry_run(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("running as root")
    r = subprocess.run(["bash", str(DEPLOY / "slurm/install.sh")], capture_output=True, text=True)
    assert r.returncode != 0 and "run as root" in r.stderr


# ---- accounts.sh (os)

@pytest.mark.feature("os")
def test_accounts_install(tmp_path):
    r = dry("accounts.sh", "install", "--admin", me(), root=tmp_path)
    conf = (tmp_path / "etc/kotl/kotl.conf").read_text()
    assert "lockdown = soft" in conf and f"admin = {me()}" in conf and "pc_account = virtex-host" in conf
    assert "would run: groupadd -f kotl-users" in r.stdout
    assert "would run: passwd -l kotl" in r.stdout
    assert f"would run: gpasswd -a {me()} kotl-users" in r.stdout
    for d in ("var/lib/kotl", "srv/kotl/jobs", "srv/kotl/out", "opt/kotl/bin"):
        assert (tmp_path / d).is_dir()
    assert oct((tmp_path / "srv/kotl").stat().st_mode & 0o777) == "0o711"


@pytest.mark.feature("os")
def test_sudoers_rule_is_valid_and_narrow(tmp_path):
    dry("accounts.sh", "install", "--admin", me(), root=tmp_path)
    f = tmp_path / "etc/sudoers.d/kotl"
    assert subprocess.run(["visudo", "-cf", str(f)], capture_output=True).returncode == 0
    rules = [l for l in f.read_text().splitlines() if l and not l.startswith("#")]
    assert rules == ["%kotl-users ALL=(kotl) NOPASSWD: /opt/kotl/launch, /opt/kotl/attach"]
    assert oct(f.stat().st_mode & 0o777) == "0o440"


@pytest.mark.feature("os")
def test_set_admin_and_users(tmp_path):
    dry("accounts.sh", "install", "--admin", me(), root=tmp_path)
    r = dry("accounts.sh", "set-admin", "root", root=tmp_path)
    assert "admin = root" in (tmp_path / "etc/kotl/kotl.conf").read_text()
    assert "sacctmgr -i modify user name=root set qos+=urgent,maint" in r.stdout
    r = dry("accounts.sh", "add-user", me(), root=tmp_path)
    assert f"gpasswd -a {me()} kotl-users" in r.stdout
    r = dry("accounts.sh", "remove-user", "root", root=tmp_path, check=False)
    assert r.returncode != 0 and "is the admin" in r.stderr
    r = dry("accounts.sh", "add-user", "no-such-user-kotl", root=tmp_path, check=False)
    assert r.returncode != 0 and "no such user" in r.stderr


@pytest.mark.feature("os")
def test_accounts_undo_restores(tmp_path):
    (tmp_path / "etc/sudoers.d").mkdir(parents=True)
    (tmp_path / "etc/sudoers.d/kotl").write_text("# someone else's file\n")
    dry("accounts.sh", "install", "--admin", me(), root=tmp_path)
    assert (tmp_path / "etc/sudoers.d/kotl.kotl-orig").exists()
    dry("accounts.sh", "--undo", root=tmp_path)
    assert (tmp_path / "etc/sudoers.d/kotl").read_text() == "# someone else's file\n"
    assert not (tmp_path / "etc/kotl/kotl.conf").exists()


# ---- slurm/install.sh (queue, starter, runner, acct)

@pytest.fixture
def slurm(tmp_path):
    r = dry("slurm/install.sh", root=tmp_path)
    return tmp_path, r.stdout, (tmp_path / "etc/slurm/slurm.conf").read_text()


@pytest.mark.feature("queue")
def test_slurm_conf_queue(slurm):
    _, _, conf = slurm
    host = subprocess.run(["hostname", "-s"], capture_output=True, text=True).stdout.strip()
    assert f"SlurmctldHost={host}" in conf
    assert f"NodeName={host} CPUs={os.cpu_count()} " in conf
    assert "Licenses=vcu118:1" in conf
    assert "PriorityType=priority/multifactor" in conf
    assert "@" not in conf.replace("# managed", "")


@pytest.mark.feature("queue")
def test_slurm_qos_and_users(slurm):
    _, out, _ = slurm
    assert "sacctmgr -i add qos urgent" in out and "sacctmgr -i add qos maint" in out
    assert "sacctmgr -i add account kotl cluster=kotl" in out


@pytest.mark.feature("starter")
def test_slurm_conf_never_kills_on_eta(slurm):
    root, _, conf = slurm
    assert "OverTimeLimit=UNLIMITED" in conf and "KillWait=120" in conf
    assert "Epilog=/opt/kotl/epilog.sh" in conf
    epilog = root / "opt/kotl/epilog.sh"
    assert os.access(epilog, os.X_OK)
    assert subprocess.run([str(epilog)]).returncode == 0  # must never drain the node


@pytest.mark.feature("runner")
def test_slurm_conf_health_check(slurm):
    root, _, conf = slurm
    assert "HealthCheckProgram=/opt/kotl/health.sh" in conf and "HealthCheckInterval=300" in conf
    assert subprocess.run([str(root / "opt/kotl/health.sh")]).returncode == 0


@pytest.mark.feature("acct")
def test_slurmdbd_conf_private(slurm):
    root, out, conf = slurm
    assert "AccountingStorageType=accounting_storage/slurmdbd" in conf
    assert "AccountingStorageEnforce=associations,limits,qos" in conf
    dbd = root / "etc/slurm/slurmdbd.conf"
    assert oct(dbd.stat().st_mode & 0o777) == "0o600"
    pw = [l.split("=", 1)[1] for l in dbd.read_text().splitlines() if l.startswith("StoragePass=")][0]
    assert len(pw) >= 32 and "@" not in pw
    assert "CREATE DATABASE IF NOT EXISTS slurm_acct_db" in out


@pytest.mark.feature("acct")
def test_slurm_rerun_keeps_db_password(tmp_path):
    dry("slurm/install.sh", root=tmp_path)
    first = (tmp_path / "etc/slurm/slurmdbd.conf").read_text()
    dry("slurm/install.sh", root=tmp_path)
    assert (tmp_path / "etc/slurm/slurmdbd.conf").read_text() == first


@pytest.mark.feature("queue")
def test_slurm_undo(tmp_path):
    dry("slurm/install.sh", root=tmp_path)
    r = dry("slurm/install.sh", "--undo", root=tmp_path)
    assert not (tmp_path / "etc/slurm/slurm.conf").exists()
    assert "systemctl disable --now slurmctld slurmd slurmdbd" in r.stdout
    assert "apt-get purge" not in r.stdout  # only with --purge


# ---- ssh/setup-kotl-key.sh (key)

@pytest.mark.feature("key")
def test_kotl_ssh_config(tmp_path):
    r = dry("ssh/setup-kotl-key.sh", "--pc", "vcu118-pc1=192.168.1.2", root=tmp_path)
    cfg = tmp_path / "home/kotl/.ssh/config"
    text = cfg.read_text()
    assert "Host vcu118-pc1\n  HostName 192.168.1.2\n  User kotl" in text
    assert "BatchMode yes" in text and "IdentitiesOnly yes" in text
    assert oct(cfg.stat().st_mode & 0o777) == "0o600"
    assert "ssh-keygen -q -t ed25519 -N" in r.stdout


@pytest.mark.feature("key")
def test_kotl_ssh_needs_pc(tmp_path):
    r = dry("ssh/setup-kotl-key.sh", root=tmp_path, check=False)
    assert r.returncode != 0 and "--pc" in r.stderr
    r = dry("ssh/setup-kotl-key.sh", "--pc", "noequals", root=tmp_path, check=False)
    assert r.returncode != 0


# ---- pc/setup.sh (pc1)

KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAItest kotl@test"


@pytest.mark.feature("pc1")
def test_pc_setup_soft_lockdown(tmp_path):
    r = dry("pc/setup.sh", "--key", KEY, root=tmp_path)
    assert "useradd --create-home --shell /bin/bash" in r.stdout or "passwd -l kotl" in r.stdout
    assert "passwd -l kotl" in r.stdout
    assert KEY in r.stdout
    # soft lockdown: never edits sshd's config or anyone's password
    text = (DEPLOY / "pc/setup.sh").read_text()
    for word in ("sshd_config", "PasswordAuthentication", "chpasswd", "usermod"):
        assert word not in text


@pytest.mark.feature("pc1")
def test_pc_setup_rejects_bad_key(tmp_path):
    r = dry("pc/setup.sh", "--key", "not a key", root=tmp_path, check=False)
    assert r.returncode != 0 and "public key" in r.stderr


@pytest.mark.feature("fsmod")
def test_firesim_check_is_read_only():
    text = (DEPLOY / "adapters/firesim/check.sh").read_text()
    body = text.split('check "kotl login"')[1]
    for word in ("rm ", "sed -i", "install ", "chmod", "tee ", "useradd", "systemctl"):
        assert word not in body


# ---- kotl/install.sh (launcher)

@pytest.mark.feature("launcher")
def test_kotl_install_dry_run(tmp_path):
    r = dry("kotl/install.sh", "--board", "vcu118-pc1=vcu118@vcu118-pc1", root=tmp_path)
    assert (tmp_path / "opt/kotl/lib/kotl/core/launcher.py").exists()
    assert not list((tmp_path / "opt/kotl/lib").rglob("__pycache__"))
    launch = (tmp_path / "opt/kotl/launch").read_text()
    assert launch.startswith("#!/usr/bin/python3 -I") and "kotl.core.launcher" in launch
    assert "kotl.cli.main" in (tmp_path / "opt/kotl/bin/kotl").read_text()
    assert (tmp_path / "opt/kotl/job.sh").read_text() == (DEPLOY / "job.sh").read_text()
    assert "adminlevel=Admin" in r.stdout
    assert "systemctl enable --now kotl-notifier.timer" in r.stdout
    svc = (tmp_path / "etc/systemd/system/kotl-notifier.service").read_text()
    assert "User=kotl" in svc and "ExecStart=/opt/kotl/launch notify" in svc
    assert "OnUnitActiveSec=1min" in (tmp_path / "etc/systemd/system/kotl-notifier.timer").read_text()
    assert "board-add vcu118-pc1 vcu118 vcu118-pc1" in r.stdout
    assert not (tmp_path / "opt/kotl/bin/firesim").exists()          # generic: no firesim wrapper
    assert not (tmp_path / "etc/profile.d/kotl.sh").exists()           # and no PATH tricks
    client = (tmp_path / "etc/ssh/ssh_config.d/kotl.conf").read_text()
    assert "Host vcu118-pc1\n" in client and "IdentityFile /tmp/kotl-keys-%u/%n" in client


@pytest.mark.feature("launcher")
def test_kotl_install_bad_board(tmp_path):
    r = dry("kotl/install.sh", "--board", "vcu118-pc1", root=tmp_path, check=False)
    assert r.returncode != 0 and "NAME=TYPE@HOST" in r.stderr


@pytest.mark.feature("launcher")
def test_kotl_undo_leaves_noop_epilog(tmp_path):
    dry("kotl/install.sh", root=tmp_path)
    dry("kotl/install.sh", "--undo", root=tmp_path)
    ep = tmp_path / "opt/kotl/epilog.sh"
    assert ep.exists() and subprocess.run(["sh", str(ep)]).returncode == 0
    assert not (tmp_path / "opt/kotl/launch").exists()


@pytest.mark.feature("launcher")
def test_install_cleans_up_the_old_wrapper(tmp_path):
    for f in ("opt/kotl/bin/firesim", "etc/profile.d/kotl.sh"):
        (tmp_path / f).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / f).write_text("# managed by kotl\n")
    dry("kotl/install.sh", root=tmp_path)
    assert not (tmp_path / "opt/kotl/bin/firesim").exists() and not (tmp_path / "etc/profile.d/kotl.sh").exists()


@pytest.mark.feature("access")
def test_pc_setup_installs_keys_helper(tmp_path):
    r = dry("pc/setup.sh", "--keys-helper", str(DEPLOY / "pc/kotl-keys"), "--account", "root", root=tmp_path)
    assert "install -m 755 -o root -g root" in r.stdout and "/usr/local/bin/kotl-keys" in r.stdout
    assert "kotl ALL=(root) NOPASSWD: /usr/local/bin/kotl-keys" in r.stdout
    r = dry("pc/setup.sh", "--keys-helper", str(DEPLOY / "accounts.sh"), root=tmp_path, check=False)
    assert r.returncode != 0


@pytest.mark.feature("fsmod")
def test_firesim_pc_setup_installs_driver_helper_with_no_arguments(tmp_path):
    r = dry("adapters/firesim/pc-setup.sh", root=tmp_path)
    assert "/usr/local/bin/kotl-xdma-reload" in r.stdout
    assert 'kotl ALL=(root) NOPASSWD: /usr/local/bin/kotl-xdma-reload ""' in r.stdout   # "" = no arguments allowed
    r = dry("adapters/firesim/pc-setup.sh", "--undo", root=tmp_path)
    assert "rm -f /usr/local/bin/kotl-xdma-reload /etc/sudoers.d/kotl-driver" in r.stdout


@pytest.mark.feature("pc1")
def test_generic_pc_setup_knows_no_tool():
    text = (DEPLOY / "pc/setup.sh").read_text()
    assert "--driver-helper" not in text and "xdma" not in text.lower().replace("kotl-xdma-reload", "")


@pytest.mark.feature("notifier")
def test_notifier_units_removed_on_undo(tmp_path):
    dry("kotl/install.sh", root=tmp_path)
    r = dry("kotl/install.sh", "--undo", root=tmp_path)
    assert "systemctl disable --now kotl-notifier.timer" in r.stdout
    assert not (tmp_path / "etc/systemd/system/kotl-notifier.timer").exists()


@pytest.mark.feature("starter")
@pytest.mark.parametrize("script", ["epilog.sh", "health.sh"])
def test_slurm_hooks_work_without_path(script, tmp_path):
    # Slurm starts Prolog/Epilog/HealthCheckProgram with no PATH: the scripts must set their own
    fake = tmp_path / "opt"
    text = (DEPLOY / script).read_text()
    assert "PATH=/usr/sbin:/usr/bin:/sbin:/bin" in text
    assert text.index("PATH=") < text.index("runuser")
    r = subprocess.run(["/bin/sh", str(DEPLOY / script)], env={}, capture_output=True)
    assert r.returncode == 0


@pytest.mark.feature("plugin")
def test_install_publishes_the_plugin(tmp_path):
    dry("kotl/install.sh", root=tmp_path)
    assert (tmp_path / "opt/kotl/plugin/skills/kotl/SKILL.md").exists()
    assert os.access(tmp_path / "opt/kotl/plugin/hooks/pre-bash.sh", os.X_OK)
    mk = json.loads((tmp_path / "opt/kotl/.claude-plugin/marketplace.json").read_text())
    assert mk["plugins"][0]["source"] == "./plugin"
    assert (tmp_path / "opt/kotl/plugin-band/hooks/register.tsx").exists()
    assert not list((tmp_path / "opt/kotl/plugin-band").rglob("*.test.tsx"))
    assert (tmp_path / "opt/kotl/kotl-status.vsix").stat().st_size > 1000
    dry("kotl/install.sh", "--undo", root=tmp_path)
    assert not (tmp_path / "opt/kotl/plugin").exists()


@pytest.mark.feature("fsmod")
def test_xdma_reload_loads_it_the_way_firesim_does():
    text = (DEPLOY / "adapters/firesim/kotl-xdma-reload").read_text()
    assert 'insmod "$KO" poll_mode=1' in text and "modprobe xdma poll_mode=1" in text
    assert "/lib/modules/$(uname -r)/extra/xdma.ko" in text
    assert "modprobe xdma\n" not in text                     # never a plain modprobe (no poll_mode)


@pytest.mark.feature("daemon")
def test_install_runs_the_kotl_daemon(tmp_path):
    r = dry("kotl/install.sh", root=tmp_path)
    unit = (tmp_path / "etc/systemd/system/kotl-daemon.service").read_text()
    assert "User=kotl" in unit and "ExecStart=/opt/kotl/launch daemon" in unit
    assert "Restart=always" in unit and "RuntimeDirectory=kotl" in unit and "RuntimeDirectoryMode=0755" in unit
    assert "systemctl restart kotl-daemon.service" in r.stdout          # runs the code just installed
    r = dry("kotl/install.sh", "--undo", root=tmp_path)
    assert "systemctl disable --now kotl-daemon.service" in r.stdout
    assert not (tmp_path / "etc/systemd/system/kotl-daemon.service").exists()


@pytest.mark.feature("setup")
def test_install_publishes_the_client_installer_and_replaces_json(tmp_path):
    (tmp_path / "opt/kotl/.claude-plugin").mkdir(parents=True)
    (tmp_path / "opt/kotl/.claude-plugin/marketplace.json").write_text('{"old": true}')
    dry("kotl/install.sh", root=tmp_path)
    assert os.access(tmp_path / "opt/kotl/client/install.sh", os.X_OK)
    assert not (tmp_path / "opt/kotl/.claude-plugin/marketplace.json.kotl-orig").exists()
    assert '"kotl-band"' in (tmp_path / "opt/kotl/.claude-plugin/marketplace.json").read_text()
