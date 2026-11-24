# Next: what Claude needs from you

This file always holds only the current steps. **To run them: `bash ~/working_dir/kotl/deploy/next.sh`**
(it asks before each step and logs everything to `.kotl/next.log`).

Kotl 1.0.0 (milestone P): Kotl sets up and removes PCs itself, updates everything in one go,
uninstalls completely, and tells users when their copy is out of date.

1. **Update to 1.0.0** with `deploy/kotl/update.sh`: the workstation (sudo), then the PC (its sudo
   password, once).
2. **Test PC onboarding** by re-adding the board you have:
   `bash deploy/kotl/pc.sh add vcu118-pc1 vcu118 192.168.1.2`. It re-applies everything (same key,
   same helpers, the board keeps its state and jobs) and ends with the board check.
3. **Preview the uninstall** (`--dry-run`: nothing changes). Read what it would remove.
4. **`kotl version`, then `kotl setup`**, and reload VS Code. Before step 4, VS Code should show an
   up-arrow on Kotl and ask you to run `kotl setup`: that's the new update nudge.
