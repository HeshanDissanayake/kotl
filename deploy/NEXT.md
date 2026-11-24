# Next: what Claude needs from you

This file always holds only the current steps. **To run them: `bash ~/working_dir/kotl/deploy/next.sh`**
(it asks before each step and logs everything to `.kotl/next.log`).

1. **Update Kotl (sudo).** Brings `kotl setup` and `kotl client-bundle`, the fixed Claude band
   (`/kotl-band`), the band and VS Code extension reading the daemon's file every second.
2. **`kotl setup`** for yourself: it re-installs the Claude plugins and the VS Code extension the
   way every new user will. Then reload the VS Code window and start a new `claude`.
3. **XDMA check** (read-only): `poll_mode=1` is right.
4. **Only if it isn't:** reload XDMA with the fixed helper, when nobody runs FireSim.

New users: the view's first tab, **New user: start here**, walks them through it. The admin adds
them with `sudo deploy/accounts.sh add-user NAME`, which now tells them what to run next.
