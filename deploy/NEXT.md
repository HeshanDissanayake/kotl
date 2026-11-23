# Next: what Claude needs from you

This file always holds only the current steps. Copy commands from here.

## 1. Install once more (sudo on the workstation)

It fixes the health check and the epilog: Slurm starts them with no PATH, so they quietly did
nothing. The health check itself works (Claude ran it by hand).

```sh
cd ~/working_dir/kotl
sudo deploy/kotl/install.sh --board vcu118-pc1=vcu118@vcu118-pc1
```

## 2. Tell Claude

Claude then waits for Slurm's next 5-minute run and checks that it recorded the board.
