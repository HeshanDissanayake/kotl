# Kotl — handoff to the building agent

Kotl manages the lab's FPGAs and servers. Version 1 queues and runs FireSim jobs on the lab's VCU118 (one board today; a second later). Later versions add board programming/reset, driver tests, power monitoring and more boards.

The full design is the architecture view in `docs/architecture/`. `index.html` only draws; everything it shows comes from `architecture.json` (the design) and `status.json` (build status). Serve that folder and open it in a browser:

```sh
cd docs/architecture && python3 -m http.server 8000   # then open http://localhost:8000
```

Click any box for its commands and config files. The tabs show what Kotl is, where it meets Slurm, three flows step by step, and build progress. **Read the view before writing code.** The config files shown in it are starting sketches, not tested configs.

---

## 1. Ground rules

1. **Ask before anything needing root or touching another machine.** Installing Slurm, editing `/etc`, creating accounts, changing anything on the FPGA PCs: write it as a script under `deploy/`, explain it, and ask the user to run it. Never run `sudo` yourself unless the user says to for that step.
2. **Never disturb other people's work.** Once the queue is live, board tests go *through Kotl/Slurm* like any other job. Never run `firesim` directly against a board that someone else might be using.
3. **Keep the status view true.** See section 6. A part is "tested" only when its tests pass, never because you believe it works.
4. **Don't guess lab facts.** Host names, user lists, FireSim version and hwdb names, and priority weights come from the user. The open questions are listed in section 8.
5. **Small steps.** One part per commit where possible, each with tests and a status update.

## 2. Architecture in one page

- **Kotl (ours, teal in the view).** The `kotl` CLI, launcher, board registry, health check, ETA notifier, job results, console attach, the kotl SSH key setup, per-job PC access (job keys), a `firesim` wrapper and job template, adapters (FireSim first) on a generic board lease, and a Claude Code plugin.
- **Slurm (off the shelf, purple).** It runs on the workstation as a single node. Kotl meets it in exactly **four** places:
  1. The CLI uses `sbatch` / `scancel` / `squeue`.
  2. Slurm's job starter runs `deploy/job.sh`, which hands over to the launcher via `sudo -u kotl`.
  3. Slurm runs `health.sh` every 5 minutes.
  4. The notifier and dashboard read `squeue` / `sacct`.
- **Other off-the-shelf parts (gray):** each user's own FireSim (in their own Chipyard), and the workstation's sudo, systemd timers and OpenSSH.
- **FPGA PCs.** Only the workstation can reach them, and only with keys: Kotl's `kotl` key, plus a job key that Kotl adds when a job starts and removes when it ends. No Kotl code runs on them besides a small key helper.
- **No always-running Kotl process.** The CLI runs per command, the launcher runs per job, and timers start the notifier.

## 3. Decisions already made (don't reopen without asking)

- **Boards:** Slurm licenses per board type: `Licenses=vcu118:2`.
- **ETA:** every job gives one (`--eta`), and it becomes Slurm's `--time`. `OverTimeLimit=UNLIMITED`, so a job is never killed for passing it. `KillWait=120` leaves time for clean stops.
- **Who can stop a job:** only the owner or root can cancel. The owner's own `--max` (default 2× ETA) and `--idle` are hang guards enforced by the launcher.
- **Priority (rough, user will tune):** multifactor with fair-share and age, plus admin-only QOS `urgent` and `maint`.
- **How a batch job ends:** the simulated Linux powers off. The workload has a run script ending in `poweroff`, or an `--expect` script drives it. `kotl firesim submit` refuses a batch job that has neither.
- **Pass or fail:** the run script prints `KOTL RESULT: PASS` or `KOTL RESULT: FAIL`. The launcher reads it from the console log, and the exit code tells Slurm succeeded or failed.
- **Clean stop:** every lease ends with the same end step: the adapter's polite `stop` (`firesim kill` for FireSim), then remove the job key, kill every process of the PC account, and only then free the board.
- **Users' own FireSim (decided 2026-11-22):** users keep their own Chipyard and FireSim; Kotl installs none. A `firesim` wrapper first on PATH queues plain FireSim commands; the user's FireSim runs as them, inside their Slurm job.
- **PC access follows the job:** a per-job SSH key is added at job start and removed by the end step (with Slurm's `Epilog` as backup), which also closes leftover sessions. No timer closes a job; idle and `--max` guards catch forgotten or hung ones.
- **Job template:** `kotl new` gives `marshal.json` (FireMarshal, `run` powers off when done), `run.sh` (prints `KOTL RESULT`) and `kotl.json` (mode, ETA, guards, hwdb). `check` refuses batch jobs that can't end by themselves.
- **Board registry:** one SQLite file at `/var/lib/kotl/kotl.db`. States: down → idle → setting_up → busy → draining → maintenance. Boards are claimed atomically.
- **Results:** `/srv/kotl/out/<user>/<job>/` holds `status.json`, `uartlog`, `launcher.log` and `outputs/`. Only the owner can read it, and it's deleted after 30 days. Remote users get it with `kotl fetch`.
- **Console attach:** `ssh -t <pc> screen -r fsim0` as kotl, after checking ownership. kotl's `.screenrc` on the PCs blocks new windows.
- **Notices:** the owner hears at ETA and the admin at 2× ETA. Queued users hear when their start estimate slips.
- **Parked:** preferring a board that already has the job's bitstream loaded. FireSim says to re-run `infrasetup` every time. Record setup time per job anyway.

## 4. Code layout and tech

Python 3.10+. Only the standard library at runtime where practical: `sqlite3`, `subprocess`, `argparse`. Tests use `pytest`.

```
kotl/
  cli/                 # the kotl command: lease/run/release, firesim wrapper, per-adapter subcommands
  core/                # board lease (launcher, access, guards, end step), registry, results, health, notifier, attach
  adapters/firesim/    # triggers / check / prepare / stop / collect
  slurm.py             # the ONLY place that runs Slurm commands
  ssh.py               # the ONLY place that runs ssh/scp/rsync to the PCs
deploy/                # setup scripts and config templates; the admin runs these
  slurm/  sudoers/  systemd/  ssh/  pc/  firesim/  job.sh  health.sh  accounts.sh
plugin/                # Claude Code plugin: skills/kotl/SKILL.md, hooks/
tools/status.py        # check + refresh (shipped; section 6)
.githooks/pre-commit   # runs tools/status.py check --staged (shipped)
tests/
  conftest.py          # records which feature each test covers (shipped)
  unit/                # fakes for Slurm and SSH; run anywhere
  integration/         # real Slurm on the workstation, `kotl run` with a dummy command, no FPGA
  hw/                  # real VCU118; marked hw; only submitted through Kotl
docs/architecture/
  index.html           # renderer only; don't put content here
  architecture.json    # boxes, arrows, details, commands, files, flows
  status.json          # build status per part
```

**The lease and adapters (decided 2026-11-22):** the core is a generic board lease: claim a board, add a job key, run the user's work, then the end step. It has no task knowledge. `kotl lease`/`release` and `kotl run -- <cmd>` use it directly. An **adapter** is a folder of optional hooks (or one Python class): `triggers` (what starts and ends a lease, e.g. FireSim commands), `check`, `prepare`, `stop` (polite stop, safe any time and more than once) and `collect`. FireSim is the first adapter; program/reset and board tests come later the same way.

## 5. Milestones (each ends with its parts green in the view)

**M0: Repo, tooling, status checks** (the tooling is already shipped; adopt and verify it)
- Run `git config core.hooksPath .githooks` and add `.kotl/` and `__pycache__/` to `.gitignore`.
- Create the package skeleton (`kotl/`, `kotl/core/`, `kotl/adapters/`) and a first tagged test.
- Run `python3 tools/status.py check`. It must pass.
- Done when: a commit that changes code without its status is refused, a file no feature owns is refused, and `pytest` followed by `tools/status.py refresh` turns a `built` feature with a passing tagged test green in the view.

**M1: Workstation and PC setup** (scripts written by you, run by the admin)
- Slurm single node: slurmctld, slurmd, slurmdbd with MariaDB, munge. Use the licenses, priority, QOS, `OverTimeLimit`, `KillWait` and health-check lines from the view's `slurm.conf` card.
- The `kotl` account and `kotl-users` group, the sudoers rule, and `/srv/kotl`, `/var/lib/kotl` with correct ownership.
- The kotl SSH key, plus the PCs' `sshd_config.d/kotl.conf` and kotl's `.screenrc`. Verify the lockdown: a normal user gets `Permission denied`.
- The PC's FireSim account and the `kotl-keys` helper for job keys; Slurm `Epilog=`; the `firesim` wrapper on PATH (`/etc/profile.d/kotl.sh`). No shared FireSim install.
- Done when `deploy/verify-m1.sh` passes: `sbatch -L vcu118:1` jobs queue and run, a second one waits for the license, `scancel` by another user is refused, history shows completed and cancelled jobs, and `sudo -u kotl ssh vcu118-pc1 hostname` works. (In soft lockdown, a normal user's password ssh still works on purpose.)

**M2: Board lease end to end (no FPGA)**
- Registry with atomic claim and release, plus state changes.
- `deploy/job.sh`, the epilog and the launcher (the lease): ownership check, adapter hooks, `--max`/`--idle` guards, and the end step on exit or SIGTERM within `KillWait`.
- CLI: `lease`, `release`, `run -- <cmd>`, `status`, `cancel`, `history`, `logs -f`, `fetch`.
- The results folder and `status.json` per job.
- Done when: `kotl run -- sleep 30` goes queued → running → done through real Slurm, cancel stops it cleanly, `--max` trips correctly, and two jobs never claim the same board.

**M3: FireSim batch jobs on a real board**
- The FireSim adapter: triggers (`infrasetup` starts a lease, `runworkload` returning or `firesim kill` ends it), `check` (template: powers off, or `--expect`), `prepare` (per-job `config_runtime.yaml`), `stop` (`firesim kill`), `collect` (results plus the KOTL RESULT marker). Job keys and the PC-side `kotl-keys` helper.
- `--expect` support, with expect running against the console.
- Record setup time.
- Done when: a sample workload passes on VCU118 PC 1 *through Kotl*, a forced hang trips `--max` and leaves the board healthy, and the result shows correctly in Slurm's history.

**M4: Health check, ETA notices, interactive sessions**
- `health.sh` run by Slurm, with registry updates, one driver reload attempt, and alerts.
- The notifier with its systemd timer: ETA and 2× ETA notices, start-estimate slips, board down/up.
- `kotl firesim session` / `attach` / `end`, with the console lockdown verified.
- Done when: unplugging or breaking a board marks it down and back, and a session can attach, detach and end cleanly.

**M5: Kotl plugin for Claude Code**
- The skill (kotl commands, expect scripts with timeouts, fetch-then-read-status workflow) and hooks (check that `firesim` is Kotl's wrapper and job folders follow the template, show the queue at session start).
- Done when: a fresh Claude Code session on a user's PC can submit, wait, fetch and report a FireSim job using only the plugin.

**Later:** power monitor, usage dashboard, program/reset adapter, board-tests adapter, more boards. **Parked:** same-design board pick.

## 6. Keeping the view in sync

Two files, both checked on every commit:
- **`docs/architecture/architecture.json`** is the design: `canvas`, `zones`, `texts`, `dividers`, `nodes` (boxes), `edges` (arrows), `flows` (the step-through tabs), `details` (the panel for each box) and `files` (the file cards).
- **`docs/architecture/status.json`** is build status. It has one entry per box, keyed by the box's `detail` or `id`, plus non-drawn entries like `tooling` (`"drawn": false`). It also holds `watch` (folders whose files must belong to a feature), `shared` (paths no feature needs to own) and `milestones`.

**`python3 tools/status.py check`** (also run by the pre-commit hook, with `--staged`) refuses a commit when:
- a box has no details entry, or no status entry (users excepted);
- a status entry has no box, unless it is `"drawn": false`;
- an arrow or flow step names a box or arrow that doesn't exist, or details list a file card that doesn't exist;
- two boxes overlap, or a box sticks out of the canvas;
- a file under `kotl/`, `deploy/`, `plugin/` or `tools/` belongs to no feature's `code` paths (`__init__.py` excepted);
- code under a feature changed but `status.json` isn't in the commit;
- a status says tested or failing without test results.

Each status entry has these fields: `status`, `milestone`, `now`, `code`, `tests.unit`, `tests.hardware`, `last_commit`, `issues` and `log`.

| Status | Who sets it | Meaning |
|---|---|---|
| `planned` | — | not started |
| `in_progress` | you | being worked on; say what in `now` |
| `built` | you | code done, not yet proven by tests |
| `blocked` | you | waiting on something; say what in `issues` |
| `tested` | **only `tools/status.py`** | all its tests pass (code, and board tests where they exist) |
| `failing` | **only `tools/status.py`** | at least one of its tests fails |
| `later` / `parked` | the user | not in this release |

With every commit that touches a feature:
1. Update its `status`, `now` (one short sentence), `issues`, and add a `log` entry (`date`, `text`).
2. Run the tests, then `python3 tools/status.py refresh`. Refresh fills in test counts and the last commit. It moves a `built` feature to `tested` or `failing`; it leaves `in_progress` alone, so set `built` when the work is done.
3. Commit `status.json` together with the code.

The user watches a published copy of this view on claude.ai, republished from the repo. Push regularly.

## 6a. How to add a part (recipe)

Whenever the system gains a part (an adapter, a board type, a check, a service), the view changes in the **same commit** as the code. **Never move existing boxes.** Use free space; if there is none, grow the zone and `canvas` downward or rightward.

1. **Box:** add a node to `architecture.json` → `nodes`:
   ```json
   {"id": "u250-pc1", "owner": "hardware", "x": 1340, "y": 820, "w": 150, "h": 130,
    "title": "U250 PC 1", "sub": ["sshd + XDMA driver", "no Kotl code"], "align": "top",
    "inner": {"x": 1360, "y": 894, "w": 110, "h": 40, "text": "U250 board"}}
   ```
   - `owner` sets the color and lens: `kotl` (ours, teal), `slurm`, `outside` (other off-the-shelf), `hardware`, or `user`.
   - Other optional fields: `later: true` (dashed outline), `style: "chip"` (a small teal chip, with `inside: "<parent id>"`), `slurm: true` (a Kotl box that talks to Slurm), and `detail` (share another box's details and status).
   - Box sizes follow the grid: core and adapter boxes are 170×70 in the four Kotl columns (x = 281, 477, 673, 869; rows y = 280, 400, 520, 650). PCs are 150 wide at x = 1340.
2. **Arrows:** add edges with `from`, `to`, an orthogonal path `d` (`M x,y H x V y`) that ends exactly on a box edge, `style` (`solid`, `bg` for background checks, `fut` for later), `slurm: true` if it is a Kotl ↔ Slurm link, and a short `label` (`{text, x, y, anchor}`, or `rotate: -90` for a vertical label).
3. **Details:** add `details["<id>"]` with `kind`, `title`, `what`, `bullets`, `term` (commands as `{host, lines:[{c}|{o}|{k}]}`) and `files` (keys into `files`). Add any new config file to `files` with `name`, `path`, `ext`, `desc` and `body`.
4. **Status:** add `features["<id>"]` to `status.json` with `title`, `status`, `milestone` and `code` paths.
5. **Flows:** if a flow now passes through the new part, add its box and arrow ids to that step.
6. **Update what changed elsewhere:** other boxes' details and file cards often change too. Update `latest` in `architecture.json` with one line on what changed.
7. **Check and look:** run `python3 tools/status.py check`, then open the view and look at the new box once. Fix overlaps and cut-off labels before committing.

**Worked example: adding a U250 board type**
- **Hardware:** a `u250-pc1` box under the FPGA PCs, as above. Grow the `net` zone and `canvas.h` to make room, an arrow from the `key` bar, and status `planned` at milestone `Later` (or the user's choice) with `code: ["deploy/pc/"]`.
- **Slurm:** change the `slurmconf` file card to `Licenses=vcu118:2,u250:1`, and the `queue` details to say board types are separate licenses.
- **Registry:** no new box. Its `type` column already exists, so mention `u250` in its details.
- **FireSim adapter:** if U250 needs a different FireSim platform, say in `fsmod` details that `prepare` picks the platform from the board's `type`. Add a file card for any new config, and a `log` line in its status.
- **Health check:** if the check differs per type (another PCI device ID), update `health` details and the `healthsh` card.
- Run `check`, look at the view, and commit code, `architecture.json` and `status.json` together.

## 7. Testing

- **Unit:** fake `slurm.py` and `ssh.py`. Every feature gets tests tagged `@pytest.mark.feature("<key>")`. `tests/conftest.py` records the results to `.kotl/test-results.json` for `refresh`.
- **Integration:** real Slurm on the workstation, `kotl run` with a dummy command, no boards. Tag them the same way.
- **Hardware:** `@pytest.mark.hw`. Submit through Kotl, never directly. Copy the job's `.kotl/test-results.json` back and run `tools/status.py refresh --results <file>`. Results land in `tests.hardware`.

## 8. Open questions for the user (ask, don't guess)

1. Where the repo is hosted (GitHub is needed for the claude.ai view to sync).
2. Host names or IPs of the two FPGA PCs and the workstation; the admin account name.
3. The list of users for `kotl-users`.
4. FireSim and Chipyard versions, the hwdb entry names, and a known-good sample workload.
5. Priority weights (the user plans to tune these), and the default ETA if a user gives none (or require it).
6. The notice channel besides the Claude plugin: email, desktop, or chat.
7. Whether the workstation can run MariaDB for Slurm accounting.

**Answers (2026-11-22).** User names stay out of git; they live in a local config that the `deploy/` scripts read.
1. GitHub `HeshanDissanayake/kotl`. The user pushes.
2. Workstation `comparch`. One VCU118 PC at `192.168.1.2` (`vcu118-pc1`); PC 2 is later. Admin: one configurable account, changeable with a `deploy/` script.
3. `kotl-users`: every regular account on the workstation, with scripts to add and remove users.
4. Users' own Chipyard 1.11.0 and FireSim 1.18.0 (reference copy `/research/heshds/chipyard`, **read-only, never modify**). M3 smoke test: `linux-poweroff` on `xilinx_vcu118_firesim_rocket_singlecore_4GB_no_nic`.
5. Rough weights from the view's `slurm.conf` card. **ETA is required**; there is no default.
6. Notices: the Claude plugin only (plus `kotl status`).
7. MariaDB: yes, slurmdbd on the workstation.
- PC FireSim account: `virtex-host`, which receives job keys.
- **Soft lockdown for now** (`lockdown = soft` in `/etc/kotl/kotl.conf`): password logins to `virtex-host` and existing keys keep working; the end step kills only the job's own sessions and simulations; unleased work only warns. **Full lockdown later**: a separate admin account, `virtex-host` key-only, and the end step kills every `virtex-host` process.
- The old `fpga-vcu118` xlock is retired: Kotl replaces it.
