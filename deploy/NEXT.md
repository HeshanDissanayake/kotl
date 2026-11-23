# Next: what Claude needs from you

This file always holds only the current steps. Copy commands from here.

## Why

Smoke job 47 ran through Kotl correctly, but FireSim's driver didn't start on the PC:
`libc.so.6: undefined symbol: __tunable_is_initialized, version GLIBC_PRIVATE`.
FireSim bundles the workstation's glibc (now 2.39-0ubuntu8.12, updated since 7 Nov), and the
PC's own loader is older. The PC's glibc has to match the workstation's.

## 0. Install the new health check (sudo on the workstation)

```sh
cd ~/working_dir/kotl
sudo deploy/kotl/install.sh --board vcu118-pc1=vcu118@vcu118-pc1
kotl board check          # expect a "glibc differs" warning for vcu118-pc1
```

From now on Slurm runs this check every 5 minutes, and `kotl board list` and `kotl top` show
the warning until the versions match.

## 1. Compare glibc versions

```sh
ldd --version | head -n 1
ssh virtex-host@192.168.1.2 'ldd --version | head -n 1; lsb_release -ds'
```

The workstation shows `2.39-0ubuntu8.12`. If the PC shows an older `2.39-0ubuntu8.x` (Ubuntu 24.04),
go on to step 2. If the PC runs a different Ubuntu release, stop and tell Claude.

## 2. Upgrade glibc on the PC (sudo on the PC)

```sh
ssh -t virtex-host@192.168.1.2 'sudo apt-get update && sudo apt-get install --only-upgrade -y libc6 libc-bin && ldd --version | head -n 1'
```

This is a normal Ubuntu security update, but it is still a change on the PC: do it when no one is
running FireSim there. Afterwards `kotl board check` should print `vcu118-pc1: ok`.

## 3. Smoke run again (in your FireSim shell)

```sh
cd /research/$USER/chipyard && source env.sh
cd sims/firesim && source sourceme-manager.sh --skip-ssh-setup && cd deploy
kotl run --eta 30m -- ~/working_dir/kotl/deploy/examples/firesim-smoke.sh config_runtime_kotl_smoke.yaml
```

It ends with `KOTL RESULT: PASS` only if the simulated Linux really powered off.

## 4. Tell Claude

The job number. No sudo on the workstation is needed.
