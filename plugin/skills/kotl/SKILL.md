---
name: kotl
description: Use the lab's FPGA boards (VCU118) through Kotl, the lab's board queue. Use whenever a task runs anything on an FPGA board or its PC (FireSim infrasetup/runworkload, a bitstream, a driver test, ssh to an FPGA PC), or when the person asks about the board queue, their Kotl jobs, results, logs or notices.
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
  `passed`/`failed` instead. Print one when the exit code alone can't tell (see FireSim below).
- `kotl run` waits and streams the output. For a long run, add `--no-wait` (it prints the job
  number), then follow with `kotl logs JOB -f` or check `kotl status`. Run long waits in the
  background rather than blocking the conversation.

### FireSim

Run FireSim from the person's own Chipyard, with their environment active (`source env.sh` and
`sourceme-manager.sh --skip-ssh-setup` in the same shell), from `sims/firesim/deploy`:

```sh
kotl run --eta 30m -- sh -c "firesim infrasetup -c CFG && firesim runworkload -c CFG"
```

- The workload must power off by itself (FireMarshal `run`/`command`, or a script ending in
  `poweroff`); otherwise `runworkload` waits until `--max` stops the job.
- `runworkload` reports "completed" even when the driver failed to start: check the uartlog in
  `results-workload/<newest>/*/uartlog` and print `KOTL RESULT: PASS` only if it shows the real
  end (e.g. `reboot: Power down`). The lab's `deploy/adapters/firesim/firesim-smoke.sh` does this.
- If `kotl board list` warns that glibc differs between the workstation and the PC, FireSim's
  bundled glibc must be removed on the PC after infrasetup: use
  `deploy/adapters/firesim/firesim-smoke.sh --use-pc-glibc CFG`, or
  `ssh "$KOTL_PC" "cd <sim dir>/sim_slot_0 && rm -f libc.so.6 libm.so.6 libpthread.so.0 libdl.so.2 librt.so.1"`
  between the two commands.

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
- Don't guess an ETA of hours for a minutes-long run: ETAs order the queue for everyone.
