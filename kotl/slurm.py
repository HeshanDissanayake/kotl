"""The ONLY place Kotl runs Slurm commands (sbatch, scancel, squeue, scontrol, sacct)."""
import subprocess


class SlurmError(RuntimeError):
    pass


def _run(args, check=True):
    r = subprocess.run(args, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SlurmError(f"{args[0]} failed: {(r.stderr or r.stdout).strip()}")
    return r


def submit(script, args, *, license, minutes, name, chdir, env=None):
    """sbatch the script; returns the job id (int)."""
    exports = "ALL" + "".join(f",{k}={v}" for k, v in (env or {}).items())
    cmd = ["sbatch", "--parsable", "-J", name, "-L", license, f"--time={minutes}",
           f"--chdir={chdir}", "--output=/dev/null", f"--export={exports}", script, *args]
    return int(_run(cmd).stdout.strip().split(";")[0])


def cancel(job_id, signal=None):
    cmd = ["scancel"] + ([f"--signal={signal}"] if signal else []) + [str(job_id)]
    return _run(cmd, check=False).returncode == 0


def job_info(job_id):
    """scontrol's view of one job as a dict (UserId -> user name only), or None if Slurm forgot it."""
    r = _run(["scontrol", "show", "job", "-o", str(job_id)], check=False)
    if r.returncode != 0 or not r.stdout.strip():
        return None
    info = {}
    for tok in r.stdout.split():
        if "=" in tok:
            k, v = tok.split("=", 1)
            info[k] = v
    if "UserId" in info:
        info["User"] = info["UserId"].split("(")[0]
    return info


def state(job_id):
    """RUNNING, PENDING, ... or '' once the job has left the queue."""
    r = _run(["squeue", "-h", "-j", str(job_id), "-o", "%T"], check=False)
    return r.stdout.strip() if r.returncode == 0 else ""


def queue():
    """Every job in the queue: list of dicts."""
    fmt = "%i|%u|%j|%T|%l|%M|%S|%r"
    r = _run(["squeue", "-h", "-o", fmt])
    keys = ["job", "user", "name", "state", "eta", "used", "start", "reason"]
    return [dict(zip(keys, line.split("|"))) for line in r.stdout.splitlines() if line]


def run_in_job(job_id, argv, env=None):
    """Run argv as a step of a running job (srun --overlap), so cancel and the end step reach it.
    Returns its exit code; output goes straight to the caller's terminal."""
    return subprocess.run(["srun", f"--jobid={job_id}", "--overlap", "--quiet", "--ntasks=1", *argv],
                          env=env).returncode


def hold_license(name, license):
    """Hold a license with a reservation nobody can use, so queued jobs wait (a board is down)."""
    r = _run(["scontrol", "create", "reservation", f"ReservationName={name}", "StartTime=now",
              "Duration=infinite", "Users=root", f"Licenses={license}", "Flags=ANY_NODES"], check=False)
    return r.returncode == 0 or "already exists" in (r.stderr + r.stdout)


def release_hold(name):
    r = _run(["scontrol", "delete", f"ReservationName={name}"], check=False)
    return r.returncode == 0 or "not found" in (r.stderr + r.stdout).lower()


def holds():
    """Names of current reservations."""
    r = _run(["scontrol", "show", "reservation", "-o"], check=False)
    return [tok.split("=", 1)[1] for line in r.stdout.splitlines() for tok in line.split()
            if tok.startswith("ReservationName=")]


def pending_starts():
    """{job: (user, estimated start as epoch or None)} for pending Kotl jobs."""
    import time as _t
    r = _run(["squeue", "-h", "-t", "PENDING", "-o", "%i|%u|%j|%S"], check=False)
    out = {}
    for line in r.stdout.splitlines():
        job, user, name, start = (line.split("|") + ["", "", "", ""])[:4]
        if not name.startswith("kotl-"):
            continue
        try:
            when = _t.mktime(_t.strptime(start, "%Y-%m-%dT%H:%M:%S"))
        except ValueError:
            when = None
        out[int(job)] = (user, when)
    return out


def running_times():
    """{job: (user, seconds used, time limit seconds or None)} for running Kotl jobs."""
    r = _run(["squeue", "-h", "-t", "RUNNING", "-o", "%i|%u|%j|%M|%l"], check=False)
    out = {}
    for line in r.stdout.splitlines():
        job, user, name, used, limit = (line.split("|") + [""] * 5)[:5]
        if name.startswith("kotl-"):
            out[int(job)] = (user, _secs(used), _secs(limit))
    return out


def _secs(text):
    if not text or text in ("UNLIMITED", "INVALID", "NOT_SET"):
        return None
    days = 0
    if "-" in text:
        d, text = text.split("-", 1)
        days = int(d)
    parts = [int(x) for x in text.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts
    return ((days * 24 + h) * 60 + m) * 60 + s
