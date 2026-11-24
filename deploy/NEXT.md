# Next: what Claude needs from you

This file always holds only the current steps. **To run them: `bash ~/working_dir/kotl/deploy/next.sh`**
(it asks before each step and logs everything to `.kotl/next.log`).

Job 68 stopped at its first check: a FireSim console (`fsim0`) was already running on the PC,
outside any Kotl job (the 22:25 health check had warned about it too). Job 68's end step most
likely stopped it, since the end step stops every FireSim screen and driver on the board's PC.

1. **Look (read-only):** what FireSim runs on the PC now, and the end of job 68's `launcher.log`
   (it should show `end step: kotl-firesim-stop: ...`).
2. **Run the test package again.** If the console was a leftover, this run should pass.
3. **Update Kotl (sudo, small):** the client installer now carries Kotl's mark, so installs stop
   keeping a stale `.kotl-orig` copy.

If someone was running FireSim directly on the PC (outside Kotl), their run was ended by job 68.
