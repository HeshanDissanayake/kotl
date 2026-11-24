# Next: what Claude needs from you

This file always holds only the current steps. **To run them: `bash ~/working_dir/kotl/deploy/next.sh`**
(it asks before each step and logs everything to `.kotl/next.log`).

1. **Run the FireSim test package on the board.** It's a self-contained folder
   (`/research/heshds/kotl-firesim-test`, 623 MB) that any Kotl user can run without Chipyard:
   it checks the PC, flashes the FPGA, boots Linux, waits for the power-off and prints
   `KOTL RESULT: PASS`. This first run proves it before you hand it out. Results go to
   `/research/heshds/kotl-test-runs/firesim-test-results/<job>/`.

To hand it out: users (or their Claude) run
`kotl run --eta 15m -- /research/heshds/kotl-firesim-test/run.sh` from any folder they can write to.
The folder's `README.md` has the steps, including a section for Claude.
