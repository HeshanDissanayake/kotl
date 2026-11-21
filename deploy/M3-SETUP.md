# M3 setup: job keys and the firesim wrapper

## 1. The FPGA PC (192.168.1.2): kotl-keys

This adds `/usr/local/bin/kotl-keys` and one sudoers line, so kotl may run only kotl-keys, as
virtex-host. Nothing else on the PC changes (soft lockdown).

```sh
scp deploy/pc/setup.sh deploy/pc/kotl-keys virtex-host@192.168.1.2:/tmp/
ssh -t virtex-host@192.168.1.2 "sudo bash /tmp/setup.sh --keys-helper /tmp/kotl-keys && rm /tmp/setup.sh /tmp/kotl-keys"
```

## 2. The workstation: update Kotl

Same command as M2. This time it adds the firesim wrapper (`/opt/kotl/bin/firesim`),
`/etc/profile.d/kotl.sh` (puts the wrapper first on PATH) and `/etc/ssh/ssh_config.d/kotl.conf`.

```sh
sudo deploy/kotl/install.sh --board vcu118-pc1=vcu118@vcu118-pc1
```

Log in again (or run `export PATH=/opt/kotl/bin:$PATH`), then check:

```sh
which firesim          # /opt/kotl/bin/firesim
kotl lease --eta 10m
ssh vcu118-pc1 hostname   # uses your job key
kotl release
```

## 3. Job-key test (touches the PC; holds the board about 30 s)

```sh
.venv/bin/pytest -m hw tests/hw -k job_key
```

## 4. FireSim smoke test, from your own Chipyard

Use a copy of your runtime config with the stock design and workload:
`default_hw_config: xilinx_vcu118_firesim_rocket_singlecore_4GB_no_nic` and
`workload_name: linux-poweroff.json`.

```sh
cd <your chipyard> && source env.sh && cd sims/firesim && source sourceme-manager.sh --skip-ssh-setup && cd deploy
which firesim                       # must say /opt/kotl/bin/firesim
export KOTL_ETA=30m
firesim infrasetup  -c config_runtime_kotl_smoke.yaml    # waits for the board, then sets it up
firesim runworkload -c config_runtime_kotl_smoke.yaml    # boots Linux, powers off, frees the board
```

The last line names the job, for example `kotl: job 57 done · vcu118-pc1 freed`. Then:

```sh
KOTL_SMOKE_JOB=57 .venv/bin/pytest -m hw tests/hw
```

Then tell Claude. It folds the results into the view.
