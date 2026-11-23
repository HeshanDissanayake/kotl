# M4 setup: health check, ETA notices, console attach

## 1. The FPGA PC: the driver-reload helper (sudo on the PC)

Adds `/usr/local/bin/kotl-xdma-reload` and one sudoers line (kotl may run only that script, as
root, with no arguments). It also refreshes kotl-keys.

```sh
cd ~/working_dir/kotl
scp deploy/pc/setup.sh deploy/pc/kotl-keys deploy/pc/kotl-xdma-reload virtex-host@192.168.1.2:/tmp/
ssh -t virtex-host@192.168.1.2 "sudo bash /tmp/setup.sh --keys-helper /tmp/kotl-keys --driver-helper /tmp/kotl-xdma-reload && rm /tmp/setup.sh /tmp/kotl-keys /tmp/kotl-xdma-reload"
```

Expect `kotl-xdma-reload installed` and `kotl-keys installed`. If it prints
`WARNING: 'modinfo xdma' finds no xdma module`, tell Claude: the reload then needs to know how
your PC loads the driver.

## 2. The workstation: update Kotl (sudo)

Adds the notifier's systemd timer and makes kotl a Slurm admin (to hold a down board's license).

```sh
cd ~/working_dir/kotl
sudo deploy/kotl/install.sh --board vcu118-pc1=vcu118@vcu118-pc1
systemctl list-timers kotl-notifier.timer     # next run within a minute
```

## 3. Tell Claude

Claude then runs, by itself and with no PC access, the license-hold test (drain, a queued job
waits, resume) and checks the notifier. The board tests that break the driver on purpose will be
listed separately, for your OK.
