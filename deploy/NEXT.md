# Next: what Claude needs from you

This file always holds only the current steps. **To run them: `bash ~/working_dir/kotl/deploy/next.sh`**
(it asks before each step and logs everything to `.kotl/next.log`).

## The Claude band: fixed, needs the install

The band never drew anything (CLI or VS Code): its `/kotl` command clashed with the kotl plugin's
skill, and that stopped it before it read any data. Fixed (now `/kotl-band`). Step 1 below publishes
it to `/opt/kotl`; then reload VS Code's window (or start a new `claude`).

## XDMA (from before)

Job 54 failed with `xdma_id != -1`. FireSim's infrasetup unloads the XDMA driver, flashes the FPGA,
then loads it with `poll_mode=1`, but only if it isn't loaded already. Kotl's health check
reloaded it with a plain `modprobe` (no `poll_mode`), and even while a job held the board. Fixed:
it now reloads only on an idle board, exactly as FireSim does. The PC may still have the driver
loaded the wrong way from earlier, so check it once and reload it.

## Steps (in next.sh)

1. Update `kotl-xdma-reload` on the PC (sudo there) and Kotl on the workstation (sudo).
2. Show how XDMA is loaded now: `poll_mode=1` is right; `poll_mode=0` or none is the problem.
3. If it isn't `poll_mode=1`: reload it with the fixed helper. Only when nobody runs FireSim.
4. Check the terminal can reach Kotl (`kotl-users`; restart tmux or log in again if not).

Also: in your other Claude sessions, deactivate Kotl's test venv (`deactivate`) before running
FireSim. Jobs 55 to 58 failed because that venv's Python hid Chipyard's.

## VS Code

The Kotl extension is installed in your VS Code (`kotl.kotl-status`). It needs the VS Code server
restarted to show anything but "unreachable" (the same kotl-users reason): in VS Code run
**Remote-SSH: Kill VS Code Server on Host**, then reconnect. Kotl then sits in the status bar
(bottom left); hover it for the queue, click it for `kotl top`.

Other users install it once with `code --install-extension /opt/kotl/kotl-status.vsix`
(from a VS Code terminal).
