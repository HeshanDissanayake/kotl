# Next: what Claude needs from you

This file always holds only the current steps. **To run them: `bash ~/working_dir/kotl/deploy/next.sh`**
(it asks before each step and logs everything to `.kotl/next.log`).

1. **Update Kotl (sudo).** The end step now runs each adapter's cleanup on the PC after the job's
   key is removed; for FireSim that's `kotl-firesim-stop`, as root.
2. **Update the PC (sudo there).** Installs `kotl-firesim-stop` and its sudoers line (kotl may run
   only it, as root, with no arguments), next to `kotl-xdma-reload`. FireSim starts its driver
   through sudo, so the driver runs as root and the board account couldn't stop it before.
3. **Run the FireSim test package** on the board (your research folder's `kotl-firesim-test`).
   It proves the package before you hand it out, and the job's `launcher.log` should end with
   `end step: kotl-firesim-stop: no FireSim driver running` (the run already cleaned up).
