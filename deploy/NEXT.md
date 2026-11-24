# Next: what Claude needs from you

This file always holds only the current steps. **To run them: `bash ~/working_dir/kotl/deploy/next.sh`**
(it asks before each step and logs everything to `.kotl/next.log`).

Every Claude session should know Kotl before it touches a board, not after a run was killed. The
skill and the plugin's session start now say it, and the install adds Kotl's rules to Claude
Code's workstation-wide `/etc/claude-code/CLAUDE.md`, which every Claude session here reads, with
or without the plugin (an admin's own file there would be left alone).

1. **Update Kotl (sudo).** Publishes the new skill, the hook and `/etc/claude-code/CLAUDE.md`.
2. **Show the file**, to read what Claude sessions now get.
3. **Try it:** start a new Claude Code session anywhere on the workstation and ask "how do I use
   the FPGA board?". It should answer with `kotl run` / `kotl lease`.
