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
