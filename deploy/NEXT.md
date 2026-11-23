# Next: what Claude needs from you

This file always holds only the current steps. **To run them: `bash ~/working_dir/kotl/deploy/next.sh`**
(it asks before each step and logs everything to `.kotl/next.log`; Claude sees the log with your
next message). This file explains them.

## 1. Update kotl-keys on the PC, then Kotl on the workstation (sudo on both)

- kotl-keys: "something runs as virtex-host" now counts only remote work (SSH sessions, screen,
  tmux, FireSim drivers), not the PC's desktop login. That stops the long warning, and it lets a
  lease's idle guard work at all.
- Kotl: `kotl top` no longer crashes on terminals that can't hide the cursor; long process lists
  are capped.

## 2. Say "ok PC" in your next message if Claude may run its two short tests

- ETA notice: `kotl run --eta 1m -- sleep 100` (about 2 minutes on the board).
- Console attach: a short lease, then `kotl attach` (about 30 seconds).
