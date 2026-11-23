"""The ETA notifier: a short pass that a systemd timer runs every minute, as kotl.
It only reads Slurm and writes notices into each user's inbox; it never stops anything.

  ETA passed        the owner hears once:            "job 41 passed its ETA (30m); nothing is stopped"
  2x ETA passed     the owner and the admin, once:   "... --max will stop it at ..."
  start slipped     a queued job's start estimate moved later by 15 minutes or more
  boards            down/up notices come from the health check

Users read them with `kotl notices`, in `kotl top` and `kotl status`, and (M5) in Claude.
"""
import time

from kotl import slurm as slurm_mod

SLIP = 15 * 60      # a later start estimate of at least this much is worth telling


def fmt(seconds):
    seconds = int(seconds)
    return f"{seconds // 3600}h{seconds % 3600 // 60:02d}m" if seconds >= 3600 else f"{seconds // 60}m"


def run(registry, slurm=slurm_mod, admin="", now=time.time):
    """One pass. Returns how many notices it wrote."""
    sent = 0
    t = now()
    for job, (user, used, limit) in slurm.running_times().items():
        if not limit or used is None:
            continue
        if used > limit and registry.once(f"eta:{job}"):
            registry.notify(user, f"job {job} passed its ETA ({fmt(limit)}); nothing is stopped. "
                                  f"Your --max guard ends it if it hangs.", t)
            sent += 1
        if used > 2 * limit and registry.once(f"eta2:{job}"):
            text = f"job {job} of {user} is at {fmt(used)}, past 2x its ETA ({fmt(limit)})"
            registry.notify(user, text + ". Is it stuck? kotl logs " + str(job), t)
            if admin and admin != user:
                registry.notify(admin, text + ".", t)
            sent += 2 if admin and admin != user else 1
    for job, (user, start) in slurm.pending_starts().items():
        if start is None:
            continue
        seen = registry.remembered(f"start:{job}")
        if seen is None:
            registry.once(f"start:{job}", int(start), t)
            continue
        if start - float(seen["value"]) >= SLIP:
            registry.forget(f"start:{job}")
            registry.once(f"start:{job}", int(start), t)
            registry.notify(user, f"job {job} now expects to start at {time.strftime('%H:%M', time.localtime(start))} "
                                  f"(later than before: the job ahead runs past its ETA)", t)
            sent += 1
    return sent
