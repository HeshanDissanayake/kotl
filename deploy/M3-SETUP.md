# M3 setup: job keys on the real board

## 1. The FPGA PC (192.168.1.2): kotl-keys

This adds `/usr/local/bin/kotl-keys` and one sudoers line, so kotl may run only kotl-keys, as
virtex-host. Nothing else on the PC changes (soft lockdown).

```sh
scp deploy/pc/setup.sh deploy/pc/kotl-keys virtex-host@192.168.1.2:/tmp/
ssh -t virtex-host@192.168.1.2 "sudo bash /tmp/setup.sh --keys-helper /tmp/kotl-keys && rm /tmp/setup.sh /tmp/kotl-keys"
```

## 2. The workstation: update Kotl

Same command as M2. It adds `/etc/ssh/ssh_config.d/kotl.conf`, so plain `ssh vcu118-pc1` uses
your job key during a lease. It also removes any firesim wrapper or PATH snippet left by an
earlier M3 install.

```sh
sudo deploy/kotl/install.sh --board vcu118-pc1=vcu118@vcu118-pc1
```

## 3. Check: the job key works only during a lease

This touches the PC and holds the board for about 30 s.

```sh
KOTL_HW=1 .venv/bin/pytest -m hw tests/hw -k job_key
```

## 4. FireSim smoke test, from your own Chipyard

Use a copy of your runtime config with the stock design and workload:
`default_hw_config: xilinx_vcu118_firesim_rocket_singlecore_4GB_no_nic` and
`workload_name: linux-poweroff.json`. Its run farm stays `virtex-host@192.168.1.2`, as now.

```sh
cd <your chipyard> && source env.sh && cd sims/firesim && source sourceme-manager.sh --skip-ssh-setup && cd deploy
kotl run --eta 30m -- sh -c "firesim infrasetup -c config_runtime_kotl_smoke.yaml && firesim runworkload -c config_runtime_kotl_smoke.yaml"
```

The board is held while that runs and is freed the moment `runworkload` returns. The output
names the job (`kotl: job 57 queued`). Then:

```sh
KOTL_HW=1 KOTL_SMOKE_JOB=57 .venv/bin/pytest -m hw tests/hw
```

Then tell Claude. It folds the results into the view.
