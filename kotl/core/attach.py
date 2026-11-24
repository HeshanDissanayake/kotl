"""Console attach: open a screen session on your job's PC, with your job key.

  kotl attach [JOB]      attach (Ctrl-a d detaches; the job keeps running)

Which session: the enabled adapter's console (the FireSim adapter names one), sent by the
launcher in the job's status; with none, the PC's only screen session. It's a shortcut for what you can do by hand
during a lease: ssh with the job key, then screen.
"""
import os
import re

from kotl import ssh

def remote_command(session=""):
    # attach (sharing it if someone else, e.g. another of your terminals, is attached);
    # if there's no such session yet, list what there is
    if not session:
        return "screen -x || { echo 'kotl: pick a screen session (screen -x NAME):'; screen -ls; }"
    return f"screen -x {session} || {{ echo 'kotl: no {session} console yet; screens on the PC:'; screen -ls; }}"


def argv_for(status, user, job, keydir=None, session=None):
    """The ssh command for a running job's console, or a reason it can't be opened."""
    if not status or status.get("state") != "running":
        return None, f"job {job} isn't running"
    if not status.get("pc_address"):
        return None, f"job {job} has no PC access"
    key = os.path.join(keydir or f"/tmp/kotl-keys-{user}", f"job-{job}")
    if not os.path.exists(key):
        return None, f"no job key at {key}: attach from the workstation, as the job's owner"
    if session is None:
        session = status.get("console") or ""
    if session and not re.fullmatch(r"[A-Za-z0-9_.-]+", session):
        return None, f"bad console name {session!r}"
    return ssh.attach_argv(f"{status['pc_user']}@{status['pc_address']}", key, remote_command(session)), None
