# Next: what Claude needs from you

This file always holds only the current steps. **To run them: `bash ~/working_dir/kotl/deploy/next.sh`**
(it asks before each step and logs everything to `.kotl/next.log`).

1. **Update Kotl (sudo)** with `--adapters firesim`: FireSim's checks, XDMA repair, cleanup and
   console now live in the FireSim adapter, switched on in `/etc/kotl/kotl.conf`
   (`adapters = firesim`). Without that line Kotl runs generic only.
2. **Update the PC (sudo there):** `kotl-keys` is generic now (it stops what the workstation's
   adapters name), and the FireSim adapter installs its own PC part (`kotl-xdma-reload`, same
   paths as before, so nothing else changes).
3. **`kotl board check`:** the same checks as before, through the adapter.
4. **`kotl setup`** for yourself, if you haven't yet (Claude plugins + VS Code extension).
