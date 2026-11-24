"""kotl setup: give the person running it everything they use Kotl with, on the workstation.

  kotl setup            the Claude Code plugins (kotl, kotl-band) and the VS Code extension
  kotl setup --undo     remove them again
  kotl client-bundle    (see client.py) the same for a user's own PC, as a tar on stdout

Per user and safe to re-run: what is already there is left as it is (the VS Code extension is
re-installed, so a re-run after an update brings the new version). Nothing here needs sudo.
"""
import glob
import grp
import os
import pwd
import shutil
import subprocess

OPT = "/opt/kotl"
VSIX = f"{OPT}/kotl-status.vsix"
PLUGINS = ("kotl@kotl", "kotl-band@kotl")
EXTENSION = "kotl.kotl-status"


def run(argv, timeout=180):
    try:
        r = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
        return r.returncode, (r.stdout + r.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, str(e)


def vscode_servers(home=None):
    """This user's VS Code server command-line tools, newest first (one per VS Code version)."""
    home = home or os.path.expanduser("~")
    found = glob.glob(f"{home}/.vscode-server/cli/servers/Stable-*/server/bin/code-server") + \
        glob.glob(f"{home}/.vscode-server/bin/*/bin/code-server")
    return sorted(found, key=os.path.getmtime, reverse=True)


def in_kotl_users():
    """Does THIS process have the group (a shell started before it was added doesn't)?"""
    try:
        gid = grp.getgrnam("kotl-users").gr_gid
    except KeyError:
        return False
    return gid in os.getgroups()


def member_of_kotl_users(user):
    try:
        return user in grp.getgrnam("kotl-users").gr_mem
    except KeyError:
        return False


def setup(undo=False, out=print, opt=OPT):
    """Returns 0 when everything it could do worked, 1 otherwise."""
    user = pwd.getpwuid(os.getuid()).pw_name
    ok = True
    claude = shutil.which("claude")
    servers = vscode_servers()
    vsix = f"{opt}/kotl-status.vsix"

    if not undo:
        if not member_of_kotl_users(user):
            out(f"! {user} is not in kotl-users: ask the admin (sudo deploy/accounts.sh add-user {user})")
            ok = False
        elif not in_kotl_users():
            out("! this terminal started before you joined kotl-users: log in again (or restart tmux / the VS Code server)")

    # Claude Code: the marketplace at /opt/kotl and the two plugins
    if not claude:
        out("- Claude Code: not installed here; skipped (install it, then run kotl setup again)")
    elif undo:
        for p in PLUGINS:
            rc, text = run([claude, "plugin", "uninstall", p])
            out(f"- Claude Code: {p} {'removed' if rc == 0 else 'not removed: ' + text.splitlines()[-1] if text else 'not removed'}")
        rc, _ = run([claude, "plugin", "marketplace", "remove", "kotl"])
        out(f"- Claude Code: marketplace kotl {'removed' if rc == 0 else 'was not added'}")
    else:
        rc, text = run([claude, "plugin", "marketplace", "list"])
        if "kotl" not in text:
            rc, text = run([claude, "plugin", "marketplace", "add", opt])
            out(f"- Claude Code: marketplace {opt} {'added' if rc == 0 else 'NOT added: ' + text[-200:]}")
            ok &= rc == 0
        else:
            out("- Claude Code: marketplace kotl already added")
        for p in PLUGINS:
            rc, text = run([claude, "plugin", "install", p])
            already = "already" in text.lower()
            out(f"- Claude Code: {p} {'installed' if rc == 0 and not already else 'already installed' if already else 'NOT installed: ' + text[-200:]}")
            ok &= rc == 0 or already
        out("  (start a new Claude Code session to load them; /reload-plugins in an open one)")

    # VS Code: the extension, into this user's VS Code server on this machine
    if not servers:
        out("- VS Code: no VS Code server for you on this machine yet: connect VS Code to it once "
            "(Remote-SSH), then run kotl setup again")
    elif undo:
        rc, _ = run([servers[0], "--uninstall-extension", EXTENSION])
        out(f"- VS Code: extension {EXTENSION} {'removed' if rc == 0 else 'was not installed'}")
    elif not os.path.exists(vsix):
        out(f"! VS Code: {vsix} is missing: ask the admin to run deploy/kotl/install.sh")
        ok = False
    else:
        rc, text = run([servers[0], "--install-extension", vsix, "--force"])
        out(f"- VS Code: extension {'installed' if rc == 0 else 'NOT installed: ' + text[-200:]}"
            + (" (reload the VS Code window: Developer: Reload Window)" if rc == 0 else ""))
        ok &= rc == 0

    if not undo and ok:
        out("Done. Try: kotl status · kotl top · kotl run --eta 5m -- hostname")
    return 0 if ok else 1
