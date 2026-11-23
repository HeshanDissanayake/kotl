# M3 setup: job keys on the real board, and a FireSim run through Kotl

Run each block as written, in order. The admin runs these on comparch, from the Kotl repo
(`cd ~/working_dir/kotl`) unless a block says otherwise.

---

## 1. Update kotl-keys on the PC (192.168.1.2)

kotl-keys gained a `busy` command for the lease idle guard. These commands copy it over and
install it again. Nothing else on the PC changes.

```sh
cd ~/working_dir/kotl
scp deploy/pc/setup.sh deploy/pc/kotl-keys virtex-host@192.168.1.2:/tmp/
ssh -t virtex-host@192.168.1.2 "sudo bash /tmp/setup.sh --keys-helper /tmp/kotl-keys && rm /tmp/setup.sh /tmp/kotl-keys"
```

Expect: `kotl-pc: kotl-keys installed; kotl may run it as virtex-host`

---

## 2. Update Kotl on the workstation

```sh
cd ~/working_dir/kotl
sudo deploy/kotl/install.sh --board vcu118-pc1=vcu118@vcu118-pc1
```

Expect, near the end: `removed /opt/kotl/bin/firesim` and `removed /etc/profile.d/kotl.sh`
(the old wrapper going away), then `wrote /etc/ssh/ssh_config.d/kotl.conf`.

Check:

```sh
ls /opt/kotl/bin                 # only: kotl
grep -c ssh-agent /opt/kotl/job.sh   # 1 or more
```

---

## 3. Job-key test (holds the board about 30 s)

Use a plain shell: no conda env, no venv active.

```sh
cd ~/working_dir/kotl
KOTL_HW=1 .venv/bin/pytest -m hw tests/hw -k job_key
```

Expect: `1 passed`. The test takes a lease, logs in to the PC with the lease's key, releases
the lease, and checks that the same key is refused afterwards.

---

## 4. A shell for FireSim

Open a **new terminal**. Kotl's `.venv` must not be active: its `python3` hides Chipyard's
(job 30 failed with `No module named 'argcomplete'` because of this).

```sh
cd /research/$USER/chipyard
source env.sh
cd sims/firesim
source sourceme-manager.sh --skip-ssh-setup
cd deploy
which python3        # must be /research/$USER/chipyard/.conda-env/bin/python3
```

---

## 5. Build the linux-poweroff workload (once)

FireSim makes its disk image (`poweroffnode.ext2`) from your existing `br-base.img`.
Job 36 failed because this hadn't been built yet.

```sh
cd /research/$USER/chipyard/sims/firesim/deploy/workloads
make linux-poweroff
ls linux-poweroff/        # must list poweroffnode.ext2
cd ..
```

## 5b. Make the smoke-test config (once)

Your `config_runtime.yaml` already has the stock design
(`xilinx_vcu118_firesim_rocket_singlecore_4GB_no_nic`) and the run farm
(`virtex-host@192.168.1.2`). Only the workload changes, from `br-base.json` (it waits at a
login prompt and never powers off) to `linux-poweroff.json` (it boots, then powers off).

```sh
cp config_runtime.yaml config_runtime_kotl_smoke.yaml
sed -i 's/^\(\s*workload_name:\) br-base.json/\1 linux-poweroff.json/' config_runtime_kotl_smoke.yaml
grep -nE "workload_name|^ *default_hw_config:|@192" config_runtime_kotl_smoke.yaml
```

Expect three lines:
`- virtex-host@192.168.1.2: one_fpgas_spec`,
`default_hw_config: xilinx_vcu118_firesim_rocket_singlecore_4GB_no_nic`,
`workload_name: linux-poweroff.json`.

---

## 6. Run it through Kotl

In the same shell (still in `deploy/`):

```sh
kotl run --eta 30m -- ~/working_dir/kotl/deploy/examples/firesim-smoke.sh --use-pc-glibc config_runtime_kotl_smoke.yaml
```

`--use-pc-glibc` removes the glibc libraries FireSim bundled from the workstation, so the
driver uses the PC's own (needed while their glibc versions differ; `kotl board check` says).

What happens: `kotl: job N queued`, FireSim's infrasetup output (flashes the board), then
runworkload boots Linux, which powers off. runworkload returns, and you see
`kotl: job N succeeded · vcu118-pc1 freed`. The board is freed at that moment, not at 30 min.

Note the job number `N`.

---

## 7. Check and record it

Back in a plain shell (no conda env, no venv active):

```sh
cd ~/working_dir/kotl
KOTL_HW=1 KOTL_SMOKE_JOB=N .venv/bin/pytest -m hw tests/hw
```

Expect: `2 passed`. Then tell Claude the job number, and it folds the results into the view.

If step 6 fails, send Claude the last 20 lines it printed and the job number.
