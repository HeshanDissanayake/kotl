# Next: what Claude needs from you

This file always holds only the current steps. Copy commands from here.

M3 is done: job 49 booted Linux on the VCU118 through Kotl and passed.

## 1. Install the health check (sudo on the workstation)

```sh
cd ~/working_dir/kotl
sudo deploy/kotl/install.sh --board vcu118-pc1=vcu118@vcu118-pc1
kotl board check
```

`kotl board check` warns that glibc differs between the workstation and the PC. Choose one:
- keep working around it: run FireSim with `deploy/examples/firesim-smoke.sh --use-pc-glibc`
  (or delete the bundled glibc yourself after infrasetup);
- or upgrade the PC so the warning goes away:
  `ssh -t virtex-host@192.168.1.2 'sudo apt-get update && sudo apt-get install --only-upgrade -y libc6 libc-bin'`

## 2. Tell Claude

When the install is done, so it can start M4.
