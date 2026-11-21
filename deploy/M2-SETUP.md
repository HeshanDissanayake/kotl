# M2 setup: install Kotl's code

Run on the workstation (comparch), from the repo folder. To preview, add `--dry-run`.

```sh
sudo deploy/kotl/install.sh --board vcu118-pc1=vcu118@vcu118-pc1
```

This copies `kotl/` to `/opt/kotl/lib` and installs `/opt/kotl/launch`, `/opt/kotl/job.sh`,
`/opt/kotl/epilog.sh` (replacing the M1 no-op) and the `kotl` command (`/usr/local/bin/kotl`).
It adds the board to the registry and makes the `kotl` account a Slurm operator, so its
guards can cancel a hung job. It doesn't touch the FPGA PC.

Re-run the same command after every repo update that changes `kotl/` or `deploy/job.sh`.

**Log in again first.** Sessions that started before M1 added you to `kotl-users` don't have the group yet,
so `sudo` to kotl asks for a password. A new login, `newgrp kotl-users`, or `sg kotl-users -c '...'` fixes it.
The same goes for every user who was logged in during M1.

Then try it as yourself:

```sh
kotl status
kotl run --eta 5m -- hostname
```

Then tell Claude. It runs the M2 integration tests (`tests/integration/`), which submit a
few small `sleep` jobs through Slurm.

Undo: `sudo deploy/kotl/install.sh --undo`. This keeps the registry and results, and leaves a
no-op epilog so Slurm keeps working.
