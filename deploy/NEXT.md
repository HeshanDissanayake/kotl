# Next: what Claude needs from you

This file always holds only the current steps. **To run them: `bash ~/working_dir/kotl/deploy/next.sh`**
(it asks before each step and logs everything to `.kotl/next.log`; Claude sees the log with your
next message). deploy/M5-SETUP.md has the full procedure.

## 1. Publish the plugin (sudo)

Re-runs the Kotl install, which now also copies the plugin to `/opt/kotl/plugin` with a marketplace
file at `/opt/kotl`, readable by every user on the workstation.

## 2. Install them in your Claude Code (no sudo)

`claude plugin marketplace add /opt/kotl`, `claude plugin install kotl@kotl`, and the optional
`claude plugin install kotl-band@kotl` (the live Kotl line above the prompt; `/kotl hide` hides it).

## 3. Try it in a NEW Claude Code session

Open a new terminal, start `claude` anywhere (not this session), and ask:

    run hostname on the FPGA board through kotl and tell me the result

The Kotl line should sit above the prompt. It should: show the Kotl queue at the start, run `kotl run --eta ... -- hostname`, and report the
result (vcu118-pc1's job, `succeeded`, the PC's hostname). Then ask it:

    run firesim runworkload -c config_runtime.yaml

and check that it asks you first and suggests `kotl run`. Answer no.

Tell Claude how it went (the log shows steps 1 and 2; step 3 happens in the other session).
