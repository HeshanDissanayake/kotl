---
name: kotl-firesim
description: Run FireSim on the lab's FPGA boards (VCU118) through Kotl, from a Chipyard on the workstation or on the person's own PC (a run package). Use whenever a task runs FireSim (infrasetup, runworkload, a bitstream or driver from a Chipyard/FireSim build) on a board, packs a FireSim build to run it there, checks whether a build will work on the lab's boards, or asks what FireSim setup worked before. Read the kotl skill too, for the queue itself.
---

# FireSim on the lab's boards, through Kotl

Kotl's FireSim adapter keeps the boards ready for FireSim (XDMA loaded, glibc checked), stops a
run's FireSim when its job ends, and writes every FireSim run into the lab notes. The queue
itself (`kotl run`, `kotl lease`, ETAs, results) is in the **kotl** skill.

## 1. Read the lab notes first

```sh
kotl notes firesim            # setup.md, compatible.md, the latest runs, notes.md
```

Before any run, compare what the person is about to run with the notes:

- their FireSim and Chipyard commits (`git -C <chipyard> rev-parse --short=10 HEAD`, and in
  `sims/firesim`), the hardware config (`default_hw_config` in their `config_runtime.yaml`), its
  bitstream (`bitstream_tar` in `config_hwdb.yaml`), and the workload;
- against the `ok` lines in `runs.md` and the combinations in `compatible.md`.

If nothing like it has worked on these boards (another FireSim version, another shell or board
config, a bitstream built for something else), say so and what last worked, before using the
queue. If `setup.md` lists something the PC needs and the person's build expects something else
(e.g. another XDMA or Vivado version), stop and ask.

## 2. Run it

Two ways. Which one depends on where the person's Chipyard is:

| Their Chipyard is | Use |
| --- | --- |
| on their own PC (Kotl's client bundle, `KOTL_SSH` set) | **a run package** (2a): build there, pack, copy, run |
| on the workstation | **FireSim itself** (2b), or a run package too |

### 2a. A run package: build anywhere, run through Kotl (no FireSim on the workstation)

The FPGA PCs are reachable only from the workstation, so FireSim's manager can't drive a board
from the person's own PC. Instead, pack what FireSim would copy to the board's PC and let Kotl's
runner do the rest. Requirements: one simulation, no network (`topology: no_net_config`,
`no_net_num_nodes: 1`), a `xilinx_vcu118` bitstream, a workload that ends by itself.

1. Build on their PC, in their FireSim environment: the bitstream (or one they already have, in
   `config_hwdb.yaml` as a local `bitstream_tar`), `firesim builddriver -c CFG`, and the
   FireMarshal workload (`marshal build` + `marshal install`).
2. Pack it, in `sims/firesim/deploy` (on their own PC the tool is
   `~/.kotl-client/adapters/firesim/kotl-firesim-pack`; on the workstation
   `/opt/kotl/adapters/firesim/kotl-firesim-pack`):

   ```sh
   kotl-firesim-pack -c CFG --out ~/kotl-runs/NAME [--timeout 30m] [--pass REGEX]
   ```

   It reads, never changes, their FireSim. It tells you what it packed (hardware config,
   workload, driver, the glibc the driver needs) and the next two commands. If it refuses, it
   says why (no driver built, a network topology, a bitstream that isn't local, ...): fix that,
   don't work around it.
3. Copy it and run it (the eta covers copy-to-PC, flash and the simulation):

   ```sh
   rsync -a --partial ~/kotl-runs/NAME/ "$KOTL_SSH":kotl-runs/NAME/
   ssh "$KOTL_SSH" kotl run --eta 20m -- /opt/kotl/adapters/firesim/run-package.sh kotl-runs/NAME
   ```

   The runner checks the PC (and that the PC's glibc is new enough for the driver), flashes the
   bitstream, runs the driver in screen `fsim0` (`kotl attach` shows it), copies back the
   uartlog and what the run wrote, and prints `KOTL RESULT: PASS` only on a pass line
   (`*** PASSED ***` or `reboot: Power down`, or `--pass REGEX` from the pack). It prints the
   package's `KOTL FACT` lines, so the run's line in the notes says what it used.
4. Results: `ssh "$KOTL_SSH" kotl fetch JOB` (into `kotl-results/JOB/` in their workstation
   home; the uartlog and what the run wrote are in `outputs/`), then
   `rsync -a "$KOTL_SSH":kotl-results/JOB/ kotl-results/JOB/` to bring them to their PC.
5. Remove the package on the workstation when done (`ssh "$KOTL_SSH" rm -rf kotl-runs/NAME`):
   root filesystems are large.

### 2b. FireSim itself, from a Chipyard on the workstation

Run FireSim from the person's own Chipyard, with their environment active (`source env.sh` and
`sourceme-manager.sh --skip-ssh-setup` in the same shell), from `sims/firesim/deploy`:

```sh
kotl run --eta 30m -- sh -c "firesim infrasetup -c CFG && firesim runworkload -c CFG"
```

- The workload must power off by itself (FireMarshal `run`/`command`, or a script ending in
  `poweroff`); otherwise `runworkload` waits until `--max` stops the job.
- `runworkload` reports "completed" even when the driver failed to start: check the uartlog in
  `results-workload/<newest>/*/uartlog` and print `KOTL RESULT: PASS` only if it shows the real
  end (e.g. `reboot: Power down`). `/opt/kotl/adapters/firesim/firesim-smoke.sh CFG` does this.
- If `kotl board list` warns that glibc differs between the workstation and the PC, FireSim's
  bundled glibc must be removed on the PC after infrasetup: use
  `/opt/kotl/adapters/firesim/firesim-smoke.sh --use-pc-glibc CFG`, or
  `ssh "$KOTL_PC" "cd <sim dir>/sim_slot_0 && rm -f libc.so.6 libm.so.6 libpthread.so.0 libdl.so.2 librt.so.1"`
  between the two commands.
- By hand, in a lease: `kotl lease --eta 1h`, then the same FireSim commands (`ssh-add
  /tmp/kotl-keys-$USER/<board>` first, so FireSim's ssh uses the job key); `kotl attach` shows
  the console (screen `fsim0`); `kotl release` when done.

## 3. Afterwards: the notes

- Kotl adds the run to `runs.md` by itself when a `kotl run` ends: `ok`/`FAIL`, who, the board,
  how long, and what it used (FireSim and Chipyard commits, `hw_config`, `bitstream`, `workload`),
  read from the person's FireSim as the run ends. `+changes` after a commit means uncommitted
  changes.
- A script can describe its run itself with `KOTL FACT: key=value` lines (e.g.
  `KOTL FACT: bitstream=...`); then only those are used.
- Add what the next person needs: `kotl notes add firesim "what worked, what didn't, the fix"`.
  A run done in a lease gets no automatic line: add one.
- When a run proves a new combination works (or doesn't), tell the person, and with their OK
  update `compatible.md`: `kotl notes firesim compatible.md > /tmp/c.md`, edit,
  `kotl notes set firesim compatible.md < /tmp/c.md` (the old one is kept).

## A quick check that a board works

The lab may have a FireSim test package (a known-good bitstream and driver that boots Linux and
powers off, no Chipyard needed); `setup.md` says where. Run it with
`kotl run --eta 15m -- <package>/run.sh`. It prints `KOTL RESULT: PASS` only when Linux powered
off, and describes itself in the notes.

## Don'ts

- Don't run `firesim infrasetup`/`runworkload`/`kill` outside `kotl run` or a lease.
- Don't stop a FireSim `fsim*` screen or `FireSim-*` driver that isn't your job's: report who runs
  it, for how long, and that it is outside Kotl (the kotl skill says more).
- Don't write guesses into the notes: only what a run showed.
