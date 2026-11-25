"""Adapters: task-specific knowledge, kept out of Kotl's generic core.

The core (lease, launcher, health check, end step, attach) knows boards, jobs and keys, nothing
about any tool. An adapter adds what one tool needs, through these hooks, all optional:

  probe        shell lines printing key=value; added to the health check's one ssh call
  failures(p)  what in the probe answer makes a board unusable for this tool
  warnings(p)  what to show on the board without taking it out of the pool
  repair(...)  one fix to try on an IDLE board whose checks fail (never while a job holds it)
  stop_screens screen-session name prefixes the end step quits
  stop_procs   process patterns the end step stops (pkill -f, as the PC account)
  work_procs   process name prefixes that count as work for the lease idle guard
  console      the screen session `kotl attach` opens
  title        the tool's name for people, e.g. "FireSim" (lab notes headings)
  notes_seed   {page: text}: how its lab notes pages start (kotl/core/notes.py: setup.md, ...)
  is_run(cmd)  is a job with this command a run of this tool (a line in its notes' runs.md)?
  facts        shell lines run as the user, in the job's folder, when such a run ends; they print
               key=value lines for its runs.md line (versions, config, workload). KOTL_COMMAND
               holds the job's command. A command that prints 'KOTL FACT: key=value' lines itself
               is taken at its word instead
  end_commands(age)  commands the end step runs on the board's PC (as kotl, over its SSH key)
               after the job's key is removed, e.g. a root helper that stops what the board account
               can't; age is the job's age in seconds (stop only what started during the job)

Adapters are switched on in /etc/kotl/kotl.conf: `adapters = firesim` (comma-separated).
With none, Kotl still runs leases and jobs on any board, with only the generic checks.
"""
import importlib
import re
import sys

KNOWN = {"firesim": "kotl.adapters.firesim:FireSim"}
SAFE = re.compile(r"^[A-Za-z0-9_.-]+$")   # what may be passed to kotl-keys on the PC


class Adapter:
    name = ""
    probe = ""
    stop_screens = ()
    stop_procs = ()
    work_procs = ()
    console = ""
    title = ""
    notes_seed = {}
    facts = ""

    def is_run(self, command):
        return False

    def end_commands(self, age):
        return []

    def failures(self, p):
        return []

    def warnings(self, p):
        return []

    def repair(self, board, ssh, failures):
        """Try one fix for `failures` on an idle board; a note for the board, or None if not ours."""
        return None


def load(names):
    """Adapter objects for a comma-separated list of names (unknown names are reported, skipped)."""
    out = []
    for name in [n.strip() for n in (names or "").split(",") if n.strip()]:
        if name not in KNOWN:
            print(f"kotl: unknown adapter '{name}' in kotl.conf (known: {', '.join(KNOWN)})", file=sys.stderr)
            continue
        mod, cls = KNOWN[name].split(":")
        out.append(getattr(importlib.import_module(mod), cls)())
    return out


def enabled(cfg):
    return load(cfg.get("adapters"))


def _safe(values):
    return [v for v in values if SAFE.match(v)]


def stop_args(adapters, age=None):
    """kotl-keys arguments for the end step: --max-age (the job's age: stop only what started
    during the job), then --screen PREFIX / --proc PREFIX for each adapter."""
    args = ["--max-age", str(int(age))] if adapters and age is not None else []
    for a in adapters:
        for s in _safe(a.stop_screens):
            args += ["--screen", s]
        for p in _safe(a.stop_procs):
            args += ["--proc", p]
    return args


def work_args(adapters):
    """kotl-keys busy arguments: --proc PREFIX for each adapter's work processes."""
    return [x for a in adapters for p in _safe(a.work_procs) for x in ("--proc", p)]


def end_commands(adapters, age=None):
    """Every adapter's end-step commands, in order (argv lists run on the PC)."""
    return [list(c) for a in adapters for c in a.end_commands(age)]


def run_of(adapters, command, facts=None):
    """The adapter a job's run belongs to: named by a 'tool' fact, or the first whose is_run says so."""
    named = (facts or {}).get("tool")
    for a in adapters:
        if a.name == named:
            return a
    return next((a for a in adapters if a.is_run(command or "")), None)


def console(adapters):
    """The first adapter's console session, or '' (attach then picks the PC's only screen)."""
    return next((a.console for a in adapters if a.console), "")
