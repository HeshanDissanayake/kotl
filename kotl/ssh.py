"""The ONLY place Kotl runs ssh to the FPGA PCs. Runs as kotl, with kotl's own key and config."""
import re
import shlex
import subprocess


class SSHError(RuntimeError):
    pass


def run(host, argv, timeout=60, check=True):
    """Run argv on host (quoted for the remote shell). Returns stdout."""
    remote = " ".join(shlex.quote(str(a)) for a in argv)
    try:
        r = subprocess.run(["ssh", "-o", "BatchMode=yes", host, remote],
                           capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise SSHError(f"{host}: no answer within {timeout} s") from None
    if check and r.returncode != 0:
        raise SSHError(f"{host}: {(r.stderr or r.stdout).strip() or f'exit {r.returncode}'}")
    return r.stdout


def address(host):
    """The real address behind an ssh alias (ssh -G), e.g. vcu118-pc1 -> 192.168.1.2."""
    r = subprocess.run(["ssh", "-G", host], capture_output=True, text=True)
    m = re.search(r"^hostname (\S+)$", r.stdout, re.M)
    return m.group(1) if m else host


def attach_argv(target, key, remote):
    """The ssh command a user runs (as themselves) to reach their job's PC with the job key only."""
    return ["ssh", "-t", "-o", "IdentitiesOnly=yes", "-o", "IdentityAgent=none", "-i", key, target, remote]
