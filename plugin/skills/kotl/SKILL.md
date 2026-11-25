---
name: kotl
description: Use the lab's FPGA boards (VCU118) through Kotl, the lab's board queue. Use whenever a task runs anything on an FPGA board or its PC (FireSim infrasetup/runworkload, a bitstream, a driver test, ssh to an FPGA PC), or when the person asks about the board queue, their Kotl jobs, results, logs, notices or the lab notes (what worked before). For FireSim also read the kotl-firesim skill.
---

# Kotl: the lab's FPGA board queue

The FPGA boards are shared. Kotl queues every use of a board through Slurm, gives the job SSH
access to the board's PC only while it runs, and frees the board the moment the job ends.
**Never use a board outside Kotl** (no plain `firesim infrasetup`/`runworkload`, no direct ssh to
an FPGA PC without a lease): it can break someone else's run.

## Where to run `kotl`

- On the workstation (`command -v kotl` finds it): run `kotl ...` directly.
- On a user's own PC: run it over ssh, `ssh "$KOTL_SSH" 'cd <folder> && kotl ...'`.
  `KOTL_SSH` is the workstation's ssh name (set in `~/.claude/settings.json` under `env`). If it
  is unset, ask the person for it. Files and folders must exist on the workstation.

## Every job needs an ETA and an exit plan

- `--eta` is required: your honest estimate. It only orders the queue; it never kills the job.
- `--max` (default 2x ETA) stops a hung job. Set it when a run might legitimately take longer.
- The job must end by itself: a command that exits, or a lease that is released.

## Run a command on a board: `kotl run` (preferred)

The board is held while the command runs and freed the moment it exits.

```sh
kotl run --eta 30m -- <command>
```

- Inside the job, the command has `KOTL_JOB`, `KOTL_BOARD`, `KOTL_PC` (user@address of the board's
  PC) and an ssh-agent holding only the job key: `ssh "$KOTL_PC" ...` works, FireSim's own ssh too.
- Exit code 0 = `succeeded`. A line `KOTL RESULT: PASS` or `KOTL RESULT: FAIL` in the output sets
  `passed`/`failed` instead. Print one when the exit code alone can't tell (the tool's skill says
  how).
- `kotl run` waits and streams the output. For a long run, add `--no-wait` (it prints the job
  number), then follow with `kotl logs JOB -f` or check `kotl status`. Run long waits in the
  background rather than blocking the conversation.

## Tools on the boards: each has its own skill, and lab notes

Kotl itself is generic: it queues the board and gives the job access. What one tool needs lives
in that tool's adapter, and each adapter brings a skill. Before running a tool on a board, read its
skill (it is installed next to this one) and its lab notes.

| Tool | Skill | Lab notes |
| --- | --- | --- |
| FireSim | `kotl-firesim` | `kotl notes firesim` |
| anything else (a driver test, `ls` on the PC) | this skill | `kotl notes general` |

## Lab notes: what the lab knows, kept by Kotl

`/srv/kotl/notes/` on the workstation holds what worked before, per tool. The paths never change:

```sh
kotl notes                      # the index: every tool's pages, and its last good run
kotl notes firesim              # setup.md, compatible.md, the latest runs, notes.md
kotl notes firesim runs.md      # one page, whole
kotl notes add firesim "text"   # a dated, signed note: what you learned, what to avoid
```

- **Read them before a run**: `setup.md` (what the board's PC has), `compatible.md` (what works
  together), `runs.md` (every run Kotl saw, `ok`/`FAIL`, with what it used), `notes.md` (free
  notes). Compare what the person is about to run with the last good runs, and say so if it
  differs (another commit, config or bitstream) before using the queue.
- **Kotl adds the run line itself** when a `kotl run` of a tool ends. A command can describe
  itself with `KOTL FACT: key=value` lines in its output (they replace what the adapter finds).
- **Add a note** when you learn something the next person needs: a fix, a known-bad combination,
  a step that was missing. One or two lines, facts only. Runs done in a lease get no automatic
  line: add one.
- `kotl notes set TOOL setup.md|compatible.md < file` replaces a curated page (the old one is kept;
  `kotl notes history TOOL`). Change these only with facts from runs, and tell the person.
- Lab facts in the notes come from the lab; don't invent them.

## Work by hand: `kotl lease`

```sh
kotl lease --eta 1h        # waits for a board, then prints how to reach it
ssh <board>                # e.g. ssh vcu118-pc1: uses the lease's job key
kotl attach                # FireSim's console (Ctrl-a d detaches)
kotl release               # ALWAYS release when done
```

A lease ends on `kotl release`, after 30 minutes with nothing of yours running on the PC, or at
`--max`. If you start a lease for the person, release it when the work is done.

## Check, follow, fetch

| Need | Command |
| --- | --- |
| queue, boards, unread notices | `kotl status` (live view for a person: `kotl top`) |
| your past jobs and results | `kotl history` |
| output of a job | `kotl logs JOB` (`-f` follows a running one) |
| everything a job left | `kotl fetch JOB` -> `kotl-results/JOB/` with `status.json`, `output.log`, `launcher.log`, `outputs/` |
| cancel your job | `kotl cancel JOB` |
| notices (ETA passed, start slipped, board down/up) | `kotl notices` (marks them read) |

After a job ends: fetch it, read `status.json` first (`result`, `rc`, `reason`), then
`output.log`, then `launcher.log` (what Kotl did: key added/removed, guards, end). Report the
result, how long it took against the ETA, and anything odd.

## Results

`passed` / `failed` (KOTL RESULT line), `succeeded` / `failed` (exit code), `over_max` (the --max
guard stopped it), `idle` (a lease with nothing running), `released`, `cancelled`, `killed`
(ended by Slurm's backup), `no_access` (the board's PC couldn't be reached).

## A board that is busy, or a run that stopped

- Signs that a machine or board is Kotl's: `kotl` on the workstation's PATH, files on an FPGA PC
  that start with "managed by kotl" (`/usr/local/bin/kotl-*`, `/etc/sudoers.d/kotl*`), and
  `kotl-job-N` keys in the board account's `~/.ssh/authorized_keys`. If you see them, every use of
  that board goes through Kotl.
- A FireSim `fsim*` screen or `FireSim-*` driver on a board's PC that isn't your job's is someone
  else's work, or work outside Kotl. **Never stop it.** Tell the person who seems to run it, for
  how long, and that it is outside Kotl. `kotl board list` and `kotl status` show the same.
- Kotl itself never stops work it didn't start: a job's end step stops only what started during
  that job. If the person's run outside Kotl stopped anyway, look at `kotl status` and
  `kotl history` (a Kotl job may have taken the board), then move the run into `kotl run`.

## Don'ts

- Don't run FireSim or touch an FPGA PC outside a Kotl job or lease.
- Don't stop FireSim, screens or processes on a board's PC that aren't your own job's.
- Don't cancel other people's jobs (Kotl won't let you anyway).
- Don't leave a lease running: release it.
- Don't start a tool's run without reading its lab notes first, and don't leave what you learned
  out of them.
- Don't guess an ETA of hours for a minutes-long run: ETAs order the queue for everyone.
