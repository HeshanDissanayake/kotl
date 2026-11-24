# M1 setup: what the admin runs

Run these on the workstation (comparch), from the repo folder, in this order.
To preview a step first, add `--dry-run`: nothing changes, and the files it would
write go under a temporary folder that the script names.
Each step can be reversed with `--undo` (see the end).

## 1. Accounts, folders, sudoers

```sh
sudo deploy/accounts.sh install --admin <your-user>
```

Creates the `kotl` account and the `kotl-users` group (every regular user), and writes
`/etc/kotl/kotl.conf` (`lockdown = soft`). Also creates `/opt/kotl`, `/var/lib/kotl`,
`/srv/kotl` and `/etc/sudoers.d/kotl`.

## 2. Slurm and MariaDB

```sh
sudo deploy/slurm/install.sh
```

Installs `slurm-wlm slurmdbd munge mariadb-server expect`. Writes `/etc/slurm/{slurm,cgroup,slurmdbd}.conf`
and starts the services. Adds the `kotl` cluster, account and users, and the `urgent` and
`maint` QOS. Safe to re-run.

## 3. The kotl SSH key

```sh
sudo deploy/ssh/setup-kotl-key.sh --pc vcu118-pc1=192.168.1.2
```

Prints kotl's public key at the end.

## 4. The FPGA PC (192.168.1.2)

This step needs `virtex-host` to have sudo on the PC.

```sh
KEY=$(sudo cat /home/kotl/.ssh/id_ed25519.pub)
scp deploy/pc/setup.sh virtex-host@192.168.1.2:/tmp/kotl-pc-setup.sh
ssh -t virtex-host@192.168.1.2 "sudo bash /tmp/kotl-pc-setup.sh --key '$KEY' && rm /tmp/kotl-pc-setup.sh"
```

Adds a `kotl` account on the PC that logs in with that key only. Nothing else on the PC changes:
sshd, `virtex-host`, its password and its keys stay as they are.

## 5. Check everything

```sh
sudo deploy/adapters/firesim/check.sh vcu118-pc1
sudo deploy/verify-m1.sh
python3 tools/status.py refresh --results /tmp/kotl-m1-results.json
```

`verify-m1.sh` submits two short `sleep` jobs, tries to cancel one as another user (this
must be refused), and logs in to the PC as kotl. Every line should say `PASS`.
`refresh` then shows the results in the view.

Send Claude the output of any step that prints `FAIL` or `error`.

## Later: users and admin

```sh
sudo deploy/accounts.sh add-user NAME [NAME...]
sudo deploy/accounts.sh remove-user NAME [NAME...]
sudo deploy/accounts.sh set-admin NAME
sudo deploy/accounts.sh sync            # adds any new regular account
```

## Undo

Run these in reverse order. `--purge` also removes packages, data and the kotl account.

```sh
ssh -t virtex-host@192.168.1.2 sudo bash /tmp/kotl-pc-setup.sh --undo   # copy the script over first
sudo deploy/ssh/setup-kotl-key.sh --undo [--purge]
sudo deploy/slurm/install.sh --undo [--purge]
sudo deploy/accounts.sh --undo [--purge]
```
