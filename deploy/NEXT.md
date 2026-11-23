# Next: what Claude needs from you

This file always holds only the current steps. Copy commands from here.

## 1. FireSim smoke run (in your FireSim shell, not the Kotl venv)

Open a new terminal, then:

```sh
cd /research/$USER/chipyard && source env.sh
cd sims/firesim && source sourceme-manager.sh --skip-ssh-setup
cd deploy/workloads && make linux-poweroff
ls linux-poweroff/
cd ..
kotl run --eta 30m -- sh -c "firesim infrasetup -c config_runtime_kotl_smoke.yaml && firesim runworkload -c config_runtime_kotl_smoke.yaml"
```

The `ls` must list `poweroffnode.ext2`. The last command prints `kotl: job N queued`.

## 2. Tell Claude

- the job number `N` (Claude checks it and turns M3 green)

No sudo is needed.
