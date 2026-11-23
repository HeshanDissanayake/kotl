"""Console attach: open FireSim's console (screen session fsim0) on your job's PC, with your job key.

  kotl attach [JOB]      attach (Ctrl-a d detaches; the job keeps running)

It's a shortcut for what you can do by hand during a lease: ssh with the job key, then screen.
"""
import os

from kotl import ssh

SESSION = "fsim0"


def remote_command(session=SESSION):
    # attach (sharing it if someone else, e.g. another of your terminals, is attached);
    # if there's no such session yet, list what there is
    return f"screen -x {session} || {{ echo 'kotl: no {session} console yet; screens on the PC:'; screen -ls; }}"


def argv_for(status, user, job, keydir=None, session=SESSION):
    """The ssh command for a running job's console, or a reason it can't be opened."""
    if not status or status.get("state") != "running":
        return None, f"job {job} isn't running"
    if not status.get("pc_address"):
        return None, f"job {job} has no PC access"
    key = os.path.join(keydir or f"/tmp/kotl-keys-{user}", f"job-{job}")
    if not os.path.exists(key):
        return None, f"no job key at {key}: attach from the workstation, as the job's owner"
    return ssh.attach_argv(f"{status['pc_user']}@{status['pc_address']}", key, remote_command(session)), None
