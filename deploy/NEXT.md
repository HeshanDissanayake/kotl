# Next: what Claude needs from you

This file always holds only the current steps. **To run them: `bash ~/working_dir/kotl/deploy/next.sh`**
(it asks before each step and logs everything to `.kotl/next.log`). deploy/M5-SETUP.md has the
full procedure.

Why: your new Claude Code session loaded both plugins, but its terminal isn't in `kotl-users`
(your tmux server started before M1 added you), so `sudo` to kotl asked for a password and the
Kotl line had almost nothing to show.

## 0. A fresh terminal (by hand, not in the script)

Detach from tmux and run `tmux kill-server` (this closes ALL your tmux windows), or log out and
back in. New shells then have the `kotl-users` group.

Same for VS Code: its server on the workstation also started before M1. In VS Code run
**Remote-SSH: Kill VS Code Server on Host**, then reconnect. The Kotl band then shows in the
Claude panel too.

## 1. Update Kotl and the plugins (sudo)

The Kotl line now says plainly when a terminal can't reach Kotl, instead of staying almost empty.

## 2. Check the terminal

`id -nG` must list `kotl-users`, and `kotl board list` must work without a password.

## 3. Try it in a NEW Claude Code session

Start `claude` in the fresh terminal. A line starting with **Kotl** should sit above the prompt
(`vcu118-pc1 idle · nobody waiting`). Then ask:

    run hostname on the FPGA board through kotl and tell me the result

and then

    run firesim runworkload -c config_runtime.yaml

which should make Claude Code ask you first and suggest `kotl run`. Answer no.
