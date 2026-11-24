# Next: what Claude needs from you

This file always holds only the current steps. **To run them: `bash ~/working_dir/kotl/deploy/next.sh`**
(it asks before each step and logs everything to `.kotl/next.log`).

1. **Update Kotl everywhere with `deploy/kotl/update.sh`.** One script from now on. It reinstalls
   the workstation (`install.sh`, keeping the boards and adapters; it asks for sudo), then the
   board's PC: Kotl's helpers and the FireSim adapter's (it asks for the sudo password there).
   Nothing changed in the helpers this time, so this run mainly tests the script.
   Preview first if you like: `bash deploy/kotl/update.sh --dry-run`.
