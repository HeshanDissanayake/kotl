# Next: what Claude needs from you

This file always holds only the current steps. **To run them: `bash ~/working_dir/kotl/deploy/next.sh`**
(it asks before each step and logs everything to `.kotl/next.log`).

Someone ran FireSim directly on the PC (outside Kotl), and job 69's end step most likely ended it:
the cleanup stopped every FireSim screen and driver on the PC. That's fixed: the end step now stops
only what started during the job, and work outside Kotl is left running and reported with **who**
(their workstation account, from their open connections to the PC) and **how long**.

1. **Update Kotl (sudo).**
2. **Update the PC (sudo there):** the new `kotl-keys` and `kotl-firesim-stop` (and its sudoers line,
   which now also accepts the job's age). Also fixes job 68's `exit 255`: the old cleanup matched its
   own command line and killed itself.
3. **`kotl board check`:** shows any work outside Kotl, with who and how long.
4. **Run the FireSim test package**, once step 3 shows nothing outside Kotl.
