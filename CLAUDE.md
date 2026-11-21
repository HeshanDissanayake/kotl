# Kotl: rules for Claude in this repo

Read `HANDOFF.md` first. The design lives in `docs/architecture/architecture.json`, and build status in `docs/architecture/status.json`. `index.html` only draws them; serve the folder with `python3 -m http.server`.

## Always
- Keep the view true, in the **same commit** as the code:
  - Touched a feature: update its `status`, `now`, `issues` and a `log` line in `status.json`.
  - Added a part or a link (adapter, board type, check, service): follow HANDOFF section 6a. That means a box and arrows in `architecture.json`, its details, commands and file cards, its status entry, and any flows it joins. Never move existing boxes.
- You may set `in_progress`, `built` and `blocked`. Only `tools/status.py refresh` sets `tested` or `failing`.
- After tests: `python3 tools/status.py refresh`. Before committing: `python3 tools/status.py check` (the pre-commit hook runs it too; fix what it reports, never bypass it).
- After changing `architecture.json`, open the view and look at it once.
- Tag every test with `@pytest.mark.feature("<key>")`; board tests also get `@pytest.mark.hw` and skip unless `KOTL_HW=1`. Never run them (or collect them without `--co`) unless the user says so: they touch the FPGA PC.
- Slurm commands only in `kotl/slurm.py`. SSH, scp and rsync to the FPGA PCs only in `kotl/ssh.py`.

## Ask first
- Anything needing root, editing `/etc`, installing system packages, or creating accounts: write a script under `deploy/` and ask the user to run it.
- Anything on the FPGA PCs.
- Lab facts (hosts, users, versions, priority weights). See HANDOFF section 8.

## Never
- Run `firesim` or board tests outside Kotl/Slurm once the queue is live.
- Cancel or touch other users' jobs.
- Commit with `--no-verify`, or keys, passwords or user data.

## Commands
- Code tests: `pytest -m "not hw"`
- Refresh the view's status: `python3 tools/status.py refresh`
- Check code, status and design agree: `python3 tools/status.py check`
- View: `cd docs/architecture && python3 -m http.server 8000`
