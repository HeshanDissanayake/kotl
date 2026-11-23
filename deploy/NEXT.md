# Next: what Claude needs from you

This file always holds only the current steps. Copy commands from here.

Nothing right now. M3 is done and the health check is live (`kotl board list` shows its warnings).

About the glibc warning: the PC runs Ubuntu 22.04 (glibc 2.35), the workstation 24.04 (glibc 2.39).
A package update on the PC can't close that gap. Keep using the workaround for FireSim runs:

```sh
kotl run --eta 30m -- ~/working_dir/kotl/deploy/examples/firesim-smoke.sh --use-pc-glibc <your runtime config>
```

(or remove the bundled glibc yourself after infrasetup). Claude is working on M4.
