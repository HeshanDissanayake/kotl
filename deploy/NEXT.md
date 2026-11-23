# Next: what Claude needs from you

This file always holds only the current steps. Copy commands from here.

The workstation part of M4 is already installed. Two steps are left.

## 1. The FPGA PC: driver-reload helper (sudo on the PC)

Adds `/usr/local/bin/kotl-xdma-reload` and one sudoers line (kotl may run only that script, as
root, with no arguments), and refreshes kotl-keys.

```sh
cd ~/working_dir/kotl
scp deploy/pc/setup.sh deploy/pc/kotl-keys deploy/pc/kotl-xdma-reload virtex-host@192.168.1.2:/tmp/
ssh -t virtex-host@192.168.1.2 "sudo bash /tmp/setup.sh --keys-helper /tmp/kotl-keys --driver-helper /tmp/kotl-xdma-reload && rm /tmp/setup.sh /tmp/kotl-keys /tmp/kotl-xdma-reload"
```

Expect `kotl-xdma-reload installed` and `kotl-keys installed`. If it prints
`WARNING: 'modinfo xdma' finds no xdma module`, tell Claude.

## 2. The workstation: install once more (sudo)

It brings in a fix: re-adding the board (every install does) no longer wipes its state.

```sh
cd ~/working_dir/kotl
sudo deploy/kotl/install.sh --board vcu118-pc1=vcu118@vcu118-pc1
```

## 3. Tell Claude

When both are done.
