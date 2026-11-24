"""The Kotl daemon (kotld): Kotl's one always-running process, a systemd service run as kotl.

It runs a list of small tasks, each on its own interval, and never stops for a task's error
(the error is recorded and shown in the status file). Tasks so far:

  status   every 1 s: writes /run/kotl/status.json, readable by everyone: the boards, Kotl's
           queue, and how many unread notices each user has (counts only, never the text).
           kotl status, kotl top, the Claude band and the VS Code extension read this file
           instead of each asking Slurm and the launcher themselves.

More tasks join later (the user's plan): add a Task subclass to TASKS.
If the daemon is down, every reader falls back to asking directly (slower, same answers).
"""
import json
import os
import sys
import time

from kotl import slurm as slurm_mod
from kotl.core.config import Config
from kotl.core.registry import Registry

VERSION = 1


class Task:
    name = "task"
    every = 60.0

    def run(self, d):  # pragma: no cover - interface
        raise NotImplementedError


class StatusTask(Task):
    """The shared status file."""
    name = "status"
    every = 1.0

    def run(self, d):
        try:
            queue = [r for r in d.slurm.queue() if r["name"].startswith("kotl-")]
        except slurm_mod.SlurmError as e:
            queue, d.notes["status"] = [], f"squeue failed: {e}"
        doc = {
            "version": VERSION,
            "updated": d.clock(),
            "daemon": d.describe(),
            "boards": d.reg.boards(),
            "queue": queue,
            "unread": d.reg.unread_counts(),
        }
        write_atomic(d.cfg.status_file, json.dumps(doc))


TASKS = [StatusTask]


def write_atomic(path, text, mode=0o644):
    tmp = f"{path}.{os.getpid()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
    os.chmod(tmp, mode)
    os.replace(tmp, path)


class Daemon:
    def __init__(self, cfg=None, slurm=slurm_mod, tasks=None, clock=time.time, sleep=time.sleep):
        self.cfg = cfg or Config()
        self.slurm = slurm
        self.clock, self.sleep = clock, sleep
        self.reg = Registry(self.cfg.db)
        self.tasks = [t() for t in (tasks or TASKS)]
        self.next_at = {t.name: 0.0 for t in self.tasks}
        self.last_ok = {t.name: None for t in self.tasks}
        self.errors = {t.name: None for t in self.tasks}
        self.notes = {}
        self.started = self.clock()

    def describe(self):
        return {"pid": os.getpid(), "started": self.started,
                "tasks": {t.name: {"every": t.every, "last_ok": self.last_ok[t.name],
                                   "error": self.errors[t.name]} for t in self.tasks}}

    def step(self):
        """Run every task that is due. Returns seconds until the next one is."""
        now = self.clock()
        for t in self.tasks:
            if now >= self.next_at[t.name]:
                self.next_at[t.name] = now + t.every
                try:
                    t.run(self)
                    self.last_ok[t.name] = now
                    self.errors[t.name] = self.notes.pop(t.name, None)
                except Exception as e:  # noqa: BLE001 - one task's error never stops the daemon
                    self.errors[t.name] = f"{type(e).__name__}: {e}"
                    print(f"kotld: task {t.name}: {self.errors[t.name]}", file=sys.stderr, flush=True)
        return max(0.05, min(self.next_at.values()) - self.clock())

    def run_forever(self):
        os.makedirs(self.cfg.run_dir, exist_ok=True)
        print(f"kotld: started, tasks: {', '.join(f'{t.name} every {t.every:g}s' for t in self.tasks)}",
              file=sys.stderr, flush=True)
        while True:
            self.sleep(self.step())


def read_status(cfg=None, max_age=5.0, now=None):
    """The daemon's status file if it is fresh, else None (then ask directly)."""
    cfg = cfg or Config()
    try:
        with open(cfg.status_file, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        return None
    if (now or time.time()) - doc.get("updated", 0) > max_age:
        return None
    return doc
